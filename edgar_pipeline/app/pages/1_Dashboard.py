"""Dashboard - high-level overview of watchlist + recent outputs."""

from __future__ import annotations

import html as _h
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import humanize
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)
logger.debug("Page load: 1_Dashboard")

from app_utils import (  # noqa: E402
    get_chart_colors,
    get_effective_watchlist,
    get_mime_type,
    get_plotly_template,
    inject_css,
    list_output_files,
    parse_output_filename,
    tail_log,
)
from components.metric_cards import render_metric_cards  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402

inject_css(st)
render_sidebar()

st.markdown('<h1 style="margin-top:0;">📊 Dashboard</h1>', unsafe_allow_html=True)
st.caption("Snapshot of stored filings, generated files, and watchlist health.")


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _kpis() -> dict:
    import config
    from storage import db_status

    try:
        sdf = db_status()
    except Exception:
        sdf = None

    return {
        "companies": sdf["ticker"].nunique() if sdf is not None and not sdf.empty else 0,
        "filings": int(sdf["filings"].sum()) if sdf is not None and not sdf.empty else 0,
        "excels": len(list_output_files(config.EXCEL_DIR, ".xlsx")),
        "reports": (
            len(list_output_files(config.REPORTS_DIR, ".docx"))
            + len(list_output_files(config.REPORTS_DIR, ".pdf"))
        ),
    }


k = _kpis()
render_metric_cards([
    {"label": "Companies", "value": str(k["companies"]), "icon": "🏢"},
    {"label": "Filings Stored", "value": str(k["filings"]), "icon": "📁"},
    {"label": "Excel Models", "value": str(k["excels"]), "icon": "📊"},
    {"label": "Word + PDF Reports", "value": str(k["reports"]), "icon": "📄"},
])

# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
auto = st.toggle("Auto-refresh every 30 seconds", value=False, key="dash_autorefresh")
if auto:
    st.caption("Refreshing every 30s …")
    # Use Streamlit's native rerun timer
    try:
        from streamlit_autorefresh import st_autorefresh  # type: ignore
        st_autorefresh(interval=30_000, key="dash_refresher")
    except ImportError:
        st.info("Install `streamlit-autorefresh` for native auto-refresh; falling back to manual rerun.")
        if st.button("Refresh now"):
            st.rerun()


# ---------------------------------------------------------------------------
# Two-column body
# ---------------------------------------------------------------------------
left, right = st.columns([1.3, 1])

