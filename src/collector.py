#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from urllib.parse import urlparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, List, Any


# -----------------------------
# Utilities
# -----------------------------

ISO_TS = "%Y-%m-%dT%H:%M:%S%z"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def now_ts():
    return datetime.now().astimezone().strftime(ISO_TS)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse_date_fuzzy(s: str):
    if not s:
        return None
    try:
        dt = dateparser.parse(s, fuzzy=True)
        return dt.date() if dt else None
    except Exception:
        # Try find YYYY-MM-DD by regex
        m = re.search(r"(20\d{2}|19\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", s)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            try:
                return date(int(y), int(mo), int(d))
            except Exception:
                return None
        return None


# -----------------------------
# Robots-aware HTTP client with retries and rate limiting
# -----------------------------

class RobotsAwareClient:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        rpm: int = 12,
        timeout: int = 15,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        logger: Optional[logging.Logger] = None,
        requests_log_path: Optional[str] = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.min_interval = max(0.0, 60.0 / float(max(1, rpm)))
        self.last_request_at = {}  # per netloc
        self.robots = {}
        self.logger = logger or logging.getLogger(__name__)
        self.requests_log_path = requests_log_path
        self._init_session(max_retries, backoff_factor)

        # Prepare request log file header if path provided
        if self.requests_log_path:
            ensure_dir(os.path.dirname(self.requests_log_path))
            if not os.path.exists(self.requests_log_path):
                with open(self.requests_log_path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "ts",
                        "method",
                        "url",
                        "status",
                        "elapsed_sec",
                        "error",
                        "robots_allowed",
                    ])

    def _init_session(self, max_retries: int, backoff_factor: float):
        self.session = requests.Session()
        retry_config = Retry(
            total=max_retries,
            read=max_retries,
            connect=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_config)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": self.user_agent})

    def _robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self.robots:
            rp = robotparser.RobotFileParser()
            rp.set_url(f"{base}/robots.txt")
            try:
                rp.read()
            except Exception:
                # If robots cannot be fetched, default to False for safety
                self.robots[base] = None
                return False
            self.robots[base] = rp
        rp = self.robots.get(base)
        if rp is None:
            return False
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return False

    def _respect_rate_limit(self, netloc: str):
        last = self.last_request_at.get(netloc)
        if last is not None:
            elapsed = time.time() - last
            wait = self.min_interval - elapsed
            if wait > 0:
                time.sleep(wait)
        self.last_request_at[netloc] = time.time()

    def _log_request(self, method: str, url: str, status: Optional[int], elapsed: Optional[float], error: Optional[str], robots_allowed: Optional[bool]):
        if not self.requests_log_path:
            return
        with open(self.requests_log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                now_ts(),
                method,
                url,
                status if status is not None else "",
                f"{elapsed:.3f}" if elapsed is not None else "",
                error or "",
                robots_allowed if robots_allowed is not None else "",
            ])

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, stream: bool = False):
        parsed = urlparse(url)
        robots_allowed = self._robots_allowed(url)
        if not robots_allowed:
            self.logger.warning(f"Robots disallow: {url}")
            self._log_request("GET", url, None, None, "robots_disallow", False)
            return None
        self._respect_rate_limit(parsed.netloc)
        t0 = time.time()
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout, stream=stream)
            elapsed = time.time() - t0
            self._log_request("GET", resp.url if hasattr(resp, 'url') else url, resp.status_code, elapsed, None, True)
            return resp
        except Exception as e:
            elapsed = time.time() - t0
            self.logger.error(f"GET error: {url} -> {e}")
            self._log_request("GET", url, None, elapsed, str(e), True)
            return None


# -----------------------------
# Source 1: State Council search (sousuo.gov.cn) for policy/news items
# -----------------------------

def parse_search_items(html: str):
    soup = BeautifulSoup(html, "lxml")
    items = []
    # Try common container patterns
    containers = []
    for selector in [
        "ul.search-result li",
        "div.result li",
        "div.sr-list li",
        "li.search-result-item",
        "li",
    ]:
        found = soup.select(selector)
        if found:
            containers = found
            break
    if not containers:
        return items
    for li in containers:
        a = li.find("a", href=True)
        if not a:
            continue
        url = a.get("href").strip()
        title = a.get_text(strip=True)
        # Prefer snippet in a dedicated element if exists
        snippet = ""
        des = li.select_one("p.res-des") or li.select_one("p")
        if des:
            snippet = des.get_text(" ", strip=True)
        # Date: search within the li text
        li_text = li.get_text(" ", strip=True)
        dt = parse_date_fuzzy(li_text)
        items.append({
            "url": url,
            "title": title,
            "snippet": snippet,
            "date": dt.isoformat() if dt else None,
        })
    return items


