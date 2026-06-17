"""Shared sidebar: logo, navigation, watchlist manager, status indicator."""

from __future__ import annotations

import html as _html
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from app_utils import (  # noqa: E402
    add_to_watchlist,
    get_effective_watchlist,
    list_output_files,
    remove_from_watchlist,
)
from components.status_badge import badge_html  # noqa: E402


def render_sidebar() -> None:
    import config
    from storage import db_status

    with st.sidebar:
        # ---- Logo ----
        st.markdown(
            '<div style="padding: 8px 0 16px 0;">'
            '<div style="font-family: var(--mono); font-size:11px; color: var(--text-muted); letter-spacing: 0.18em;">VALUEADD</div>'
            '<div style="font-size:22px; font-weight:800; background: linear-gradient(90deg, #FAFAFA, #6FCDF7); -webkit-background-clip:text; -webkit-text-fill-color: transparent;">RESEARCH</div>'
            '<div style="font-family: var(--mono); font-size:10px; color: var(--text-muted); margin-top:2px;">SEC EDGAR Intelligence</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # ---- Navigation ----
        st.markdown('<div class="section-header" style="font-size:13px;">Navigation</div>', unsafe_allow_html=True)
        try:
            st.page_link("streamlit_app.py", label="🏠 Home", icon=None)
            st.page_link("pages/1_Dashboard.py", label="📊 Dashboard")
            st.page_link("pages/2_Run_Pipeline.py", label="🚀 Run Pipeline")
            st.page_link("pages/3_Financials.py", label="📋 Financials")
            st.page_link("pages/4_Charts.py", label="📈 Charts")
            st.page_link("pages/5_Downloads.py", label="⬇️ Downloads")
            st.page_link("pages/6_Logs.py", label="📜 Logs")
        except Exception:
            # st.page_link requires streamlit >= 1.30 and a multipage layout
            pass

        # ---- Pipeline status ----
        running = bool(st.session_state.get("pipeline_running"))
        st.markdown('<div class="section-header" style="font-size:13px; margin-top:18px;">Pipeline</div>', unsafe_allow_html=True)
        st.markdown(badge_html("running" if running else "idle"), unsafe_allow_html=True)
        last_run = st.session_state.get("last_run_ts")
        if last_run:
            st.caption(f"Last run: {last_run}")
        else:
            st.caption("No runs in this session")

        # ---- Watchlist ----
        st.markdown('<div class="section-header" style="font-size:13px; margin-top:18px;">Watchlist</div>', unsafe_allow_html=True)
        watchlist = get_effective_watchlist()
        chips_html = "".join(
            f'<span class="ticker-chip">{_html.escape(t)}</span>' for t in watchlist
        )
        empty_html = '<em style="color: var(--text-muted)">No tickers yet</em>'
        st.markdown(
            f'<div style="margin-bottom:8px;">{chips_html or empty_html}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"{len(watchlist)} ticker{'s' if len(watchlist) != 1 else ''} tracked")

        with st.form("add_ticker_form", clear_on_submit=True):
            c1, c2 = st.columns([3, 1])
            new_t = c1.text_input(
                "Add Ticker",
                placeholder="e.g. NVDA",
                label_visibility="collapsed",
            )
            add_clicked = c2.form_submit_button("Add", use_container_width=True)
            if add_clicked and new_t:
                ok, msg = add_to_watchlist(new_t)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

        with st.expander("Remove ticker", expanded=False):
            if watchlist:
                rm = st.selectbox(
                    "Select ticker to remove",
                    watchlist,
                    label_visibility="collapsed",
                    key="sb_rm_select",
                )
                if st.button("Remove", key="sb_rm_btn", use_container_width=True):
                    ok, msg = remove_from_watchlist(rm)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
            else:
                st.caption("Nothing to remove.")

        # ---- Quick stats ----
        try:
            status_df = db_status()
            n_companies = status_df["ticker"].nunique() if not status_df.empty else 0
            n_filings = int(status_df["filings"].sum()) if not status_df.empty else 0
        except Exception:
            n_companies = 0
            n_filings = 0

        n_reports = (
            len(list_output_files(config.REPORTS_DIR, ".docx"))
            + len(list_output_files(config.REPORTS_DIR, ".pdf"))
        )

        st.markdown('<div class="section-header" style="font-size:13px; margin-top:18px;">Quick Stats</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-family: var(--mono); font-size:12px; color: var(--text-muted); line-height:1.7;">'
            f'<b style="color: var(--text);">{n_companies}</b> companies · '
            f'<b style="color: var(--text);">{n_filings}</b> filings · '
            f'<b style="color: var(--text);">{n_reports}</b> reports'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ---- Footer ----
        st.markdown(
            '<div style="position:absolute; bottom: 20px; font-size: 10px; color: var(--text-muted); font-family: var(--mono); letter-spacing: 0.06em;">'
            'SEC EDGAR · Free · No API Key'
            '</div>',
            unsafe_allow_html=True,
        )
