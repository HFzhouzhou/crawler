# BI 仪表盘（Streamlit + Plotly）

该仪表盘读取采集产物（世界银行 CSV 与国务院搜索 JSONL），展示 4 个核心可视化与关键指标卡，满足“对比/趋势清晰、标注规范、可交互”的要求。

## 运行

```bash
# 建议在已激活的虚拟环境中
pip install -r requirements.txt
streamlit run bi/app.py
```

默认会自动读取 `runs/manifest_*.json` 中最近一次运行产出的文件；如未找到，将回退到 `data/wb/*.csv` 与 `data/news/*.jsonl` 中最新文件。你也可以在左侧栏手动指定路径。

## 图表清单（4 图 + KPI）
- 指标卡（KPI）：最近一年数值和同比变化（%）。
- 趋势折线图：多指标同图对比趋势，支持“指数(基期=100)”归一化以便跨指标对比。
- 年度对比柱形图：最近一年不同指标水平对比（数值或指数）。
- 同比变化柱形图：最近一年各指标同比增减（%）。
- 新闻月度折线：国务院搜索新闻月度频次（可按关键词与时间窗筛选）。

## 交互说明
- 左侧选择年份范围与指标，支持最多 4–6 个指标以保持可读性。
- 勾选“指数(基期=100)”以将不同单位的指标归一化，便于对比相对变化。
- 图表悬停查看具体数值；指标卡显示最近一年 YoY。
- 新闻模块支持关键词与时间窗筛选，点击表格链接可查看原文。
- 侧栏有“指标定义与口径”气泡，说明指标中文名、单位与来源口径。

## 数据口径与说明
- 世界银行数据为年频；不同指标单位不同，开启“指数(基期=100)”更直观。
- 国务院搜索仅抓列表页元信息（标题/摘要/链接/日期），用于舆情趋势示例。
- 若需地区/机构对比，请扩展数据源为省级或机构级口径后，新增地图/分组柱形图。

## 可选：地区/机构图表（分组柱形/地图）
- 侧栏可填写两项以启用：
  - “地区或机构CSV路径”：至少包含列 `region` 或 `province` 与 `value`；可选 `year`、`indicator`。
  - “中国GeoJSON路径（可选）”：若提供，将绘制分省 Choropleth；要求属性包含 `properties.name` 与 CSV 的地区名称一致。
- 多指标的地区 CSV 可生成“分组柱形图”，单指标可生成“普通柱形图”。

## 导出静态截图（PNG）
便于放入 DataEase 或报告：
```bash
python bi/export_charts.py
```
输出保存在 `bi/screenshots/`：
- trend.png（趋势折线）
- compare_latest.png（最近一年对比）
- yoy_latest.png（最近一年同比）

## 常见问题（FAQ）
- `unexpected_payload`：某些世界银行指标在当前时间窗返回 message/异常结构，可缩短时间窗、稍后重试，或更换相近指标。
- `use_container_width` 弃用提示：本应用已改为 `width='stretch'`；如仍见提示，升级 Streamlit 或刷新页面。
- 关闭 Streamlit 遥测（可选）：
  - 新建 `~/.streamlit/config.toml`：
    ```toml
    [browser]
    gatherUsageStats = false
    ```
