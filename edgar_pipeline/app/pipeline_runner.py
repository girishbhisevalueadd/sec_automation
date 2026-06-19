"""Background-thread pipeline runner with a streaming output queue.

Wraps the backend modules (fetcher, storage, processor, model_builder,
report_writer, narrative) without modifying them. Pushes status lines
to a shared queue so the Streamlit UI can render them live.
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _APP_DIR.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

logger = logging.getLogger(__name__)


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def run_pipeline_with_output(
    ticker: str,
    steps: set[str],
    form: str,
    limit: int,
    use_narrative: bool,
    output_queue: queue.Queue,
    files_out: list,
    force_refresh: bool = False,
    timings_out: list | None = None,
) -> None:
    """Execute the configured pipeline steps for one ticker.

    `form` may be a single string ("10-K") or a list ("10-K", "10-Q").
    When multiple forms are passed, fetch + store run once per form, then
    the build steps (Excel / Word / PDF) run ONCE using the combined data.
    The resulting files include both annual and quarterly periods, with
    each column tagged [10-K] or [10-Q].

    `output_queue` receives strings the UI can stream.
    `files_out` is mutated in-place to collect produced file paths.
    `timings_out` is mutated in-place to record per-step elapsed time.
    `force_refresh` overrides the SQLite cache.
    """
    ticker = ticker.upper()
    forms: list[str] = [form] if isinstance(form, str) else list(form)
    if not forms:
        forms = ["10-K"]
    if timings_out is None:
        timings_out = []

    def push(line: str) -> None:
        output_queue.put(line)
        logger.debug("queue<<  %s", line)

    def record_timing(label: str, seconds: float, skipped: bool = False) -> None:
        timings_out.append({"step": label, "seconds": round(float(seconds), 3), "skipped": bool(skipped)})

    logger.info(
        "Pipeline run begin: ticker=%s forms=%s limit=%d steps=%s narrative=%s force_refresh=%s",
        ticker, forms, limit, sorted(steps), use_narrative, force_refresh,
    )
    push(f"[{_ts()}] [START] Pipeline started for {ticker} (forms={forms}, limit={limit}, force_refresh={force_refresh})")
    overall_t0 = time.time()

    # Import backend modules - any ImportError here usually means an
    # environment problem (corrupt venv, pip cache, edgartools version).
    # Catch it explicitly so the UI shows a useful message instead of
    # spinning forever.
    try:
        from fetcher import fetch_company_filings
        import storage
        import processor
        import model_builder
        import report_writer
        import narrative as narrative_mod
    except ImportError as e:  # noqa: BLE001
        logger.exception("Backend import failed: %s", e)
        push(f"[{_ts()}] [ERROR] Backend module import failed: {e}")
        push(
            f"[{_ts()}] [INFO] Likely fix: reinstall the failing package. "
            f"For edgartools issues:  pip install --force-reinstall --no-deps 'edgartools>=5.30,<6.0'"
        )
        push(traceback.format_exc())
        push(f"[{_ts()}] [DONE] Pipeline aborted (errored).")
        return

    try:

        # Iterate over every requested form: each fetch/store pass adds
        # its filings to SQLite. The downstream build/report steps run
        # ONCE at the end using the combined data so a single Excel/Word/
        # PDF reflects both 10-K (annual) and 10-Q (quarterly) periods.
        any_filings_fetched = False
        fetch_total_elapsed = 0.0
        store_total_elapsed = 0.0
        fetched_at_all = False
        stored_at_all = False

        for form_iter in forms:
            filings_data: list[dict] = []

            # --- Cache check per form ---
            cached_count = 0
            should_fetch = "fetch" in steps
            if should_fetch and not force_refresh:
                storage.init_db()
                try:
                    hist = storage.get_filing_history(ticker)
                    if not hist.empty and "form_type" in hist.columns:
                        cached_count = int((hist["form_type"] == form_iter).sum())
                except Exception as e:  # noqa: BLE001
                    push(f"[{_ts()}] [WARN] Cache lookup failed for {form_iter}: {e}")
                    cached_count = 0

                if cached_count >= limit:
                    push(
                        f"[{_ts()}] [CACHE] {cached_count} {form_iter} filings already "
                        f"stored for {ticker} (limit={limit}). Skipping fetch + store."
                    )
                    should_fetch = False
                elif cached_count > 0:
                    push(
                        f"[{_ts()}] [CACHE] {cached_count} {form_iter} filings cached for "
                        f"{ticker} but {limit} requested - fetching to top up."
                    )
                else:
                    push(f"[{_ts()}] [CACHE] No cached {form_iter} for {ticker} - will fetch.")
            elif force_refresh and should_fetch:
                push(f"[{_ts()}] [INFO] Force refresh enabled for {form_iter}.")

            # --- Fetch ---
            t0 = time.time()
            if should_fetch:
                push(f"[{_ts()}] [INFO] Fetching {ticker} {form_iter} filings from SEC EDGAR ...")
                filings_data = fetch_company_filings(ticker, form=form_iter, limit=limit)
                push(f"[{_ts()}] [OK] Fetched {len(filings_data)} {form_iter} filings in {time.time()-t0:.1f}s")
                for fd in filings_data:
                    p = fd.get("period_of_report") or "?"
                    inc = fd["income_statement"].shape if fd.get("income_statement") is not None else (0, 0)
                    push(f"[{_ts()}] [INFO]   - {ticker} {form_iter} @ {p}  income={inc}")
                fetch_total_elapsed += time.time() - t0
                fetched_at_all = True
                if filings_data:
                    any_filings_fetched = True

            # --- Store ---
            t0 = time.time()
            if "store" in steps and filings_data:
                push(f"[{_ts()}] [INFO] Storing {form_iter} filings to SQLite ...")
                storage.init_db()
                saved = 0
                for fd in filings_data:
                    try:
                        storage.save_filing(fd)
                        saved += 1
                    except Exception as e:  # noqa: BLE001
                        push(f"[{_ts()}] [WARN]   save failed for {fd.get('period_of_report')}: {e}")
                push(f"[{_ts()}] [OK] Stored {saved} {form_iter} filings")
                store_total_elapsed += time.time() - t0
                stored_at_all = True

        # Record one timing entry per logical step (sum across all forms)
        if fetched_at_all:
            record_timing("Fetch from SEC EDGAR", fetch_total_elapsed)
        else:
            record_timing("Fetch from SEC EDGAR", 0.0, skipped=True)
        if stored_at_all:
            record_timing("Store in SQLite", store_total_elapsed)
        else:
            record_timing("Store in SQLite", 0.0, skipped=True)

        # File-name tag: use "ALL" when multiple forms were combined.
        build_form_tag = forms[0] if len(forms) == 1 else "ALL"

        summary = ratios = None
        if any(s in steps for s in ("build_excel", "build_word", "build_pdf")):
            push(f"[{_ts()}] [INFO] Building summary tables + ratios from all stored data ...")
            summary = processor.build_summary_table(ticker)
            ratios = processor.calculate_ratios(summary)
            push(f"[{_ts()}] [OK] Summary computed (income={summary['income'].shape}, ratios={ratios.shape})")

        # --- Excel ---
        excel_path = None
        t0 = time.time()
        if "build_excel" in steps and summary is not None:
            push(f"[{_ts()}] [INFO] Building Excel model ...")
            excel_path = model_builder.build_excel_model(ticker, summary, ratios, form_type=build_form_tag)
            files_out.append(excel_path)
            push(f"[{_ts()}] [OK] Excel saved: {excel_path.name}")
            record_timing("Build Excel Model", time.time() - t0)
        else:
            record_timing("Build Excel Model", 0.0, skipped=True)

        # --- Narrative ---
        narrative_text = None
        t0 = time.time()
        if use_narrative and summary is not None:
            push(f"[{_ts()}] [INFO] Generating AI narrative (Claude) ...")
            narrative_text = narrative_mod.generate_narrative(ticker, summary, ratios)
            push(f"[{_ts()}] [OK] Narrative ready ({len(narrative_text)} chars)")
            record_timing("Generate AI Narrative", time.time() - t0)
        else:
            record_timing("Generate AI Narrative", 0.0, skipped=True)

        # --- Word ---
        word_path = None
        t0 = time.time()
        if "build_word" in steps and summary is not None:
            push(f"[{_ts()}] [INFO] Generating Word report ...")
            word_path = report_writer.build_word_report(
                ticker, summary, ratios, narrative_text=narrative_text, form_type=build_form_tag,
            )
            files_out.append(word_path)
            push(f"[{_ts()}] [OK] Word saved: {word_path.name}")
            record_timing("Generate Word Report", time.time() - t0)
        else:
            record_timing("Generate Word Report", 0.0, skipped=True)

        # --- PDF ---
        t0 = time.time()
        if "build_pdf" in steps and word_path is not None:
            push(f"[{_ts()}] [INFO] Generating PDF report ...")
            try:
                pdf_path = report_writer.build_pdf_report(word_path)
                files_out.append(pdf_path)
                push(f"[{_ts()}] [OK] PDF saved: {pdf_path.name}")
                record_timing("Generate PDF Report", time.time() - t0)
            except Exception as e:  # noqa: BLE001
                push(f"[{_ts()}] [WARN] PDF generation failed: {e}")
                record_timing("Generate PDF Report", time.time() - t0)
        else:
            record_timing("Generate PDF Report", 0.0, skipped=True)

        # Total wall-clock time for this ticker
        record_timing("Total", time.time() - overall_t0)

        push(f"[{_ts()}] [DONE] Pipeline completed in {time.time()-overall_t0:.1f}s. {len(files_out)} files created.")
        logger.info("Pipeline run end: ticker=%s files_created=%d elapsed=%.2fs",
                    ticker, len(files_out), time.time() - overall_t0)

    except Exception as e:  # noqa: BLE001
        logger.exception("Pipeline run errored for %s: %s", ticker, e)
        push(f"[{_ts()}] [ERROR] {e}")
        push(traceback.format_exc())
        # Still emit a Total timing record so the UI table shows the
        # elapsed time of the failed run.
        try:
            record_timing("Total", time.time() - overall_t0)
        except Exception:  # noqa: BLE001
            pass
        # CRITICAL: emit a terminal marker as the LAST line so the UI's
        # rerun loop sees it and stops. Without this the page spins
        # forever because the last-line marker check would land on the
        # traceback instead of [ERROR] / [DONE].
        push(f"[{_ts()}] [DONE] Pipeline aborted (errored).")


def start_pipeline_thread(
    ticker: str,
    steps: set[str],
    form: str | list[str],
    limit: int,
    use_narrative: bool,
    force_refresh: bool = False,
) -> tuple[threading.Thread, queue.Queue, list, list]:
    """Spawn the worker. Returns (thread, queue, files_out, timings_out).

    `form` may be "10-K", "10-Q", or a list like ["10-K", "10-Q"]. When a
    list is passed, the worker fetches every form into SQLite before
    running the build steps ONCE - so a single Excel/Word/PDF includes
    both annual and quarterly periods.
    """
    out_q: queue.Queue = queue.Queue()
    files_out: list = []
    timings_out: list = []
    forms_display = form if isinstance(form, str) else "+".join(form)
    t = threading.Thread(
        target=run_pipeline_with_output,
        args=(ticker, steps, form, limit, use_narrative, out_q, files_out, force_refresh, timings_out),
        daemon=True,
        name=f"pipeline-{ticker}-{forms_display}",
    )
    t.start()
    logger.info(
        "Spawned thread '%s' (alive=%s) for ticker=%s forms=%s",
        t.name, t.is_alive(), ticker, forms_display,
    )
    return t, out_q, files_out, timings_out


def drain_queue(q: queue.Queue, into: list) -> bool:
    """Move all available lines from `q` into `into`. Returns True if any added."""
    added = False
    try:
        while True:
            into.append(q.get_nowait())
            added = True
    except queue.Empty:
        pass
    return added


def classify_console_line(line: str) -> str:
    if "[ERROR]" in line:
        return "err"
    if "[WARN]" in line:
        return "warn"
    if "[OK]" in line or "[DONE]" in line:
        return "ok"
    if "[INFO]" in line or "[START]" in line:
        return "info"
    return "muted"


def format_console_html(lines: list[str]) -> str:
    import html as _html
    rendered = "".join(
        f'<span class="console-line {classify_console_line(line)}">{_html.escape(line)}</span>\n'
        for line in lines
    )
    return rendered
