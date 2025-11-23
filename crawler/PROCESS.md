# 爬取流程说明（crawler/PROCESS.md）

本项目的采集由 `src/collector.py` 完成，来源包括：
- A. 国务院搜索（sousuo.gov.cn，列表页）
- B. 世界银行开放 API（api.worldbank.org/v2，CHN 年度指标）

## 环境
- Python 3.10+
- 依赖：见 `requirements.txt`

## 运行
```bash
python3 src/collector.py \
  --query "金融 五篇 大文章" \
  --max-pages 5 \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --rpm 10 \
  --wb-country CHN \
  --wb-indicators "IP.PAT.RESD,EN.ATM.CO2E.PC,SP.POP.65UP.TO.ZS,IT.NET.USER.ZS" \
  --wb-start-year 2000 \
  --wb-end-year 2025 \
  --loglevel INFO
```

## 产物
- `data/wb/worldbank_<run_id>.csv`：世界银行指标
- `data/news/gov_search_<run_id>.jsonl`：国务院搜索列表（若 robots 允许）
- `logs/requests_<run_id>.csv`：请求留痕
- `runs/manifest_<run_id>.json`：运行清单（参数、产物路径、计数）

## 异常与重试
- 统一封装 `RobotsAwareClient`：
  - 先读取 robots.txt，若 disallow 或无法获取则跳过该域名并记录。
  - 每域名 RPM 限速（默认 12），请求间隔均匀分配。
  - `urllib3.Retry`：对 429/5xx 指数退避并尊重 Retry-After。
  - 统一记录请求日志（方法、URL、状态码、耗时、错误）。
- HTML 解析：使用多选择器兜底；若结构变动会记录 warning，不中断流程。
- 世界银行 API：若返回 `message` 或结构异常，记录为 `unexpected_payload`，该指标跳过（仍输出其它指标）。

## 合规
- 不登录、不绕过限制、不采集个人敏感信息。
- 严格遵守 robots 与频率限制。

## 定时策略建议
- 世界银行：年频（可季度/年度更新）。
- 网页列表：低频（日/周定时），仅抓列表，不抓详情。

## 快速排障
- `robots disallow`：该域名禁止抓取，需更换来源或改为 API/文件下载渠道。
- `unexpected_payload`：检查指标代码或缩短时间窗；或更换为替代指标（如 R&D 占比 `GB.XPD.RSDV.GD.ZS`）。
- 代理/网络慢：可调大 `--timeout`，但仍受 robots 与站点速率限制约束。
