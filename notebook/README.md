# Notebook 说明

本目录包含用于任务三（Python 建模与验证）的可复用 Notebook。

- model_scoring.ipynb：
  - 读取最新运行的采集产物（优先 runs/manifest_*.json）。
  - 将世界银行年度指标转为宽表，完成标准化与加权评分（可调整方向与权重）。
  - 选择一个指标进行时间序列预测（ETS/Holt-Winters），并输出基本验证指标（MAPE）。
  - 将评分与预测结果保存到 data/model/ 下，便于复用。

运行环境：
- Python 3.10+
- pip install -r requirements.txt （包含 pandas、numpy、statsmodels、plotly 等）

操作步骤（务必按序执行）：
1. 先在项目根目录运行采集脚本，确保生成 `data/wb/worldbank_*.csv`：
   ```bash
   python3 src/collector.py --wb-country CHN \
     --wb-indicators "IP.PAT.RESD,EN.ATM.CO2E.PC,SP.POP.65UP.TO.ZS,IT.NET.USER.ZS" \
     --wb-start-year 2000 --wb-end-year 2025 --loglevel INFO
   ```
2. 打开并运行 `model_scoring.ipynb`（建议“Restart & Run All”）：
   - Notebook 会自动优先读取 `runs/manifest_*.json` 中的路径，未命中则回退到 `data/wb/worldbank_*.csv` 中最新文件。
3. 若需要自定义：
   - 修改 `DEFAULT_INDICATORS`、`DIRECTION`（+1 越大越好；-1 越小越好；0 不纳入）、`WEIGHTS`。
   - 预测目标在最后一个单元的 `target` 中设置（默认 `IT.NET.USER.ZS`）。

常见报错与修复：
- FileNotFoundError: “未找到世界银行CSV”
  - 原因：尚未生成 `data/wb/worldbank_*.csv`，或 Notebook 没有正确定位到项目根目录。
  - 处理：
    1) 先运行采集脚本生成 CSV（见步骤1）。
    2) 若仍报错，在 Notebook 顶部新建单元并设置项目根路径，然后“Restart & Run All”：
       ```python
       %env PROJECT_ROOT=/Users/puppymie/Desktop/crawler
       ```
- AssertionError: “可用于预测的数据点太少”
  - 原因：所选指标有效年份少于 6 个点，无法做基本验证切分。
  - 处理：
    - 改用数据更全的指标（如 `IT.NET.USER.ZS`），或缩小验证切分（修改 `split_n`），或更换到年数更长的时间窗重新采集。
- Statsmodels 报错（拟合失败）
  - 处理：
    - 检查数据是否全为缺失或为常数序列；
    - 将 `trend='add'` 调整为 `'mul'` 或去掉趋势项；或换用 `target`。

输出文件：
- data/model/wb_wide.csv（指标宽表）
- data/model/scoring_by_year.csv（年度评分：0-100）
- data/model/forecast_<target>.csv（简单预测）
- data/model/metrics.json（验证指标，如 MAPE）
