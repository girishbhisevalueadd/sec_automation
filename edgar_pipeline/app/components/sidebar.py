"""Shared sidebar: logo, navigation, watchlist manager, status indicator."""

from __future__ import annotations

import html as _html
import logging
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from app_utils import (  # noqa: E402
    THEME_DARK,
    THEME_LIGHT,
    add_to_watchlist,
    get_effective_watchlist,
    get_theme,
    list_output_files,
    remove_from_watchlist,
    set_theme,
)
from components.status_badge import badge_html  # noqa: E402


def render_sidebar() -> None:
    import config
    from storage import db_status

    logger.debug("render_sidebar: start")
    with st.sidebar:
        # ---- Company logo (very top of sidebar) ----
        # Base64-embed so it always renders without serving static files.
        logo_path = getattr(config, "LOGO_PATH", None)
        if logo_path and Path(logo_path).exists():
            try:
                import base64
                mime = "image/png" if str(logo_path).lower().endswith(".png") else "image/jpeg"
                with open(logo_path, "rb") as _f:
                    _b64 = base64.b64encode(_f.read()).decode("ascii")
                st.markdown(
                    f'<div style="padding: 0 0 12px 0; text-align: left;">'
                    f'<img src="data:{mime};base64,{_b64}" '
                    f'style="max-width: 180px; height: auto; display: block;" alt="ValueAdd Research"/>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            except OSError as e:  # noqa: BLE001
                logger.warning("Failed to embed sidebar logo: %s", e)

        # ---- Company name block (just below the logo) ----
        st.markdown(
            '<div style="padding: 4px 0 14px 0; border-bottom: 1px solid var(--border); margin-bottom: 12px;">'
            '<div style="font-family: var(--mono); font-size:10px; color: var(--text-muted); letter-spacing: 0.18em; margin-bottom:6px;">PRESENTED BY</div>'
            '<div style="display:flex; align-items:center; gap:8px;">'
            '<span style="display:inline-block; width:4px; height:36px; border-radius:2px; background: linear-gradient(180deg, var(--accent-blue) 0%, var(--accent-teal) 100%);"></span>'
            '<span style="font-size:17px; font-weight:900; line-height:1.20; color: var(--text); letter-spacing:-0.01em;">'
            'ValueAdd Research And Analytics Solutions LLP'
            '</span>'
            '</div>'
            '<div style="font-family: var(--mono); font-size:10px; color: var(--text-muted); margin-top:8px; letter-spacing: 0.05em;">SEC EDGAR Intelligence Platform</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        # ---- User line (below the brand block) ----
        author = getattr(config, "REPORT_AUTHOR", "Vivek Pol")
        st.markdown(
            '<div style="padding: 0 0 12px 0; margin-bottom: 6px;">'
            '<div style="font-family: var(--mono); font-size:10px; color: var(--text-muted); letter-spacing: 0.18em; margin-bottom:4px;">USER</div>'
            f'<div style="font-size:14px; font-weight:700; color: var(--text);">{_html.escape(author)}</div>'
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

        # ---- Theme toggle (bottom of sidebar) ----
        current_theme = get_theme(st)
        st.markdown(
            '<div class="theme-toggle-wrap">'
            '<div class="label">Appearance</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        labels = ["☀ Light", "🌙 Dark"]
        values = [THEME_LIGHT, THEME_DARK]
        idx = values.index(current_theme) if current_theme in values else 0
        choice = st.radio(
            "Theme",
            options=labels,
            index=idx,
            horizontal=True,
            label_visibility="collapsed",
            key="sb_theme_radio",
        )
        new_theme = values[labels.index(choice)]
        if new_theme != current_theme:
            logger.info("Theme switched: %s -> %s", current_theme, new_theme)
            set_theme(st, new_theme)
            st.rerun()

        # ---- Footer ----
        st.markdown(
            '<div style="margin-top:18px; font-size: 10px; color: var(--text-muted); font-family: var(--mono); letter-spacing: 0.06em; text-align:center;">'
            'SEC EDGAR · Free · No API Key'
            '</div>',
            unsafe_allow_html=True,
        )
