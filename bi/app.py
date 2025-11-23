#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import io
from glob import glob
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.io as pio
from typing import Optional, Tuple

APP_TITLE = "金融“五篇大文章”公开数据仪表盘"
APP_DESC = (
    "来自国务院搜索（列表）与世界银行开放API的示例性可视化。"
    "左侧可调整指标与时间范围；图表可悬停查看数值。"
)

DEFAULT_INDICATORS = [
    "IP.PAT.RESD",       # 居民专利申请量（科技-创新活动代理）
    "EN.ATM.CO2E.PC",    # 人均二氧化碳排放（绿色）
    "SP.POP.65UP.TO.ZS", # 65岁及以上人口占比（养老）
    "IT.NET.USER.ZS",    # 互联网使用率（数字）
]

INDICATOR_TOPIC = {
    "IP.PAT.RESD": "科技金融",
    "EN.ATM.CO2E.PC": "绿色金融",
    "SP.POP.65UP.TO.ZS": "养老金融",
    "IT.NET.USER.ZS": "数字金融",
}

INDICATOR_DEF = {
    "IP.PAT.RESD": "居民专利申请量：按申请人居住地计量的专利申请件数（年）。世界银行转自WIPO口径。",
    "EN.ATM.CO2E.PC": "人均二氧化碳排放：CO₂排放总量/人口（吨/人，年）。来源：世界银行环境数据库。",
    "SP.POP.65UP.TO.ZS": "65岁及以上人口占比：65+人口/总人口（%）。来源：世界银行人口数据库。",
    "IT.NET.USER.ZS": "互联网使用率：使用互联网的人口占比（%）。来源：ITU/世界银行。",
}

INDICATOR_CN_NAME = {
    "IP.PAT.RESD": "居民专利申请量",
    "EN.ATM.CO2E.PC": "人均二氧化碳排放",
    "SP.POP.65UP.TO.ZS": "65岁及以上人口占比",
    "IT.NET.USER.ZS": "互联网使用率",
}

INDICATOR_UNIT = {
    "IP.PAT.RESD": "件",
    "EN.ATM.CO2E.PC": "吨/人",
    "SP.POP.65UP.TO.ZS": "%",
    "IT.NET.USER.ZS": "%",
}

COLOR_MAP_ID = {
    "IP.PAT.RESD": "#1f77b4",
    "EN.ATM.CO2E.PC": "#2ca02c",
    "SP.POP.65UP.TO.ZS": "#d62728",
    "IT.NET.USER.ZS": "#9467bd",
}


def _find_latest(path_pattern: str) -> Optional[str]:
    files = glob(path_pattern)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def _find_from_manifest() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    runs_dir = os.path.join(os.getcwd(), "runs")
    if not os.path.isdir(runs_dir):
        return None, None, None
    manifest = _find_latest(os.path.join(runs_dir, "manifest_*.json"))
    if not manifest:
        return None, None, None
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            m = json.load(f)
        outs = (m.get("outputs") or {})
        return outs.get("worldbank"), outs.get("gov_news"), manifest
    except Exception:
        return None, None, None


