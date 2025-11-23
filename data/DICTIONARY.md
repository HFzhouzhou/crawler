# 数据字段字典（data/）

本目录下的数据来自两类公开数据源：
- 世界银行开放 API（年频，country=CHN）。
- 国务院搜索（列表页，仅元信息，遵守 robots）。

同时说明采样时间窗与建议采样频率。

## 1) 世界银行指标 CSV（data/wb/worldbank_*.csv）
- 采样时间窗：命令行指定 `--wb-start-year --wb-end-year`（示例：2000-2025）。
- 采样频率：年频；建议每年/季度更新。
- 字段：
  - `country`：国家名称（示例：China）。
  - `countryiso3code`：国家 ISO3（示例：CHN）。
  - `indicator_id`：指标代码（如 IP.PAT.RESD）。
  - `indicator_name`：指标名称（英文）。
  - `year`：年份（原字段 `date` 已转换为 `year`）。
  - `value`：数值（浮点；可能为空）。
  - `unit`：单位（v2 API 通常不含，置空）。
  - `decimal`：小数位建议。

- 指标与主题/单位映射（默认值，可在 bi/app.py 中修改）：
  - IP.PAT.RESD：居民专利申请量（科技金融，单位：件）
  - EN.ATM.CO2E.PC：人均二氧化碳排放（绿色金融，单位：吨/人）
  - SP.POP.65UP.TO.ZS：65 岁及以上人口占比（养老金融，单位：%）
  - IT.NET.USER.ZS：互联网使用率（数字金融，单位：%）

## 2) 国务院搜索 JSONL（data/news/gov_search_*.jsonl）
- 采样时间窗：命令行指定 `--start-date --end-date`（示例：2024-01-01 至 2025-12-31）。
- 采样频率：建议低频（每日/每周定时），仅抓列表页不跟进详情。
- 字段：
  - `source`：固定值 `sousuo.gov.cn`。
  - `query`：检索关键词（示例：“金融 五篇 大文章”）。
  - `url`：列表项链接（不抓取详情）。
  - `title`：标题。
  - `snippet`：摘要/片段（若存在）。
  - `pub_date`：发布日期（尽力解析，可能为空）。
  - `collected_at`：采集时间戳（ISO）。
  - `run_id`：本次运行批次号。
  - `fingerprint`：基于 `url` 的 SHA-256，用于去重。

## 合规与留痕
- robots：若站点 robots 无法获取或 disallow，则放弃访问（日志记录）。
- 频控：每域名 RPM（默认 12），指数退避并尊重 Retry-After。
- 留痕：
  - `logs/requests_<run_id>.csv`：请求日志。
  - `runs/manifest_<run_id>.json`：运行清单（输出路径、计数、参数）。
  - `data/news/.seen_urls.txt`：URL 指纹集合，避免重复写入。