def crawl_gov_search(client: RobotsAwareClient, query: str, start_date: Optional[date], end_date: Optional[date], max_pages: int, out_path_jsonl: str, seen_path: str, run_meta: dict):
    ensure_dir(os.path.dirname(out_path_jsonl))
    ensure_dir(os.path.dirname(seen_path))
    seen = set()
    if os.path.exists(seen_path):
        try:
            with open(seen_path, "r", encoding="utf-8") as f:
                for line in f:
                    seen.add(line.strip())
        except Exception:
            pass

    base = "https://sousuo.gov.cn/s.htm"
    total_written = 0

    with open(out_path_jsonl, "a", encoding="utf-8") as out_f:
        for p in range(max_pages):
            params = {
                "q": query,
                "t": "govall",
                "n": 20,
                "p": p,
                "sort": "time",
            }
            resp = client.get(base, params=params)
            if resp is None:
                continue
            if resp.status_code != 200:
                logging.warning(f"Search page {p} status {resp.status_code}")
                continue
            html = resp.text
            items = parse_search_items(html)
            if not items:
                logging.info(f"No items parsed on page {p}")
                continue
            for it in items:
                url = it["url"]
                hid = sha256(url)
                if hid in seen:
                    continue
                # time window filter
                dt = None
                if it.get("date"):
                    try:
                        dt = dateparser.parse(it["date"]).date()
                    except Exception:
                        dt = None
                if start_date and dt and dt < start_date:
                    continue
                if end_date and dt and dt > end_date:
                    continue
                doc = {
                    "source": "sousuo.gov.cn",
                    "query": query,
                    "url": url,
                    "title": it.get("title"),
                    "snippet": it.get("snippet"),
                    "pub_date": it.get("date"),
                    "collected_at": now_ts(),
                    "run_id": run_meta.get("run_id"),
                    "fingerprint": hid,
                }
                out_f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                seen.add(hid)
                total_written += 1

    # persist seen
    try:
        with open(seen_path, "w", encoding="utf-8") as f:
            for hid in sorted(seen):
                f.write(hid + "\n")
    except Exception as e:
        logging.error(f"Failed to persist seen set: {e}")

    return total_written


# -----------------------------
# Source 2: World Bank API indicator series (annual)
# -----------------------------

WB_BASE = "https://api.worldbank.org/v2"


def fetch_worldbank_indicator(client: RobotsAwareClient, country: str, indicator: str, start_year: Optional[int], end_year: Optional[int]):
    params = {
        "format": "json",
        "per_page": 20000,
    }
    if start_year and end_year:
        params["date"] = f"{start_year}:{end_year}"
    url = f"{WB_BASE}/country/{country}/indicator/{indicator}"
    resp = client.get(url, params=params)
    if resp is None:
        return {"indicator": indicator, "error": "request_failed", "records": []}
    if resp.status_code != 200:
        return {"indicator": indicator, "error": f"http_{resp.status_code}", "records": []}
    try:
        data = resp.json()
    except Exception as e:
        return {"indicator": indicator, "error": f"json_error:{e}", "records": []}
    if not isinstance(data, list) or len(data) < 2:
        # Often returns {'message': ...} on error
        return {"indicator": indicator, "error": "unexpected_payload", "records": []}
    meta, rows = data[0], data[1]
    records = []
    for r in rows:
        try:
            records.append({
                "country": (r.get("country") or {}).get("value"),
                "countryiso3code": r.get("countryiso3code"),
                "indicator_id": (r.get("indicator") or {}).get("id") or indicator,
                "indicator_name": (r.get("indicator") or {}).get("value"),
                "date": r.get("date"),
                "value": r.get("value"),
                "unit": None,  # not provided in v2 response
                "decimal": r.get("decimal"),
            })
        except Exception:
            continue
    return {"indicator": indicator, "error": None, "records": records}


def collect_worldbank(client: RobotsAwareClient, country: str, indicators: List[str], start_year: Optional[int], end_year: Optional[int], out_csv: str):
    ensure_dir(os.path.dirname(out_csv))
    total = 0
    errors = []
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "country",
            "countryiso3code",
            "indicator_id",
            "indicator_name",
            "date",
            "value",
            "unit",
            "decimal",
        ])
        for ind in indicators:
            res = fetch_worldbank_indicator(client, country, ind, start_year, end_year)
            if res["error"]:
                errors.append({"indicator": ind, "error": res["error"]})
                logging.warning(f"WorldBank indicator {ind} error: {res['error']}")
                continue
            for r in res["records"]:
                w.writerow([
                    r.get("country"),
                    r.get("countryiso3code"),
                    r.get("indicator_id"),
                    r.get("indicator_name"),
                    r.get("date"),
                    r.get("value"),
                    r.get("unit"),
                    r.get("decimal"),
                ])
                total += 1
    return total, errors


