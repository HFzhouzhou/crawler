#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from glob import glob
from datetime import datetime

import pandas as pd
import plotly.express as px

PLOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")


def _find_latest(pattern: str):
    files = glob(pattern)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def _from_manifest():
    runs = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runs")
    m = _find_latest(os.path.join(runs, "manifest_*.json"))
    if not m:
        return None, None
    with open(m, "r", encoding="utf-8") as f:
        man = json.load(f)
    outs = man.get("outputs", {})
    return outs.get("worldbank"), outs.get("gov_news")


def load_worldbank(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_numeric(df["date"], errors="coerce")
    df = df.rename(columns={"date": "year"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    if "countryiso3code" in df.columns:
        df = df[df["countryiso3code"] == "CHN"].copy()
    return df


def export_all():
    os.makedirs(PLOT_DIR, exist_ok=True)
    wb_path, news_path = _from_manifest()
    if wb_path is None:
        wb_path = _find_latest(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "wb", "worldbank_*.csv"))
    if wb_path is None:
        raise SystemExit("No World Bank CSV found")

    df = load_worldbank(wb_path)
    latest = int(df["year"].max())

    fig1 = px.line(df, x="year", y="value", color="indicator_id", markers=True, title="指标时间序列")
    fig1.write_image(os.path.join(PLOT_DIR, "trend.png"), scale=2, width=1200, height=600)

    bar_df = df[df["year"] == latest]
    fig2 = px.bar(bar_df, x="indicator_id", y="value", color="indicator_id", text_auto=".2f", title=f"{latest}年指标水平")
    fig2.write_image(os.path.join(PLOT_DIR, "compare_latest.png"), scale=2, width=1000, height=600)

    df = df.sort_values(["indicator_id", "year"]).copy()
    df["yoy_pct"] = df.groupby("indicator_id")["value"].pct_change() * 100.0
    yoy = df[df["year"] == latest]
    fig3 = px.bar(yoy, x="indicator_id", y="yoy_pct", color="indicator_id", text_auto=".2f", title=f"{latest}年同比(%)")
    fig3.write_image(os.path.join(PLOT_DIR, "yoy_latest.png"), scale=2, width=1000, height=600)

    print("Saved charts to:", PLOT_DIR)


if __name__ == "__main__":
    export_all()
