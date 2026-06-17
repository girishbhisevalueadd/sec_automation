"""Charts page - Plotly visualizations of stored financial data."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)
logger.debug("Page load: 4_Charts")

from app_utils import get_chart_colors, get_plotly_template, inject_css  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402

inject_css(st)
render_sidebar()

st.markdown('<h1 style="margin-top:0;">📈 Visual Analysis</h1>', unsafe_allow_html=True)
st.caption("Interactive Plotly charts powered by your stored SEC filings.")

PALETTE = {
    "blue": "#1D6FA4",
    "teal": "#0F9E75",
    "success": "#00C49A",
    "warning": "#F5A623",
    "error": "#E05252",
    "muted": "#8B8FA8",
}


@st.cache_data(ttl=60)
def _tickers() -> list[str]:
    from storage import db_status
    sdf = db_status()
    if sdf is None or sdf.empty:
        return []
    return sorted(sdf["ticker"].unique().tolist())


@st.cache_data(ttl=60)
def _summary(ticker: str) -> dict[str, pd.DataFrame]:
    import processor
    return processor.build_summary_table(ticker, periods=10)


@st.cache_data(ttl=60)
def _ratios(ticker: str) -> pd.DataFrame:
    import processor
    return processor.calculate_ratios(processor.build_summary_table(ticker, periods=10))


def _row(stmt: pd.DataFrame, candidates: list[str]) -> pd.Series:
    if stmt is None or stmt.empty:
        return pd.Series(dtype=float)
    work = stmt.drop(columns=["label"], errors="ignore")
    for cand in candidates:
        for idx in work.index:
            if cand.lower() in str(idx).lower():
                return pd.to_numeric(work.loc[idx], errors="coerce").dropna().sort_index()
    return pd.Series(dtype=float)


def _layout(title: str, height: int = 320) -> dict:
    colors = get_chart_colors(st)
    return dict(
        template=get_plotly_template(st),
        title=dict(text=title, font=dict(size=15, color=colors["font_color"])),
        paper_bgcolor=colors["paper_bgcolor"],
        plot_bgcolor=colors["plot_bgcolor"],
        height=height,
        margin=dict(l=40, r=20, t=40, b=40),
        font=dict(color=colors["font_color"], family="Inter"),
        xaxis=dict(gridcolor=colors["gridcolor"]),
        yaxis=dict(gridcolor=colors["gridcolor"]),
    )


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------
tickers = _tickers()
if not tickers:
    st.info("No data yet. Run the pipeline from the **Run Pipeline** page first.")
    st.stop()

ticker = st.selectbox("Ticker", tickers, key="charts_ticker")
logger.debug("Charts: selected ticker=%s", ticker)
summary = _summary(ticker)
ratios = _ratios(ticker)

inc = summary.get("income", pd.DataFrame())
bal = summary.get("balance", pd.DataFrame())
cfs = summary.get("cashflow", pd.DataFrame())

revenue = _row(inc, ["Revenue", "Total revenue"])
net_income = _row(inc, ["Net income"])
gross = _row(inc, ["Gross margin", "Gross profit"])
op_inc = _row(inc, ["Operating income"])

cash = _row(bal, ["Cash and cash equivalents"])
debt_long = _row(bal, ["Long-term debt", "LongTermDebt"])
debt_short = _row(bal, ["Current portion of long-term debt", "Short-term"])
equity = _row(bal, ["Total stockholders' equity", "Stockholders' equity"])

ocf = _row(cfs, ["Net cash from operations"])
icf = _row(cfs, ["Net cash used in investing", "investing activities"])
fcf = _row(cfs, ["Net cash used in financing", "financing activities"])
capex = _row(cfs, ["Additions to property", "Capital expenditures"])


# ---------------------------------------------------------------------------
# Chart grid (3 rows x 2 cols)
# ---------------------------------------------------------------------------
row1c1, row1c2 = st.columns(2)

with row1c1:
    fig = go.Figure()
    if not revenue.empty:
        fig.add_trace(go.Bar(name="Revenue", x=list(revenue.index), y=revenue.values, marker_color=PALETTE["blue"]))
    if not net_income.empty:
        fig.add_trace(go.Bar(name="Net Income", x=list(net_income.index), y=net_income.values, marker_color=PALETTE["teal"]))
    fig.update_layout(**_layout("Revenue & Net Income"), barmode="group", legend=dict(orientation="h", y=-0.18))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

with row1c2:
    fig = go.Figure()
    if not revenue.empty and not gross.empty:
        gross_m = (gross.reindex(revenue.index) / revenue * 100).dropna()
        fig.add_trace(go.Scatter(x=list(gross_m.index), y=gross_m.values, mode="lines+markers", name="Gross %", line=dict(color=PALETTE["success"], width=3)))
    if not revenue.empty and not op_inc.empty:
        op_m = (op_inc.reindex(revenue.index) / revenue * 100).dropna()
        fig.add_trace(go.Scatter(x=list(op_m.index), y=op_m.values, mode="lines+markers", name="Operating %", line=dict(color=PALETTE["blue"], width=3)))
    if not revenue.empty and not net_income.empty:
        ni_m = (net_income.reindex(revenue.index) / revenue * 100).dropna()
        fig.add_trace(go.Scatter(x=list(ni_m.index), y=ni_m.values, mode="lines+markers", name="Net %", line=dict(color=PALETTE["warning"], width=3)))
    fig.update_layout(**_layout("Margin Trends (%)"), legend=dict(orientation="h", y=-0.18))
    fig.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

row2c1, row2c2 = st.columns(2)

with row2c1:
    fig = go.Figure()
    for series, name, color in [(ocf, "Operating", PALETTE["success"]), (icf, "Investing", PALETTE["warning"]), (fcf, "Financing", PALETTE["error"])]:
        if not series.empty:
            fig.add_trace(go.Bar(name=name, x=list(series.index), y=series.values, marker_color=color))
    fig.update_layout(**_layout("Cash Flow Components"), barmode="relative", legend=dict(orientation="h", y=-0.18))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

with row2c2:
    fig = go.Figure()
    total_debt = debt_long.add(debt_short, fill_value=0)
    if not total_debt.empty:
        fig.add_trace(go.Bar(name="Total Debt", x=list(total_debt.index), y=total_debt.values, marker_color=PALETTE["error"]))
    if not equity.empty:
        fig.add_trace(go.Bar(name="Equity", x=list(equity.index), y=equity.values, marker_color=PALETTE["blue"]))
    fig.update_layout(**_layout("Debt vs Equity"), barmode="stack", legend=dict(orientation="h", y=-0.18))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

row3c1, row3c2 = st.columns(2)

with row3c1:
    if ratios is None or ratios.empty:
        st.info("No ratios available for radar chart.")
    else:
        latest_col = ratios.columns[0]
        radar_metrics = [
            ("Gross Margin (%)", 80),
            ("Operating Margin (%)", 50),
            ("Net Margin (%)", 40),
            ("Current Ratio", 3),
            ("Return on Equity (%)", 60),
            ("Return on Assets (%)", 30),
        ]
        cats, vals = [], []
        for name, scale in radar_metrics:
            if name in ratios.index:
                v = ratios.loc[name, latest_col]
                if pd.notna(v):
                    cats.append(name.replace(" (%)", ""))
                    vals.append(min(float(v), scale * 1.3))
        if cats:
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(r=vals + [vals[0]], theta=cats + [cats[0]], fill="toself", line=dict(color=PALETTE["teal"], width=2), fillcolor="rgba(15,158,117,0.30)"))
            _c = get_chart_colors(st)
            fig.update_layout(**_layout(f"Ratios Radar ({latest_col})"), polar=dict(bgcolor=_c["plot_bgcolor"], radialaxis=dict(gridcolor=_c["gridcolor"])))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
        else:
            st.info("Not enough ratio values to render radar.")

with row3c2:
    st.markdown('<div class="section-header" style="margin-top:0; font-size:15px;">Peer Revenue Comparison</div>', unsafe_allow_html=True)
    others = st.multiselect("Compare with", [t for t in tickers if t != ticker], key="charts_peers", max_selections=4)
    peers = [ticker] + list(others)
    fig = go.Figure()
    colors = [PALETTE["blue"], PALETTE["teal"], PALETTE["warning"], PALETTE["error"], PALETTE["success"]]
    for i, t in enumerate(peers):
        s = _row(_summary(t).get("income", pd.DataFrame()), ["Revenue", "Total revenue"])
        if s.empty:
            continue
        fig.add_trace(go.Scatter(x=list(s.index), y=s.values, mode="lines+markers", name=t, line=dict(color=colors[i % len(colors)], width=3)))
    fig.update_layout(**_layout("Revenue Trends"), legend=dict(orientation="h", y=-0.18))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})

# ---------------------------------------------------------------------------
# Multi-company overlay
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Multi-Company Overlay</div>', unsafe_allow_html=True)
overlay = st.multiselect(
    "Pick 2-4 tickers to overlay revenue trends",
    tickers,
    default=tickers[: min(2, len(tickers))],
    max_selections=4,
    key="charts_overlay",
)
if overlay:
    fig = go.Figure()
    for i, t in enumerate(overlay):
        s = _row(_summary(t).get("income", pd.DataFrame()), ["Revenue", "Total revenue"])
        if s.empty:
            continue
        fig.add_trace(go.Scatter(x=list(s.index), y=s.values, mode="lines+markers", name=t,
                                 line=dict(width=3, color=[PALETTE["blue"], PALETTE["teal"], PALETTE["warning"], PALETTE["error"]][i % 4])))
    fig.update_layout(**_layout("Revenue ($)", height=380), legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": True, "displaylogo": False})
