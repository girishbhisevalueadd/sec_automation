"""Logs page - run history + live tail of pipeline.log."""

from __future__ import annotations

import html as _h
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)
logger.info("Page load: 6_Logs")

from app_utils import (  # noqa: E402
    classify_log_line,
    extract_recent_runs,
    inject_css,
    tail_log,
)
from components.sidebar import render_sidebar  # noqa: E402
from components.status_badge import badge_html  # noqa: E402

inject_css(st)
render_sidebar()

st.markdown('<h1 style="margin-top:0;">📜 Pipeline Logs</h1>', unsafe_allow_html=True)
st.caption("Pipeline run history and live log tail.")


# ---------------------------------------------------------------------------
# Section 1: Run History
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Run History</div>', unsafe_allow_html=True)

runs = extract_recent_runs(20)
if not runs:
    st.info("No pipeline runs recorded yet.")
else:
    flt_cols = st.columns([1, 1, 1])
    status_f = flt_cols[0].multiselect("Status", ["running", "success", "failed"], default=["running", "success", "failed"])
    ticker_q = flt_cols[1].text_input("Ticker contains", "")
    date_q = flt_cols[2].text_input("Date contains (YYYY-MM-DD)", "")

    rows = []
    for r in runs:
        if r["status"] not in status_f:
            continue
        text = "\n".join(r["lines"])
        if ticker_q and ticker_q.upper() not in text.upper():
            continue
        if date_q and date_q not in (r.get("start", "") + r.get("end", "")):
            continue
        rows.append(r)

    for i, r in enumerate(rows):
        head_cols = st.columns([2, 2, 2, 1])
        head_cols[0].markdown(f'<span style="font-family: var(--mono);">{r.get("start","—")}</span>', unsafe_allow_html=True)
        head_cols[1].markdown(f'<span style="font-family: var(--mono);">→ {r.get("end","—")}</span>', unsafe_allow_html=True)
        head_cols[2].markdown(badge_html(r["status"]), unsafe_allow_html=True)
        with head_cols[3]:
            show = st.toggle("Detail", key=f"log_detail_{i}", value=False, label_visibility="visible")
        if show:
            body = "".join(
                f'<span class="console-line {classify_log_line(l)}">{_h.escape(l)}</span>\n'
                for l in r["lines"][-40:]
            )
            st.markdown(f'<div class="console-output">{body}</div>', unsafe_allow_html=True)
        st.divider()


# ---------------------------------------------------------------------------
# Section 2: Live log tail
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Live Log Tail</div>', unsafe_allow_html=True)

import config  # noqa: E402
from logging_config import UI_LOG_PATH  # noqa: E402

LOG_SOURCES = {
    "pipeline.log (backend)": config.LOG_PATH,
    "streamlit_ui.log (UI)": UI_LOG_PATH,
}

ctrl_cols = st.columns([1.4, 1, 1, 1, 2])
source_label = ctrl_cols[0].selectbox("Source", list(LOG_SOURCES.keys()), index=0)
log_path = LOG_SOURCES[source_label]
logger.debug("Logs page: source=%s path=%s", source_label, log_path)

n_lines = ctrl_cols[1].selectbox("Lines", [50, 100, 200, 500], index=1)
if ctrl_cols[2].button("🔄 Refresh", use_container_width=True):
    logger.debug("Logs page: manual refresh")
    st.rerun()
clear_display = ctrl_cols[3].button("Clear display", use_container_width=True)

if log_path.exists():
    try:
        log_bytes = log_path.read_bytes()
        ctrl_cols[4].download_button(
            "⬇ Download full log",
            data=log_bytes,
            file_name=log_path.name,
            mime="text/plain",
            use_container_width=True,
        )
    except OSError as e:
        logger.warning("Failed to read %s for download: %s", log_path, e)


def _read_tail(path: Path, n: int) -> list[str]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.readlines()[-n:]
    except OSError as e:
        logger.warning("Failed to tail %s: %s", path, e)
        return []


if clear_display:
    st.markdown('<div class="console-output muted">Display cleared. Click Refresh.</div>', unsafe_allow_html=True)
else:
    lines = _read_tail(log_path, int(n_lines))
    if not lines:
        st.info(f"No log entries yet in `{log_path.name}`.")
    else:
        body = "".join(
            f'<span class="console-line {classify_log_line(line.rstrip())}">{_h.escape(line.rstrip())}</span>\n'
            for line in lines
        )
        # Auto-scroll: render the box and let CSS handle overflow
        st.markdown(f'<div class="console-output" style="max-height: 480px;">{body}</div>', unsafe_allow_html=True)
        st.caption(f"Showing last {len(lines)} lines of {log_path.name}")