def load_worldbank(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Ensure types
    df["date"] = pd.to_numeric(df["date"], errors="coerce")
    df = df.rename(columns={"date": "year"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    # Keep CHN only if present
    if "countryiso3code" in df.columns:
        chn = df[df["countryiso3code"] == "CHN"].copy()
        if not chn.empty:
            df = chn
    df["indicator_cn"] = df["indicator_id"].map(INDICATOR_CN_NAME).fillna(df["indicator_id"])
    df["topic"] = df["indicator_id"].map(INDICATOR_TOPIC).fillna("指标")
    df["单位"] = df["indicator_id"].map(INDICATOR_UNIT).fillna("")
    return df


def make_index(df: pd.DataFrame, base_year: int) -> pd.DataFrame:
    # Compute指数(基期=100)，逐指标独立归一
    df = df.copy()
    df.sort_values(["indicator_id", "year"], inplace=True)
    idx_vals = []
    for ind, g in df.groupby("indicator_id"):
        g = g.copy()
        base = g.loc[g["year"] == base_year, "value"]
        base_val = np.nan
        if not base.empty:
            base_val = base.iloc[0]
        g["index"] = np.where(
            pd.notna(base_val) & (base_val != 0), g["value"] / base_val * 100.0, np.nan
        )
        idx_vals.append(g)
    return pd.concat(idx_vals, axis=0, ignore_index=True)


def yoy_change(df: pd.DataFrame) -> pd.DataFrame:
    # 逐指标计算同比%
    df = df.sort_values(["indicator_id", "year"]).copy()
    df["yoy_pct"] = df.groupby("indicator_id")["value"].pct_change(fill_method=None) * 100.0
    df["indicator_cn"] = df["indicator_id"].map(INDICATOR_CN_NAME).fillna(df["indicator_id"])
    return df


def load_news(jsonl_path: str) -> pd.DataFrame:
    rows = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if not rows:
        return pd.DataFrame(columns=["pub_date", "title", "url", "snippet"])  
    df = pd.DataFrame(rows)
    # Parse dates
    if "pub_date" in df.columns:
        df["pub_date"] = pd.to_datetime(df["pub_date"], errors="coerce")
    else:
        df["pub_date"] = pd.NaT
    return df


def news_monthly(df_news: pd.DataFrame) -> pd.DataFrame:
    dfn = df_news.copy()
    dfn = dfn.dropna(subset=["pub_date"]) if "pub_date" in dfn.columns else dfn
    if dfn.empty:
        return pd.DataFrame({"month": [], "count": []})
    dfn["month"] = dfn["pub_date"].dt.to_period("M").dt.to_timestamp()
    agg = dfn.groupby("month").size().reset_index(name="count")
    return agg


# ---------------------- Streamlit App ----------------------

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")
pio.templates.default = "plotly_white"
PLOT_CONFIG = {"locale": "zh-CN", "displaylogo": False}
st.title(APP_TITLE)
st.caption(APP_DESC)

# Load paths (manifest first, then fallbacks)
wb_path, news_path, manifest_path = _find_from_manifest()
wb_fallback = _find_latest(os.path.join("data", "wb", "worldbank_*.csv"))
news_fallback = _find_latest(os.path.join("data", "news", "gov_search_*.jsonl"))
if wb_path is None:
    wb_path = wb_fallback
if news_path is None:
    news_path = news_fallback

with st.sidebar:
    st.header("数据选择")
    if manifest_path:
        st.success(f"已加载清单: {os.path.basename(manifest_path)}")
    else:
        st.info("未找到运行清单，已尝试使用 data/ 下最新文件")
    wb_path = st.text_input("世界银行 CSV 路径", value=wb_path or "")
    news_path = st.text_input("国务院搜索 JSONL 路径", value=news_path or "")

# Guard
if not wb_path or not os.path.exists(wb_path):
    st.warning("未找到世界银行CSV，请先运行采集脚本生成数据。")
    st.stop()

# Load data
wb = load_worldbank(wb_path)
if wb.empty:
    st.warning("世界银行数据为空。")
    st.stop()

news = None
if news_path and os.path.exists(news_path):
    news = load_news(news_path)

# Sidebar controls
with st.sidebar:
    st.subheader("指标与时间")
    year_min, year_max = int(wb["year"].min()), int(wb["year"].max())
    years = st.slider("年份范围", min_value=year_min, max_value=year_max, value=(max(year_min, year_max-10), year_max))

    all_inds = sorted(wb["indicator_id"].dropna().unique().tolist())
    default_inds = [i for i in DEFAULT_INDICATORS if i in all_inds] or all_inds[:4]
    sel_inds = st.multiselect(
        "选择指标（最多 4-6 个以保证可读）",
        options=all_inds,
        default=default_inds,
        format_func=lambda x: f"{INDICATOR_CN_NAME.get(x, x)}（{x}）",
        help="将鼠标悬停右侧问号查看本控件说明；下方可展开查看各指标定义与口径。",
    )

    normalize = st.toggle("归一化为指数(基期=100)", value=True, help="按每个指标的基期值归一，便于跨指标对比")
    base_year = st.number_input("指数基期(年)", value=years[0], min_value=year_min, max_value=year_max)

    st.subheader("新闻筛选")
    kw = st.text_input("新闻关键词筛选", value="")
    if news is not None and news["pub_date"].notna().any():
        mind, maxd = news["pub_date"].min().date(), news["pub_date"].max().date()
        news_range = st.date_input("新闻时间窗", value=(mind, maxd))
    else:
        news_range = None

with st.sidebar:
    pop = st.popover("指标定义与口径")
    with pop:
        if 'sel_inds' in locals() and sel_inds:
            for ind in sel_inds:
                cn = INDICATOR_CN_NAME.get(ind, ind)
                unit = INDICATOR_UNIT.get(ind, "")
                desc = INDICATOR_DEF.get(ind, "暂无定义")
                st.markdown(f"**{cn}（{ind}）** · 单位：{unit if unit else '—'}\n\n{desc}")
        else:
            st.info("请先在上方选择指标")

# Filter WB data
wb_sel = wb[(wb["indicator_id"].isin(sel_inds)) & (wb["year"].between(years[0], years[1]))].copy()
wb_yoy = yoy_change(wb_sel)

if normalize:
    wb_idx = make_index(wb_sel, base_year)
    y_col = "index"
    y_title = "指数(基期=100)"
else:
    wb_idx = wb_sel.copy()
    y_col = "value"
    y_title = "数值（单位随指标而异，建议使用“指数(基期=100)”进行对比）"

wb_idx["指标"] = wb_idx["indicator_id"].map(INDICATOR_CN_NAME).fillna(wb_idx["indicator_id"])
wb_yoy["指标"] = wb_yoy["indicator_id"].map(INDICATOR_CN_NAME).fillna(wb_yoy["indicator_id"])
color_map_cn = {wb_idx.loc[wb_idx["indicator_id"]==k, "指标"].iloc[0]: v for k, v in COLOR_MAP_ID.items() if (wb_idx["indicator_id"]==k).any()}
wb_idx["单位"] = wb_idx["indicator_id"].map(INDICATOR_UNIT).fillna("")

# KPI summary
latest_year = int(wb_idx["year"].max())
wb_latest = wb_sel[wb_sel["year"] == latest_year]

kpi_cols = st.columns(4)
for i, ind in enumerate(sel_inds[:4]):
    sub = wb_latest[wb_latest["indicator_id"] == ind]
    v = sub["value"].iloc[0] if not sub.empty else np.nan
    yoy_sub = wb_yoy[(wb_yoy["indicator_id"] == ind) & (wb_yoy["year"] == latest_year)]
    yoyp = yoy_sub["yoy_pct"].iloc[0] if not yoy_sub.empty else np.nan
    topic = INDICATOR_TOPIC.get(ind, "指标")
    cn = INDICATOR_CN_NAME.get(ind, ind)
    unit = INDICATOR_UNIT.get(ind, "")
    if pd.notna(v):
        if unit == "%":
            v_str = f"{v:.2f}%"
        else:
            v_str = f"{v:,.2f}{unit}"
    else:
        v_str = "-"
    with kpi_cols[i % 4]:
        st.metric(label=f"{topic} · {cn}（{latest_year}）", value=v_str, delta=(f"{yoyp:+.2f}%" if pd.notna(yoyp) else None), delta_color="normal")

# Chart 1: Trend lines
fig1 = px.line(
    wb_idx,
    x="year",
    y=y_col,
    color="指标",
    color_discrete_map=color_map_cn,
    hover_data={"指标": True, "value": ":,.2f", "year": True},
    markers=True,
)
fig1.update_layout(yaxis_title=y_title, xaxis_title="年份", legend_title="指标", font=dict(family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Arial", size=14), margin=dict(t=50, b=40, l=40, r=20))
fig1.update_xaxes(dtick=1)
st.subheader("趋势：指标时间序列")
st.plotly_chart(fig1, width="stretch", config=PLOT_CONFIG)

# Chart 2: Latest year comparison (bar)
bar_df = wb_idx[wb_idx["year"] == latest_year].copy()
fig2 = px.bar(bar_df, x="指标", y=y_col, color="指标", text_auto=".2f", color_discrete_map=color_map_cn)
fig2.update_layout(yaxis_title=y_title, xaxis_title="指标", showlegend=False, font=dict(family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Arial", size=14), margin=dict(t=40, b=40, l=40, r=20))
st.subheader(f"对比：{latest_year} 年指标水平")
st.plotly_chart(fig2, width="stretch", config=PLOT_CONFIG)

# Chart 3: YoY change percentage (bar)
yoy_latest = wb_yoy[wb_yoy["year"] == latest_year].copy()
fig3 = px.bar(yoy_latest, x="指标", y="yoy_pct", color="指标", text_auto=".2f", color_discrete_map=color_map_cn)
fig3.update_layout(yaxis_title="同比变化(%)", xaxis_title="指标", showlegend=False, font=dict(family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Arial", size=14), margin=dict(t=40, b=40, l=40, r=20))
fig3.update_yaxes(ticksuffix="%")
st.subheader(f"变化：{latest_year} 年同比(%)")
st.plotly_chart(fig3, width="stretch", config=PLOT_CONFIG)

st.subheader("舆情：国务院搜索新闻月度频次")
if news is not None and not news.empty and news["pub_date"].notna().any():
    dn = news.copy()
    if kw:
        mask_kw = dn[["title", "snippet"]].fillna("").apply(lambda s: s.str.contains(kw, case=False, regex=False))
        mask = mask_kw.any(axis=1)
        dn = dn[mask]
    if news_range is not None and isinstance(news_range, (list, tuple)) and len(news_range) == 2:
        dn = dn[(dn["pub_date"] >= pd.to_datetime(news_range[0])) & (dn["pub_date"] <= pd.to_datetime(news_range[1]))]
    mn = news_monthly(dn)
    if not mn.empty:
        fig4 = px.line(mn, x="month", y="count", markers=True)
        fig4.update_layout(yaxis_title="条数(篇)", xaxis_title="月份", font=dict(family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Arial", size=14), margin=dict(t=40, b=40, l=40, r=20))
        st.plotly_chart(fig4, width="stretch", config=PLOT_CONFIG)
    else:
        st.info("筛选条件下无新闻数据。")
else:
    st.info("未加载或无法解析新闻列表数据。")

# Data tables
with st.expander("查看数据表(可下载)"):
    st.write("世界银行数据（筛选后）：")
    st.dataframe(wb_sel.sort_values(["indicator_id", "year"]))
    csv_buf = io.StringIO()
    wb_sel.to_csv(csv_buf, index=False)
    st.download_button("下载筛选后的世界银行数据CSV", data=csv_buf.getvalue(), file_name=f"worldbank_filtered_{latest_year}.csv", mime="text/csv")
    if news is not None and not news.empty:
        st.write("新闻列表（部分预览）：")
        news_preview = news[["pub_date", "title", "url"]].sort_values("pub_date", ascending=False).head(50)
        st.dataframe(
            news_preview,
            column_config={
                "url": st.column_config.LinkColumn("原文链接"),
                "pub_date": st.column_config.DatetimeColumn("发布时间"),
                "title": st.column_config.TextColumn("标题"),
            },
            hide_index=True,
            use_container_width=True,
        )
        news_buf = io.StringIO()
        news.to_csv(news_buf, index=False)
        st.download_button("下载全部新闻CSV", data=news_buf.getvalue(), file_name="gov_news_all.csv", mime="text/csv")

def load_region_csv(path: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    cols = {c.lower(): c for c in df.columns}
    region_col = cols.get("region") or cols.get("province") or cols.get("地区") or cols.get("省份")
    year_col = cols.get("year") or cols.get("年份")
    value_col = cols.get("value") or cols.get("数值")
    if not region_col or not value_col:
        return None
    out = df.rename(columns={region_col: "region", value_col: "value"}).copy()
    if year_col:
        out = out.rename(columns={year_col: "year"})
    else:
        out["year"] = None
    if "indicator_id" not in out.columns and "indicator" in df.columns:
        out = out.rename(columns={"indicator": "indicator_id"})
    return out

with st.sidebar:
    st.subheader("地区/机构数据（可选）")
    region_csv_path = st.text_input("地区或机构CSV路径", value="", help="需包含列：region/province，value，可选：year、indicator")
    geojson_path = st.text_input("中国GeoJSON路径（可选）", value="", help="若提供，将绘制分省地图；要求属性包含省级名称 name")

reg = None
reg_latest = None
figr = None
figm = None
if region_csv_path:
    reg = load_region_csv(region_csv_path)
    if reg is not None and not reg.empty:
        if reg["year"].notna().any():
            latest_reg_year = reg["year"].dropna().astype(str).max()
            reg_latest = reg[reg["year"].astype(str) == latest_reg_year].copy()
        else:
            reg_latest = reg.copy()
        if "indicator_id" in reg_latest.columns:
            inds_reg = sorted(reg_latest["indicator_id"].dropna().unique().tolist())
            ind_sel = st.multiselect("地区数据：选择指标", inds_reg, default=inds_reg[:1], key="ind_sel_region")
            reg_plot = reg_latest[reg_latest["indicator_id"].isin(ind_sel)].copy()
            figr = px.bar(reg_plot, x="region", y="value", color="indicator_id", barmode="group", text_auto=".2f")
        else:
            figr = px.bar(reg_latest, x="region", y="value", text_auto=".2f")
        figr.update_layout(xaxis_title="地区/机构", yaxis_title="数值", font=dict(family="PingFang SC, Microsoft YaHei, Noto Sans CJK SC, Arial", size=14))
        if geojson_path and os.path.exists(geojson_path):
            try:
                import json as _json
                with open(geojson_path, "r", encoding="utf-8") as f:
                    gj = _json.load(f)
                figm = px.choropleth(reg_latest, geojson=gj, featureidkey="properties.name", locations="region", color="value", color_continuous_scale="Blues")
                figm.update_geos(fitbounds="locations", visible=False)
                figm.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            except Exception:
                figm = None

# Footer instructions
st.markdown("""
- 操作提示：
  - 左侧选择年份范围与指标；可切换指数归一化以便跨指标对比。
  - 悬停查看具体数值；上方指标卡显示最近一年数值及同比。
  - 新闻模块可输入关键词并限定时间窗。
- 注：不同指标单位不同，建议开启“指数(基期=100)”观察相对变化趋势。
""")
