"""CLI entry point for the edgar_pipeline.

Usage examples:
  python main.py fetch --ticker AAPL --form 10-K --limit 5
  python main.py fetch-all
  python main.py build --ticker AAPL
  python main.py report --ticker AAPL --format word
  python main.py run --ticker AAPL
  python main.py run-all
  python main.py history --ticker AAPL
  python main.py status
  python main.py schedule
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import click

import config

# Configure logging once
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    handlers=[logging.FileHandler(config.LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("edgar_pipeline")


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _print(msg: str) -> None:
    click.echo(f"[{_ts()}] {msg}")


# ---------------------------------------------------------------------------
# Pipeline primitives
# ---------------------------------------------------------------------------
def do_fetch(ticker: str, form: str, limit: int, skip_existing: bool = True) -> int:
    from fetcher import fetch_company_filings
    import storage

    storage.init_db()
    _print(f"Fetching {form} filings for {ticker} (limit={limit})...")
    filings = fetch_company_filings(ticker, form=form, limit=limit)
    saved = 0
    for fdict in filings:
        period = str(fdict.get("period_of_report") or "")
        if skip_existing and storage.filing_exists(ticker, form, period):
            _print(f"  - already stored {ticker} {form} {period}, skipping")
            continue
        try:
            storage.save_filing(fdict)
            saved += 1
            _print(f"  + saved {ticker} {form} {period}")
        except Exception as e:  # noqa: BLE001
            _print(f"  ! save failed for {ticker} {form} {period}: {e}")
    _print(f"Done fetch: {ticker} {form} -> {saved} new, {len(filings) - saved} skipped/duplicate")
    return saved


def do_build(ticker: str, form_type: str = "10-K") -> Path | None:
    import processor
    import model_builder

    _print(f"Building Excel model for {ticker}...")
    summary = processor.build_summary_table(ticker)
    if all(df.empty for df in summary.values()):
        _print(f"  ! no stored data for {ticker} - run fetch first")
        return None
    ratios = processor.calculate_ratios(summary)
    out_path = model_builder.build_excel_model(ticker, summary, ratios, form_type=form_type)
    _print(f"  + Excel saved -> {out_path}")
    return out_path


def do_report(ticker: str, fmt: str, form_type: str = "10-K") -> list[Path]:
    import processor
    import report_writer
    import narrative as narrative_mod

    _print(f"Generating {fmt} report for {ticker}...")
    summary = processor.build_summary_table(ticker)
    if all(df.empty for df in summary.values()):
        _print(f"  ! no stored data for {ticker} - run fetch first")
        return []
    ratios = processor.calculate_ratios(summary)
    narrative_text = narrative_mod.generate_narrative(ticker, summary, ratios)

    outputs: list[Path] = []
    word_path = None
    if fmt in ("word", "both", "pdf"):
        word_path = report_writer.build_word_report(
            ticker, summary, ratios, narrative_text=narrative_text, form_type=form_type
        )
        if fmt in ("word", "both"):
            outputs.append(word_path)
            _print(f"  + Word saved -> {word_path}")
    if fmt in ("pdf", "both") and word_path is not None:
        try:
            pdf_path = report_writer.build_pdf_report(word_path)
            outputs.append(pdf_path)
            _print(f"  + PDF saved -> {pdf_path}")
        except Exception as e:  # noqa: BLE001
            _print(f"  ! PDF generation failed: {e}")
    return outputs


def do_run(ticker: str, form: str = "10-K", limit: int = 5) -> dict:
    result = {"ticker": ticker, "fetched": 0, "excel": None, "word": None, "pdf": None, "error": None}
    try:
        result["fetched"] = do_fetch(ticker, form, limit)
        excel_path = do_build(ticker, form_type=form)
        result["excel"] = str(excel_path) if excel_path else None
        report_paths = do_report(ticker, "both", form_type=form)
        for p in report_paths:
            if p.suffix.lower() == ".docx":
                result["word"] = str(p)
            elif p.suffix.lower() == ".pdf":
                result["pdf"] = str(p)
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
        logger.exception("Pipeline failed for %s", ticker)
    return result


def run_full_pipeline_for_watchlist() -> dict:
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    for ticker in config.WATCHLIST:
        _print(f"=== {ticker} ===")
        res = do_run(ticker, form="10-K", limit=config.FILING_LIMIT)
        if res.get("error"):
            failed.append((ticker, res["error"]))
        else:
            succeeded.append(ticker)
    _print(f"=== Summary: {len(succeeded)} succeeded, {len(failed)} failed ===")
    for t, err in failed:
        _print(f"  FAILED {t}: {err}")
    return {"succeeded": succeeded, "failed": failed}


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
@click.group()
def cli():
    """SEC EDGAR financial data pipeline."""


@cli.command("fetch")
@click.option("--ticker", required=True, help="Ticker symbol e.g. AAPL")
@click.option("--form", default="10-K", show_default=True)
@click.option("--limit", default=config.FILING_LIMIT, show_default=True, type=int)
def cmd_fetch(ticker: str, form: str, limit: int):
    """Fetch and store filings for one ticker."""
    do_fetch(ticker.upper(), form, limit)


@cli.command("fetch-all")
def cmd_fetch_all():
    """Fetch every ticker in WATCHLIST for every FORM in config."""
    for ticker in config.WATCHLIST:
        for form in config.FORMS:
            do_fetch(ticker, form, config.FILING_LIMIT)


@cli.command("build")
@click.option("--ticker", required=True)
@click.option("--form", default="10-K", show_default=True)
def cmd_build(ticker: str, form: str):
    """Build Excel model from stored data."""
    do_build(ticker.upper(), form_type=form)


@cli.command("report")
@click.option("--ticker", required=True)
@click.option("--format", "fmt", type=click.Choice(["word", "pdf", "both"]), default="word", show_default=True)
@click.option("--form", default="10-K", show_default=True)
def cmd_report(ticker: str, fmt: str, form: str):
    """Generate Word and/or PDF research report."""
    do_report(ticker.upper(), fmt, form_type=form)


@cli.command("run")
@click.option("--ticker", required=True)
@click.option("--form", default="10-K", show_default=True)
@click.option("--limit", default=config.FILING_LIMIT, show_default=True, type=int)
def cmd_run(ticker: str, form: str, limit: int):
    """Full pipeline: fetch -> store -> Excel -> report (Word + PDF)."""
    res = do_run(ticker.upper(), form=form, limit=limit)
    _print(f"Run result: {res}")


@cli.command("run-all")
def cmd_run_all():
    """Full pipeline for every ticker in WATCHLIST."""
    summary = run_full_pipeline_for_watchlist()
    _print(f"Watchlist summary: {summary}")


@cli.command("history")
@click.option("--ticker", required=True)
def cmd_history(ticker: str):
    """Show filing history stored in SQLite for a ticker."""
    import storage
    df = storage.get_filing_history(ticker.upper())
    if df.empty:
        _print(f"No filings stored for {ticker}.")
        return
    _print(f"Filings for {ticker.upper()}:")
    click.echo(df.to_string(index=False))


@cli.command("status")
def cmd_status():
    """Show what's currently in the database."""
    import storage
    df = storage.db_status()
    if df.empty:
        _print("Database is empty - run `fetch` or `run` first.")
        return
    _print("Database status:")
    click.echo(df.to_string(index=False))
    _print(f"Excel files in {config.EXCEL_DIR}: {len(list(config.EXCEL_DIR.glob('*.xlsx')))}")
    _print(f"Reports in {config.REPORTS_DIR}: {len(list(config.REPORTS_DIR.glob('*')))}")


@cli.command("schedule")
def cmd_schedule():
    """Start the weekly scheduler (Mon 07:00)."""
    import scheduler
    scheduler.start()


if __name__ == "__main__":
    cli()
