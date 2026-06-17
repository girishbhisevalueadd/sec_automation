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
) -> None:
    """Execute the configured pipeline steps for one ticker.

    `output_queue` receives strings the UI can stream.
    `files_out` is mutated in-place to collect produced file paths.
    `force_refresh` overrides the SQLite cache (re-fetch even if data is
    already stored). Default behavior reuses cached filings.
    """
    ticker = ticker.upper()

    def push(line: str) -> None:
        output_queue.put(line)
        logger.debug("queue<<  %s", line)

    logger.info(
        "Pipeline run begin: ticker=%s form=%s limit=%d steps=%s narrative=%s force_refresh=%s",
        ticker, form, limit, sorted(steps), use_narrative, force_refresh,
    )
    push(f"[{_ts()}] [START] Pipeline started for {ticker} (form={form}, limit={limit}, force_refresh={force_refresh})")

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

        filings_data: list[dict] = []

        # --- Check cache before fetching ---
        cached_count = 0
        if "fetch" in steps and not force_refresh:
            storage.init_db()
            try:
                hist = storage.get_filing_history(ticker)
                if not hist.empty and "form_type" in hist.columns:
                    cached_count = int((hist["form_type"] == form).sum())
            except Exception as e:  # noqa: BLE001
                push(f"[{_ts()}] [WARN] Cache lookup failed: {e}")
                cached_count = 0

            if cached_count >= limit:
                push(
                    f"[{_ts()}] [CACHE] Using cached SQLite data: {cached_count} {form} "
                    f"filings already stored for {ticker} (limit={limit}). Skipping fetch."
                )
                # Skip both fetch and store - downstream steps read from SQLite
                steps = steps - {"fetch", "store"}
            elif cached_count > 0:
                push(
                    f"[{_ts()}] [CACHE] {cached_count} {form} filings cached for {ticker} "
                    f"but {limit} requested - fetching to top up."
                )
            else:
                push(f"[{_ts()}] [CACHE] No cached data for {ticker} {form} - will fetch from EDGAR.")
        elif force_refresh and "fetch" in steps:
            push(f"[{_ts()}] [INFO] Force refresh enabled - bypassing cache.")

        # --- Fetch ---
        if "fetch" in steps:
            push(f"[{_ts()}] [INFO] Fetching {ticker} {form} filings from SEC EDGAR ...")
            t0 = time.time()
            filings_data = fetch_company_filings(ticker, form=form, limit=limit)
            push(f"[{_ts()}] [OK] Fetched {len(filings_data)} filings in {time.time()-t0:.1f}s")
            for fd in filings_data:
                p = fd.get("period_of_report") or "?"
                inc = fd["income_statement"].shape if fd.get("income_statement") is not None else (0, 0)
                push(f"[{_ts()}] [INFO]   - {ticker} {form} @ {p}  income={inc}")

        # --- Store (only when we actually fetched) ---
        if "store" in steps and filings_data:
            push(f"[{_ts()}] [INFO] Storing filings to SQLite ...")
            storage.init_db()
            saved = 0
            for fd in filings_data:
                try:
                    storage.save_filing(fd)
                    saved += 1
                except Exception as e:  # noqa: BLE001
                    push(f"[{_ts()}] [WARN]   save failed for {fd.get('period_of_report')}: {e}")
            push(f"[{_ts()}] [OK] Stored {saved} filings")

        summary = ratios = None
        if any(s in steps for s in ("build_excel", "build_word", "build_pdf")):
            push(f"[{_ts()}] [INFO] Building summary tables + ratios ...")
            summary = processor.build_summary_table(ticker, periods=5)
            ratios = processor.calculate_ratios(summary)
            push(f"[{_ts()}] [OK] Summary computed (income={summary['income'].shape}, ratios={ratios.shape})")

        # --- Excel ---
        excel_path = None
        if "build_excel" in steps and summary is not None:
            push(f"[{_ts()}] [INFO] Building Excel model ...")
            excel_path = model_builder.build_excel_model(ticker, summary, ratios, form_type=form)
            files_out.append(excel_path)
            push(f"[{_ts()}] [OK] Excel saved: {excel_path.name}")

        # --- Narrative ---
        narrative_text = None
        if use_narrative and summary is not None:
            push(f"[{_ts()}] [INFO] Generating AI narrative (Claude) ...")
            narrative_text = narrative_mod.generate_narrative(ticker, summary, ratios)
            push(f"[{_ts()}] [OK] Narrative ready ({len(narrative_text)} chars)")

        # --- Word ---
        word_path = None
        if "build_word" in steps and summary is not None:
            push(f"[{_ts()}] [INFO] Generating Word report ...")
            word_path = report_writer.build_word_report(
                ticker, summary, ratios, narrative_text=narrative_text, form_type=form,
            )
            files_out.append(word_path)
            push(f"[{_ts()}] [OK] Word saved: {word_path.name}")

        # --- PDF ---
        if "build_pdf" in steps and word_path is not None:
            push(f"[{_ts()}] [INFO] Generating PDF report ...")
            try:
                pdf_path = report_writer.build_pdf_report(word_path)
                files_out.append(pdf_path)
                push(f"[{_ts()}] [OK] PDF saved: {pdf_path.name}")
            except Exception as e:  # noqa: BLE001
                push(f"[{_ts()}] [WARN] PDF generation failed: {e}")

        push(f"[{_ts()}] [DONE] Pipeline completed. {len(files_out)} files created.")
        logger.info("Pipeline run end: ticker=%s files_created=%d", ticker, len(files_out))

    except Exception as e:  # noqa: BLE001
        logger.exception("Pipeline run errored for %s: %s", ticker, e)
        push(f"[{_ts()}] [ERROR] {e}")
        push(traceback.format_exc())
        # CRITICAL: emit a terminal marker as the LAST line so the UI's
        # rerun loop sees it and stops. Without this the page spins
        # forever because the last-line marker check would land on the
        # traceback instead of [ERROR] / [DONE].
        push(f"[{_ts()}] [DONE] Pipeline aborted (errored).")


def start_pipeline_thread(
    ticker: str,
    steps: set[str],
    form: str,
    limit: int,
    use_narrative: bool,
    force_refresh: bool = False,
) -> tuple[threading.Thread, queue.Queue, list]:
    out_q: queue.Queue = queue.Queue()
    files_out: list = []
    t = threading.Thread(
        target=run_pipeline_with_output,
        args=(ticker, steps, form, limit, use_narrative, out_q, files_out, force_refresh),
        daemon=True,
        name=f"pipeline-{ticker}-{form}",
    )
    t.start()
    logger.info(
        "Spawned thread '%s' (alive=%s) for ticker=%s form=%s",
        t.name, t.is_alive(), ticker, form,
    )
    return t, out_q, files_out


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
