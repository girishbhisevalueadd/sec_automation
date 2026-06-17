"""Financials page - interactive browser for stored statements + ratios."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)
logger.debug("Page load: 3_Financials")

from app_utils import inject_css  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402
from components.metric_cards import render_metric_cards  # noqa: E402

inject_css(st)
render_sidebar()

st.markdown('<h1 style="margin-top:0;">📋 Financial Statements</h1>', unsafe_allow_html=True)
st.caption("Browse stored statements with comparison and Indian/standard formatting.")


# ---------------------------------------------------------------------------
# Cached data accessors
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Top controls
# ---------------------------------------------------------------------------
tickers = _tickers()
if not tickers:
    st.info("No filings stored yet. Run the pipeline from the **Run Pipeline** page first.")
    st.stop()

top_cols = st.columns([1.2, 1, 1])
ticker = top_cols[0].selectbox("Ticker", tickers, key="fin_ticker")
logger.debug("Financials: selected ticker=%s", ticker)
view_mode = top_cols[1].radio(
    "Number format",
    ["Standard (M / B)", "Indian (Cr / L)"],
    horizontal=True,
    key="fin_view_mode",
)

summary = _summary(ticker)
ratios = _ratios(ticker)

tabs = st.tabs([
    "📈 Income Statement", "🏦 Balance Sheet", "💵 Cash Flow",
    "📊 Key Ratios", "💳 Debt Schedule",
])
stmt_keys = ["income", "balance", "cashflow", "ratios", "debt"]


def _format_value(v: float | None) -> str:
    if v is None or pd.isna(v):
        return ""
    if view_mode.startswith("Indian"):
        # Lakhs (10^5) for < 1 crore, crores otherwise
        if abs(v) >= 1e7:
            return f"₹ {v/1e7:,.2f} Cr"
        if abs(v) >= 1e5:
            return f"₹ {v/1e5:,.2f} L"
        return f"{v:,.0f}"
    # Standard
    if abs(v) >= 1e9:
        return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:,.2f}M"
    return f"{v:,.0f}"


def _style_statement(df: pd.DataFrame) -> pd.DataFrame:
    """Format numeric columns and color negative values."""
    if df is None or df.empty:
        return df
    work = df.copy()
    # Keep label as-is, format numeric cols
    period_cols = [c for c in work.columns if c != "label"]
    for c in period_cols:
        work[c] = work[c].apply(_format_value)
    return work


def _render_statement(stmt_key: str, df: pd.DataFrame, *, is_ratios: bool = False) -> None:
    if df is None or df.empty:
        st.warning(f"No {stmt_key} data stored for {ticker}.")
        return

    period_cols = [c for c in df.columns if c != "label"]
    selected_periods = st.multiselect(
        "Periods", options=period_cols, default=period_cols[: min(5, len(period_cols))],
        key=f"fin_periods_{stmt_key}",
    )
    cols_to_show = (["label"] if "label" in df.columns else []) + selected_periods
    view = df[cols_to_show].copy()

    compare = st.toggle(
        "Compare two periods side-by-side",
        value=False, key=f"fin_compare_{stmt_key}",
    )
    if compare and len(selected_periods) >= 2:
        a, b = selected_periods[0], selected_periods[1]
        cmp_df = view[["label", a, b]].copy() if "label" in view.columns else view[[a, b]].copy()
        cmp_df["Variance"] = pd.to_numeric(view[a], errors="coerce") - pd.to_numeric(view[b], errors="coerce")
        cmp_df["Variance %"] = (cmp_df["Variance"] / pd.to_numeric(view[b], errors="coerce").replace(0, np.nan)) * 100
        # Format
        cmp_disp = cmp_df.copy()
        cmp_disp[a] = cmp_df[a].apply(_format_value)
        cmp_disp[b] = cmp_df[b].apply(_format_value)
        cmp_disp["Variance"] = cmp_df["Variance"].apply(_format_value)
        cmp_disp["Variance %"] = cmp_df["Variance %"].apply(lambda v: f"{v:+.2f}%" if pd.notna(v) else "")
        st.dataframe(cmp_disp, use_container_width=True, hide_index=True)
    elif is_ratios:
        st.dataframe(view, use_container_width=True, hide_index=False)
    else:
        st.dataframe(_style_statement(view), use_container_width=True, hide_index=True)

    # Export current view as CSV
    csv = view.to_csv(index=is_ratios).encode("utf-8")
    st.download_button(
        "⬇ Export this view as CSV",
        data=csv,
        file_name=f"{ticker}_{stmt_key}.csv",
        mime="text/csv",
        key=f"fin_csv_{stmt_key}",
    )


with tabs[0]:
    _render_statement("income", summary.get("income", pd.DataFrame()))
with tabs[1]:
    _render_statement("balance", summary.get("balance", pd.DataFrame()))
with tabs[2]:
    _render_statement("cashflow", summary.get("cashflow", pd.DataFrame()))
with tabs[3]:
    if ratios is None or ratios.empty:
        st.warning("No ratios available for this ticker yet.")
    else:
        view = ratios.reset_index()
        _render_statement("ratios", view, is_ratios=True)
with tabs[4]:
    _render_statement("debt", summary.get("debt", pd.DataFrame()))


# ---------------------------------------------------------------------------
# Insight cards
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Quick Insights</div>', unsafe_allow_html=True)


def _series(stmt_df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    if stmt_df is None or stmt_df.empty:
        return pd.Series(dtype=float)
    work = stmt_df.drop(columns=["label"], errors="ignore")
    for cand in candidates:
        for idx in work.index:
            if cand.lower() in str(idx).lower():
                return pd.to_numeric(work.loc[idx], errors="coerce").dropna()
    return pd.Series(dtype=float)


inc = summary.get("income", pd.DataFrame())
cfs = summary.get("cashflow", pd.DataFrame())
rev = _series(inc, ["Revenue", "Total revenue"])
ni = _series(inc, ["Net income"])
ocf = _series(cfs, ["Net cash from operations", "Cash from operations"])
capex = _series(cfs, ["Additions to property", "Capital expenditures"])

# CAGR over span (most recent ÷ oldest)
def _cagr(series: pd.Series) -> str:
    s = series.sort_index()
    if len(s) < 2 or s.iloc[0] <= 0:
        return "—"
    years = len(s) - 1
    return f"{((s.iloc[-1]/s.iloc[0]) ** (1/years) - 1) * 100:.1f}%"


def _avg_margin(num: pd.Series, den: pd.Series) -> str:
    s_n, s_d = num.reindex(den.index), den
    margin = (s_n / s_d) * 100
    if margin.dropna().empty:
        return "—"
    return f"{margin.dropna().mean():.1f}%"


def _fcf_conv(o: pd.Series, c: pd.Series) -> str:
    if o.empty or c.empty:
        return "—"
    fcf = o.sub(c.abs(), fill_value=0)
    ratio = (fcf / o).replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        return "—"
    return f"{ratio.mean()*100:.0f}%"


render_metric_cards([
    {"label": "Revenue CAGR", "value": _cagr(rev), "icon": "📈"},
    {"label": "Avg Net Margin", "value": _avg_margin(ni, rev), "icon": "💰"},
    {"label": "FCF Conversion", "value": _fcf_conv(ocf, capex), "icon": "💸"},
])