# -----------------------------
# Main CLI
# -----------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Collect public data for China's financial 'Five Major Articles' via two sources: gov search (lists) and World Bank (annual indicators).",
    )
    p.add_argument("--outdir", default="data", help="Output directory (default: data)")
    p.add_argument("--logs", default="logs", help="Logs directory (default: logs)")
    p.add_argument("--rpm", type=int, default=12, help="Requests per minute per domain (default: 12)")
    p.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds (default: 15)")
    p.add_argument("--max-pages", type=int, default=3, help="Max pages for gov search (default: 3)")
    p.add_argument("--query", default="金融 五篇 大文章", help="Search query for sousuo.gov.cn")
    p.add_argument("--start-date", default=None, help="Start date YYYY-MM-DD for gov search filter")
    p.add_argument("--end-date", default=None, help="End date YYYY-MM-DD for gov search filter")
    p.add_argument("--wb-country", default="CHN", help="World Bank country ISO3 code (default: CHN)")
    p.add_argument(
        "--wb-indicators",
        default="IP.PAT.RESD,EN.ATM.CO2E.PC,SP.POP.65UP.TO.ZS,IT.NET.USER.ZS",
        help="Comma-separated World Bank indicator codes",
    )
    p.add_argument("--wb-start-year", type=int, default=2000, help="World Bank start year (default: 2000)")
    p.add_argument("--wb-end-year", type=int, default=datetime.now().year, help="World Bank end year (default: current year)")
    p.add_argument("--loglevel", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    ensure_dir(args.outdir)
    ensure_dir(args.logs)

    logging.basicConfig(
        level=getattr(logging, args.loglevel.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    requests_log_path = os.path.join(args.logs, f"requests_{run_id}.csv")

    client = RobotsAwareClient(
        rpm=args.rpm,
        timeout=args.timeout,
        requests_log_path=requests_log_path,
        logger=logging.getLogger("collector"),
    )

    # Parse dates
    start_date = dateparser.parse(args.start_date).date() if args.start_date else None
    end_date = dateparser.parse(args.end_date).date() if args.end_date else None

    run_meta = {
        "run_id": run_id,
        "started_at": now_ts(),
        "params": vars(args),
    }

    # Source 1: gov search
    gov_out = os.path.join(args.outdir, "news", f"gov_search_{run_id}.jsonl")
    seen_path = os.path.join(args.outdir, "news", ".seen_urls.txt")
    logging.info("[Source 1] Crawling sousuo.gov.cn search results ...")
    s1_total = crawl_gov_search(
        client=client,
        query=args.query,
        start_date=start_date,
        end_date=end_date,
        max_pages=args.max_pages,
        out_path_jsonl=gov_out,
        seen_path=seen_path,
        run_meta=run_meta,
    )
    logging.info(f"[Source 1] Wrote {s1_total} items -> {gov_out}")

    # Source 2: World Bank indicators
    wb_indicators = [x.strip() for x in args.wb_indicators.split(",") if x.strip()]
    wb_out = os.path.join(args.outdir, "wb", f"worldbank_{run_id}.csv")
    logging.info("[Source 2] Collecting World Bank indicators ...")
    s2_total, s2_errors = collect_worldbank(
        client=client,
        country=args.wb_country,
        indicators=wb_indicators,
        start_year=args.wb_start_year,
        end_year=args.wb_end_year,
        out_csv=wb_out,
    )
    logging.info(f"[Source 2] Wrote {s2_total} rows -> {wb_out}")
    if s2_errors:
        logging.warning(f"[Source 2] Indicators with errors: {s2_errors}")

    # Manifest
    run_meta.update(
        {
            "finished_at": now_ts(),
            "outputs": {
                "gov_news": gov_out,
                "worldbank": wb_out,
                "requests_log": requests_log_path,
            },
            "counts": {
                "gov_items": s1_total,
                "wb_rows": s2_total,
                "wb_errors": s2_errors,
            },
        }
    )
    runs_dir = os.path.join("runs")
    ensure_dir(runs_dir)
    manifest_path = os.path.join(runs_dir, f"manifest_{run_id}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(run_meta, f, ensure_ascii=False, indent=2)
    logging.info(f"[Done] Manifest -> {manifest_path}")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)
