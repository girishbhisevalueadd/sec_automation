"""Run Pipeline page - trigger fetch/build/report with live console output."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)
logger.debug("Page load: 2_Run_Pipeline")

from app_utils import get_effective_watchlist, get_mime_type, inject_css  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402
from components.branding import render_page_branding  # noqa: E402
from components.status_badge import badge_html  # noqa: E402
from pipeline_runner import (  # noqa: E402
    drain_queue,
    format_console_html,
    start_pipeline_thread,
)

inject_css(st)
render_sidebar()
render_page_branding()

st.markdown('<h1 style="margin-top:0;">🚀 Run Pipeline</h1>', unsafe_allow_html=True)
st.caption("Pull SEC filings, build Excel models, and generate research reports.")

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("pipeline_running", False)
ss.setdefault("pipeline_output", [])
ss.setdefault("pipeline_thread", None)
ss.setdefault("pipeline_queue", None)
ss.setdefault("pipeline_files", [])
ss.setdefault("pipeline_status", "idle")
ss.setdefault("pipeline_ticker", "")
ss.setdefault("last_run_ts", "")
ss.setdefault("pipeline_timings", [])         # accumulated across tickers/forms
ss.setdefault("pipeline_thread_timings", [])  # current worker's list (mutated)

# ---------------------------------------------------------------------------
# Layout: left config panel, right console
# ---------------------------------------------------------------------------
left, right = st.columns([1, 2])

with left:
    st.markdown('<div class="section-header">Run Configuration</div>', unsafe_allow_html=True)
    prefill = ss.pop("prefill_ticker", "") if "prefill_ticker" in ss else ""

    # Wrap inputs in a form so EVERY widget (text_input, radios, checkboxes)
    # commits its value atomically on submit. Without a form, a button's
    # `disabled=` flag is evaluated against stale widget state and the
    # first click lands while the button is still disabled, forcing the
    # user to click a second time.
    with st.form("rp_run_form", clear_on_submit=False):
        mode = st.radio(
            "Source", ["Single ticker", "Watchlist"], horizontal=True, key="rp_mode"
        )

        single = st.text_input(
            "Ticker (used only when Source = Single ticker)",
            value=prefill or ss.get("pipeline_ticker", ""),
            placeholder="AAPL",
            key="rp_single_ticker",
        )
        wl_default = get_effective_watchlist()
        multi = st.multiselect(
            "Tickers (used only when Source = Watchlist)",
            options=wl_default, default=wl_default, key="rp_multi_tickers",
        )

        form = st.radio("Form type", ["10-K", "10-Q", "Both"], horizontal=True, key="rp_form")
        limit = st.slider("Filings per form", min_value=1, max_value=10, value=5, key="rp_limit")

        st.markdown('<div class="section-header" style="font-size:14px;">Steps</div>', unsafe_allow_html=True)
        do_fetch = st.checkbox("Fetch from SEC EDGAR", value=True, key="rp_step_fetch")
        do_store = st.checkbox("Store in SQLite", value=True, key="rp_step_store")
        do_excel = st.checkbox("Build Excel Model", value=True, key="rp_step_excel")
        do_word = st.checkbox("Generate Word Report", value=True, key="rp_step_word")
        do_pdf = st.checkbox("Generate PDF Report", value=True, key="rp_step_pdf")
        do_narr = st.checkbox(
            "Generate AI Narrative (Anthropic API key)",
            value=False, key="rp_step_narr",
            help="Requires ANTHROPIC_API_KEY environment variable.",
        )
        force_refresh = st.checkbox(
            "Force refresh from EDGAR (ignore SQLite cache)",
            value=False, key="rp_force_refresh",
            help="If unchecked, the pipeline reuses already-stored filings and skips the EDGAR fetch.",
        )

        run_clicked = st.form_submit_button(
            "▶ Run Pipeline",
            type="primary",
            use_container_width=True,
            disabled=ss["pipeline_running"],
        )

    # Separate "Run Whole Watchlist" button outside the form so it works
    # without form-submit semantics.
    run_all = st.button(
        "▶ Run Whole Watchlist",
        use_container_width=True,
        disabled=ss["pipeline_running"],
        key="rp_run_all_btn",
    )

    # Resolve selected_tickers from the freshly committed widget values
    if mode == "Single ticker":
        selected_tickers = [single.strip().upper()] if single and single.strip() else []
    else:
        selected_tickers = list(multi)

    steps: set[str] = set()
    if do_fetch: steps.add("fetch")
    if do_store: steps.add("store")
    if do_excel: steps.add("build_excel")
    if do_word: steps.add("build_word")
    if do_pdf: steps.add("build_pdf")

    # Validation feedback - shown if the user tries to submit incomplete inputs
    if run_clicked and not selected_tickers:
        st.error("Please enter at least one ticker before running.")
    if run_clicked and not steps:
        st.error("Pick at least one pipeline step.")

    if run_all:
        selected_tickers = get_effective_watchlist()
        run_clicked = True

    if run_clicked and selected_tickers and steps:
        logger.info(
            "User triggered pipeline: tickers=%s form=%s limit=%d steps=%s narrative=%s force_refresh=%s",
            selected_tickers, form, limit, sorted(steps), do_narr, force_refresh,
        )
        # Reset state
        ss["pipeline_output"] = []
        ss["pipeline_files"] = []
        ss["pipeline_timings"] = []
        ss["pipeline_thread_timings"] = []
        ss["pipeline_running"] = True
        ss["pipeline_status"] = "running"
        ss["pipeline_ticker"] = selected_tickers[0]
        ss["pipeline_queue_list"] = list(selected_tickers)
        ss["last_run_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Spawn the first ticker; subsequent ones queued for serial execution
        forms_to_run = ["10-K", "10-Q"] if form == "Both" else [form]
        ss["pipeline_forms_to_run"] = forms_to_run
        ss["pipeline_form_idx"] = 0
        first_ticker = selected_tickers[0]
        thread, q, files, timings = start_pipeline_thread(
            ticker=first_ticker,
            steps=steps,
            form=forms_to_run[0],
            limit=limit,
            use_narrative=do_narr,
            force_refresh=force_refresh,
        )
        ss["pipeline_thread"] = thread
        ss["pipeline_queue"] = q
        ss["pipeline_files"] = files
        ss["pipeline_thread_timings"] = timings
        ss["pipeline_steps"] = steps
        ss["pipeline_limit"] = limit
        ss["pipeline_use_narr"] = do_narr
        ss["pipeline_force_refresh"] = force_refresh
        st.rerun()

with right:
    # Status bar
    sb_col, info_col = st.columns([1, 3])
    with sb_col:
        st.markdown(badge_html(ss["pipeline_status"]), unsafe_allow_html=True)
    with info_col:
        if ss["pipeline_running"]:
            cur_t = ss.get("pipeline_ticker", "")
            st.caption(f"Running: {cur_t}")
        elif ss["pipeline_status"] == "success":
            st.caption(f"Done at {ss.get('last_run_ts','')}")
        else:
            st.caption("Configure on the left, then click Run.")

    # Live console
    st.markdown('<div class="section-header" style="margin-top:4px;">Live Console</div>', unsafe_allow_html=True)
    console_placeholder = st.empty()
    progress_placeholder = st.empty()

    def _render_console() -> None:
        lines = ss.get("pipeline_output", [])
        cls = "console-output running" if ss["pipeline_running"] else "console-output"
        body = format_console_html(lines) if lines else (
            '<span class="console-line muted">Waiting for pipeline run …</span>'
        )
        console_placeholder.markdown(
            f'<div class="{cls}">{body}</div>',
            unsafe_allow_html=True,
        )

    _render_console()

    # Drain queue if running
    if ss["pipeline_running"] and ss.get("pipeline_queue") is not None:
        drain_queue(ss["pipeline_queue"], ss["pipeline_output"])

        # Progress proxy: ~10% per OK/INFO event, capped at 95% until DONE
        ok_count = sum(1 for line in ss["pipeline_output"] if "[OK]" in line or "[INFO]" in line)
        progress = min(5 + ok_count * 8, 95)

        thread_alive = ss["pipeline_thread"] and ss["pipeline_thread"].is_alive()
        last_line = ss["pipeline_output"][-1] if ss["pipeline_output"] else ""

        # Failsafe: if the worker thread has finished but for some reason
        # no terminal marker reached us yet, synthesise one. This prevents
        # the page from spinning forever after a crash inside the thread.
        if not thread_alive and "[DONE]" not in last_line and "[ERROR]" not in last_line:
            logger.warning("Pipeline thread died without a terminal marker - synthesising [DONE]")
            ss["pipeline_output"].append("[FAILSAFE] [DONE] worker thread exited unexpectedly")
            last_line = ss["pipeline_output"][-1]

        if "[DONE]" in last_line or "[ERROR]" in last_line:
            # Worker emits all timing records BEFORE pushing [DONE], so it
            # is safe to drain them into the persistent session list now.
            if ss.get("pipeline_thread_timings"):
                ss["pipeline_timings"].extend(ss["pipeline_thread_timings"])
                ss["pipeline_thread_timings"] = []

            # Move to next form or next ticker
            tickers = ss.get("pipeline_queue_list", [])
            forms = ss.get("pipeline_forms_to_run", ["10-K"])
            form_idx = ss.get("pipeline_form_idx", 0) + 1
            done = False
            if form_idx < len(forms):
                ss["pipeline_form_idx"] = form_idx
                next_ticker = ss.get("pipeline_ticker", tickers[0] if tickers else "")
            else:
                ss["pipeline_form_idx"] = 0
                if len(tickers) > 1:
                    tickers = tickers[1:]
                    ss["pipeline_queue_list"] = tickers
                    next_ticker = tickers[0]
                else:
                    done = True
                    next_ticker = ""

            if not done:
                ss["pipeline_ticker"] = next_ticker
                thread, q, files, timings = start_pipeline_thread(
                    ticker=next_ticker,
                    steps=ss["pipeline_steps"],
                    form=forms[ss["pipeline_form_idx"]],
                    limit=ss["pipeline_limit"],
                    use_narrative=ss["pipeline_use_narr"],
                    force_refresh=ss.get("pipeline_force_refresh", False),
                )
                ss["pipeline_thread_timings"] = timings
                ss["pipeline_thread"] = thread
                ss["pipeline_queue"] = q
                ss["pipeline_files"].extend(files) if files is not ss["pipeline_files"] else None
                # We track files in-place via list mutation in pipeline_runner.
                ss["pipeline_thread_files"] = files
            else:
                ss["pipeline_running"] = False
                had_err = any("[ERROR]" in ln for ln in ss["pipeline_output"])
                ss["pipeline_status"] = "failed" if had_err else "success"
                progress = 100
                logger.info(
                    "Pipeline run finished: status=%s files=%d",
                    ss["pipeline_status"], len(ss["pipeline_files"]),
                )

        progress_placeholder.progress(progress / 100, text=f"Progress {progress}%")

        if ss["pipeline_running"]:
            time.sleep(0.6)
            st.rerun()
    else:
        progress_placeholder.empty()

# ---------------------------------------------------------------------------
# Files created card row
# ---------------------------------------------------------------------------
if ss.get("pipeline_files") and not ss["pipeline_running"]:
    st.markdown('<div class="section-header" style="margin-top:20px;">Files Created</div>', unsafe_allow_html=True)
    cols = st.columns(min(len(ss["pipeline_files"]), 4))
    for i, fp in enumerate(ss["pipeline_files"]):
        fp = Path(fp)
        if not fp.exists():
            continue
        with cols[i % len(cols)]:
            st.markdown(
                f'<div class="metric-card" style="padding:14px;">'
                f'<div class="label">{fp.suffix.lstrip(".").upper()}</div>'
                f'<div style="font-family: var(--mono); font-size:13px; word-break: break-all;">{fp.name}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            try:
                st.download_button(
                    label="⬇ Download",
                    data=fp.read_bytes(),
                    file_name=fp.name,
                    mime=get_mime_type(fp.suffix),
                    key=f"rp_dl_{fp.name}_{int(fp.stat().st_mtime)}",
                    use_container_width=True,
                )
            except OSError as e:
                st.caption(f"⚠ {e}")


# ---------------------------------------------------------------------------
# Time Required - per-step elapsed time table
# ---------------------------------------------------------------------------
if ss.get("pipeline_timings") and not ss["pipeline_running"]:
    import pandas as pd

    # Order rows in the user's preferred display order, not the execution
    # order (execution: fetch -> store -> excel -> narrative -> word -> pdf).
    display_order = [
        "Fetch from SEC EDGAR",
        "Store in SQLite",
        "Build Excel Model",
        "Generate Word Report",
        "Generate PDF Report",
        "Generate AI Narrative",
    ]

    # Aggregate by step name. When multiple tickers run in one pipeline,
    # each step's time is summed across all tickers / forms.
    agg: dict[str, dict] = {}
    total_seconds = 0.0
    for rec in ss["pipeline_timings"]:
        step = rec.get("step", "")
        secs = float(rec.get("seconds") or 0)
        skipped = bool(rec.get("skipped"))
        if step == "Total":
            total_seconds += secs
            continue
        bucket = agg.setdefault(step, {"seconds": 0.0, "ran_at_least_once": False})
        if not skipped:
            bucket["seconds"] += secs
            bucket["ran_at_least_once"] = True

    rows = []
    for i, step in enumerate(display_order, start=1):
        info = agg.get(step)
        if info and info["ran_at_least_once"]:
            time_str = f"{info['seconds']:.2f}"
        else:
            time_str = "Skipped"
        rows.append({"#": i, "Step": step, "Time (seconds)": time_str})

    # Total row - formatted as plain seconds when short, otherwise "Xm Y.Zs"
    if total_seconds < 60:
        total_str = f"{total_seconds:.2f} seconds"
    else:
        mins = int(total_seconds // 60)
        rem = total_seconds - mins * 60
        total_str = f"{mins}m {rem:.1f}s  ({total_seconds:.2f} seconds)"
    rows.append({"#": 7, "Step": "TOTAL", "Time (seconds)": total_str})

    timing_df = pd.DataFrame(rows)

    st.markdown('<div class="section-header" style="margin-top:24px;">⏱ Time Required</div>', unsafe_allow_html=True)

    # Render with last row (TOTAL) highlighted bold.
    def _highlight_total(row):
        if row["Step"] == "TOTAL":
            return ["font-weight: 700; background-color: rgba(29,111,164,0.08);"] * len(row)
        return [""] * len(row)

    styled = timing_df.style.apply(_highlight_total, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)