with left:
    st.markdown('<div class="section-header">Watchlist Status</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=30)
    def _watchlist_rows() -> pd.DataFrame:
        import config
        from storage import db_status, get_filing_history

        wl = get_effective_watchlist()
        sdf = db_status()
        excels = list_output_files(config.EXCEL_DIR, ".xlsx")
        excel_by_t = {p.stem.split("_")[0]: p for p in excels}

        rows = []
        for t in wl:
            sub = sdf[sdf["ticker"] == t] if not sdf.empty else sdf
            try:
                hist = get_filing_history(t)
                latest_fetched = (
                    hist["fetched_at"].iloc[0][:10] if not hist.empty else None
                )
                latest_period = hist["period"].iloc[0] if not hist.empty else "—"
            except Exception:
                latest_fetched, latest_period = None, "—"
            periods = int(sub["filings"].sum()) if not sub.empty else 0
            file_ready = "✅" if t in excel_by_t else "—"
            rows.append({
                "Ticker": t,
                "Last Fetched": latest_fetched or "Never",
                "Periods": periods,
                "Latest Period": latest_period,
                "Excel": file_ready,
            })
        return pd.DataFrame(rows)

    df_wl = _watchlist_rows()

    def _row_color(row: pd.Series) -> list[str]:
        last = row["Last Fetched"]
        color = "#E05252"
        if last and last != "Never":
            try:
                d = datetime.strptime(last, "%Y-%m-%d")
                age = (datetime.now() - d).days
                color = "#00C49A" if age <= 1 else ("#F5A623" if age <= 7 else "#E05252")
            except (ValueError, TypeError):
                color = "#8B8FA8"
        return [f"color: {color}"] * len(row)

    if df_wl.empty:
        st.info("Add tickers in the sidebar to populate your watchlist.")
    else:
        styled = df_wl.style.apply(_row_color, axis=1, subset=["Last Fetched"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

with right:
    st.markdown('<div class="section-header">Recent Outputs</div>', unsafe_allow_html=True)
    import config
    recent = (
        list_output_files(config.EXCEL_DIR, ".xlsx")
        + list_output_files(config.REPORTS_DIR, ".docx")
        + list_output_files(config.REPORTS_DIR, ".pdf")
    )
    recent = sorted(recent, key=lambda p: p.stat().st_mtime, reverse=True)[:10]
    if not recent:
        st.caption("No output files yet. Run the pipeline to generate Excel and reports.")
    else:
        for p in recent:
            info = parse_output_filename(p)
            cols = st.columns([3, 1.2, 1])
            cols[0].markdown(
                f'<div style="font-family: var(--mono); font-size:12px;">{_h.escape(p.name)}</div>'
                f'<div style="font-size:10px; color: var(--text-muted);">'
                f'{humanize.naturalsize(info["size_bytes"])} · '
                f'{humanize.naturaltime(datetime.now() - info["mtime"])}</div>',
                unsafe_allow_html=True,
            )
            cols[1].markdown(f'<span class="tag-pill">{p.suffix.lstrip(".").upper()}</span>', unsafe_allow_html=True)
            try:
                cols[2].download_button(
                    "⬇",
                    data=p.read_bytes(),
                    file_name=p.name,
                    mime=get_mime_type(p.suffix),
                    key=f"dash_dl_{p.name}_{int(p.stat().st_mtime)}",
                    use_container_width=True,
                )
            except OSError:
                cols[2].caption("err")

# ---------------------------------------------------------------------------
# Revenue sparklines per ticker
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Revenue Trend by Ticker</div>', unsafe_allow_html=True)


@st.cache_data(ttl=60)
def _revenue_trend(ticker: str) -> pd.Series:
    import processor
    summary = processor.build_summary_table(ticker)
    inc = summary.get("income")
    if inc is None or inc.empty:
        return pd.Series(dtype=float)
    period_cols = [c for c in inc.columns if c != "label"]
    for kw in ("Revenue", "Revenues", "Total revenue"):
        for idx in inc.index:
            if kw.lower() in str(idx).lower():
                row = inc.loc[idx, period_cols]
                return pd.to_numeric(row, errors="coerce").dropna().sort_index()
    return pd.Series(dtype=float)


wl = get_effective_watchlist()
if wl:
    sparkline_cols = st.columns(min(len(wl), 4))
    for i, t in enumerate(wl[:8]):
        rev = _revenue_trend(t)
        col = sparkline_cols[i % len(sparkline_cols)]
        with col:
            st.markdown(f'<div style="font-family: var(--mono); font-size:13px; font-weight:700;">{t}</div>', unsafe_allow_html=True)
            if rev.empty:
                st.caption("No data")
                continue
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(rev.index), y=rev.values,
                mode="lines+markers",
                line=dict(color="#0F9E75", width=2),
                marker=dict(size=4, color="#00C49A"),
                hovertemplate="<b>%{x}</b>: $%{y:,.0f}<extra></extra>",
            ))
            fig.update_layout(
                template=get_plotly_template(st), height=110,
                margin=dict(l=0, r=0, t=10, b=10),
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False, visible=False),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            latest = rev.iloc[-1] if len(rev) else 0
            st.caption(f"Latest: ${latest:,.0f}")
else:
    st.caption("Add tickers in the sidebar to see revenue sparklines.")
