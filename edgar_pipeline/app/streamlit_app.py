"""Edgar Pipeline - Streamlit landing page.

Run from the edgar_pipeline directory:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# Make sibling modules importable
_APP_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---- Initialize logging FIRST so every subsequent import is logged ----
from logging_config import setup_logging, log_call, UI_LOG_PATH  # noqa: E402
setup_logging(level=os.environ.get("EDGAR_UI_LOG_LEVEL", "INFO"))

import logging  # noqa: E402
logger = logging.getLogger(__name__)
logger.info("=" * 70)
logger.info("Streamlit app boot: streamlit_app.py")
logger.info("APP_DIR=%s  PIPELINE_ROOT=%s", _APP_DIR, _PIPELINE_ROOT)
logger.info("Streamlit version=%s", st.__version__)

# Page config MUST be the very first Streamlit call in the script
st.set_page_config(
    page_title="Edgar Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "ValueAdd Research · SEC EDGAR pipeline · Powered by edgartools"},
)
logger.debug("st.set_page_config() applied")

from app_utils import (  # noqa: E402
    get_effective_watchlist,
    inject_css,
    list_output_files,
    tail_log,
    classify_log_line,
)
from components.sidebar import render_sidebar  # noqa: E402
from components.metric_cards import render_metric_cards  # noqa: E402

logger.debug("Imports complete - injecting CSS and rendering sidebar")
inject_css(st)
render_sidebar()


# ---------------------------------------------------------------------------
# Cached data accessors
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
@log_call(log_args=False)
def _kpi_snapshot() -> dict:
    import config
    from storage import db_status

    try:
        sdf = db_status()
    except Exception:
        sdf = None

    n_companies = sdf["ticker"].nunique() if sdf is not None and not sdf.empty else 0
    n_filings = int(sdf["filings"].sum()) if sdf is not None and not sdf.empty else 0
    n_reports = (
        len(list_output_files(config.REPORTS_DIR, ".docx"))
        + len(list_output_files(config.REPORTS_DIR, ".pdf"))
    )
    n_excels = len(list_output_files(config.EXCEL_DIR, ".xlsx"))

    last_run = ""
    log_lines = tail_log(200)
    for line in reversed(log_lines):
        if "[DONE]" in line or "Pipeline completed" in line or "Run result" in line:
            last_run = line[:19]
            break
    if not last_run and log_lines:
        last_run = log_lines[-1][:19]

    return {
        "companies": n_companies,
        "filings": n_filings,
        "reports": n_reports,
        "excels": n_excels,
        "last_run": last_run or "—",
    }


# ---------------------------------------------------------------------------
# Hero banner
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="hero">'
    '<h1>SEC Financial Intelligence Platform</h1>'
    '<p>Powered by <b>edgartools</b> &nbsp;·&nbsp; Built by ValueAdd Research And Analytics Solutions LLP</p>'
    '</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
kpi = _kpi_snapshot()
render_metric_cards([
    {"label": "Companies Tracked", "value": str(kpi["companies"]), "icon": "🏢", "delta": ""},
    {"label": "Filings Stored", "value": str(kpi["filings"]), "icon": "📁", "delta": ""},
    {"label": "Reports Generated", "value": str(kpi["reports"]), "icon": "📄", "delta": ""},
    {"label": "Last Pipeline Run", "value": kpi["last_run"], "icon": "⏱", "delta": ""},
])

# ---------------------------------------------------------------------------
# Quick Run
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Quick Run</div>', unsafe_allow_html=True)
qr_col1, qr_col2 = st.columns([3, 1])
quick_ticker = qr_col1.text_input(
    "Ticker",
    placeholder="e.g. AAPL, MSFT, NVDA …",
    key="home_quick_ticker",
    label_visibility="collapsed",
)
qr_run = qr_col2.button("▶ Run Full Pipeline", type="primary", use_container_width=True)

if qr_run and quick_ticker:
    logger.info("Quick Run clicked: ticker=%s → routing to 2_Run_Pipeline", quick_ticker.upper())
    st.session_state["prefill_ticker"] = quick_ticker.upper()
    st.switch_page("pages/2_Run_Pipeline.py")

# ---------------------------------------------------------------------------
# Two-column body: watchlist quick view + activity feed
# ---------------------------------------------------------------------------
left, right = st.columns([1.2, 1])

with left:
    st.markdown('<div class="section-header">Watchlist Snapshot</div>', unsafe_allow_html=True)
    wl = get_effective_watchlist()
    if not wl:
        st.info("Add tickers in the sidebar to populate your watchlist.")
    else:
        from storage import get_filing_history
        rows = []
        for t in wl:
            try:
                hist = get_filing_history(t)
                periods = len(hist) if hist is not None else 0
                latest = (hist["period"].iloc[0] if periods else "—") if periods else "—"
            except Exception:
                periods, latest = 0, "—"
            rows.append({"Ticker": t, "Periods": periods, "Latest": latest})
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with right:
    st.markdown('<div class="section-header">Recent Activity</div>', unsafe_allow_html=True)
    runs = []
    for line in reversed(tail_log(60)):
        line = line.rstrip("\n")
        if not line:
            continue
        runs.append(line)
        if len(runs) >= 6:
            break
    if not runs:
        st.caption("No pipeline activity yet.")
    else:
        import html as _h
        feed_html = "".join(
            f'<div class="activity-item {classify_log_line(line)}">{_h.escape(line[:150])}</div>'
            for line in runs
        )
        st.markdown(feed_html, unsafe_allow_html=True)
