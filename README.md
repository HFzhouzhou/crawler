# 金融“五篇大文章”公开数据采集脚本

本项目提供一个可直接运行的 Python 爬虫/采集脚本，遵循合规要求（尊重 robots 协议、频率控制、不登录、不破解、不采集个人敏感信息），用于采集与“五篇大文章”（科技金融、绿色金融、普惠金融、养老金融、数字金融）相关的公开数据。

- 数据源A（网页列表）：国务院搜索（sousuo.gov.cn）中与“金融 五篇 大文章”等关键词相关的新闻/政策列表。
- 数据源B（开放接口）：世界银行开放 API 指标时间序列（年频），作为相关主题的可用代理指标。

## 1. 项目结构

- src/collector.py：主采集脚本（含重试、robots 检查、频控、日志、留痕、去重）。
- requirements.txt：依赖清单（含 Streamlit/Plotly/Statsmodels/Kaleido）。
- data/：默认输出目录（运行后生成），含 DICTIONARY.md/DICTIONARY.json（字段字典）。
- logs/：请求日志 CSV（运行后生成）。
- runs/：每次运行的清单 manifest（运行后生成）。
- bi/：交互式仪表盘（Streamlit）与截图导出脚本。
- notebook/：任务三模型 Notebook 与说明。
- crawler/：爬取流程与合规说明（PROCESS.md）。
- license.txt：合规与使用声明（仅使用公开数据）。

## 2. 安装与运行

建议在虚拟环境中运行：

```bash
# 进入项目根目录（含 requirements.txt）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 示例运行（默认两个数据源都会采集）
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
# 示例运行（notebook向）
python3 src/collector.py --wb-country CHN \
  --wb-indicators "IP.PAT.RESD,EN.ATM.CO2E.PC,SP.POP.65UP.TO.ZS,IT.NET.USER.ZS" \
  --wb-start-year 2000 --wb-end-year 2025 --loglevel INFO

可选参数（部分）：
- `--outdir`：输出目录（默认 data）。
- `--logs`：日志目录（默认 logs）。
- `--rpm`：每域名每分钟最大请求数（默认 12，建议 6~30 之间）。
- `--max-pages`：国务院搜索结果翻页数（默认 3）。
- `--start-date`/`--end-date`：新闻/公告样本时间窗（YYYY-MM-DD）。
- `--wb-indicators`：世界银行指标代码，逗号分隔。
- `--wb-start-year`/`--wb-end-year`：指标起止年份（年频）。

## 3. 数据源与字段

### 3.1 数据源A：国务院搜索（网页列表）
- 网址：`https://sousuo.gov.cn/s.htm`（仅抓取搜索列表页，不抓详情页）。
- 样本选择：按关键词检索并按时间排序抓取前 N 页。
- 时间窗：通过 `--start-date` 与 `--end-date` 过滤（基于列表页可解析到的日期）。
- 采样频率：由运行频率决定；建议低频周期性运行（如每日 1 次）。
- 输出文件：`data/news/gov_search_<run_id>.jsonl`
- 每行 JSON 字段：
  - `source`：固定为 `sousuo.gov.cn`。
  - `query`：检索关键词。
  - `url`：结果链接（不跟进抓取）。
  - `title`：标题（列表页解析）。
  - `snippet`：摘要/片段（若存在）。
  - `pub_date`：发布日期（尽力从列表页文本解析；可能为空）。
  - `collected_at`：采集时间戳（ISO）。
  - `run_id`：本次运行批次号。
  - `fingerprint`：基于 `url` 的 SHA-256，用于去重。

说明：列表页结构可能变化，解析器使用若干 CSS 选择器自适应；如未匹配到，可能产生空结果。

### 3.2 数据源B：世界银行开放 API（年频指标）
- 端点：`https://api.worldbank.org/v2/country/{ISO3}/indicator/{INDICATOR}?format=json`
- 时间窗：`--wb-start-year` 至 `--wb-end-year`（年频）。
- 采样频率：年频（API 数据按年度发布）。
- 默认指标（可按需调整）：
  - `IP.PAT.RESD`：居民专利申请量（科技金融的创新活动代理）。
  - `EN.ATM.CO2E.PC`：人均二氧化碳排放（绿色转型约束的宏观代理）。
  - `SP.POP.65UP.TO.ZS`：65 岁及以上人口占比（养老需求相关的人口结构代理）。
  - `IT.NET.USER.ZS`：使用互联网的人口占比（数字化程度代理）。
- 输出文件：`data/wb/worldbank_<run_id>.csv`
- CSV 字段：
  - `country`：国家名称。
  - `countryiso3code`：国家 ISO3（如 CHN）。
  - `indicator_id`：指标代码。
  - `indicator_name`：指标名称（英文）。
  - `date`：年份（字符串）。
  - `value`：数值（可能为空）。
  - `unit`：单位（v2 响应通常无明确单位，置空）。
  - `decimal`：小数位建议。

说明：若个别指标返回异常（如 `unexpected_payload`），说明该指标在当前时间窗或口径存在返回 message/异常结构。可尝试缩短时间窗、稍后重试，或替换为相近指标（例如绿色主题可考虑 `GB.XPD.RSDV.GD.ZS` 等）。

补充：如需覆盖“普惠金融”更针对性的代理指标，可将 `--wb-indicators` 添加例如私人部门信贷占 GDP（`FS.AST.PRVT.GD.ZS`）等宏观可用指标（以官方口径为准）。

## 4. 清洗、去重与留痕

- 去重：
  - 网页列表基于 `url` 计算 `fingerprint`，并在 `data/news/.seen_urls.txt` 维护已抓集合，避免重复写入。
- 日志留痕：
  - 请求日志 `logs/requests_<run_id>.csv` 字段：
    - `ts`、`method`、`url`、`status`、`elapsed_sec`、`error`、`robots_allowed`。
  - 运行清单 `runs/manifest_<run_id>.json`：记录启动/结束时间、参数、输出路径、条目计数与错误清单。
- 异常与失败重试：
  - 内置 `requests` + `urllib3` 重试（429/5xx 指数退避），并尊重 `Retry-After`。
  - 解析错误与不可预期响应会记录 warning/错误信息，不中断全局流程。

此外：若 robots 禁止（如 `sousuo.gov.cn/s.htm`），脚本将跳过该域名（记录 `robots disallow`），输出 0 条符合合规策略。

## 5. 合规与频控

- 严格检查 `robots.txt`：若站点 robots 无法获取或不允许抓取，则放弃访问并做日志记录。
- 频控（每域名）：通过 `--rpm` 限速（默认 12 次/分钟），并在请求之间 sleep。
- 不登录、不绕过站点限制、不采集个人敏感信息；仅抓取公开的列表页与开放 API。

详情见 `license.txt` 与 `crawler/PROCESS.md`。

## 6. 如何扩展

- 扩展网页源：可增加央行/部委公开栏目（注意 robots 与频控），建议仅抓列表页结构化信息。
- 扩展 API 指标：在命令行通过 `--wb-indicators` 添加指标代码（用逗号分隔）。
- 扩展输出：可将 JSONL/CSV 导入数据库或数据湖，保持 `run_id` 以便溯源。

BI 扩展：如提供省级或机构维度数据（CSV），可在仪表盘中增加地图与分组柱形图（当前版本默认不展示）。

## 7. 已知限制

- 国务院搜索列表的页面结构可能调整，导致解析项减少或缺失；必要时需更新解析选择器。
- robots 获取失败时默认停止访问该域名（合规优先），可能导致该源空结果。
- 世界银行个别年份值可能为空或修订，建议按需做缺失值处理与口径核对。

## 8. 任务映射与交付

- 任务一（找能用的数据）：两类来源（网页列表 + 开放 API）、字段字典、去重与留痕、失败重试与合规控制。
- 任务二（BI 做图）：4 张核心图 + KPI，操作说明与下载按钮，支持导出 PNG 截图。
- 任务三（Python 建模）：评分模型 + 简单预测，Notebook 可复用、含特征/权重/方向说明与 MAPE 验证。
