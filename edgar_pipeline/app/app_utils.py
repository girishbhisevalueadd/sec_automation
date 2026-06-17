"""Shared helpers for the Streamlit app.

Path resolution, CSS loading, ticker validation, watchlist override,
download mime types, and other small utilities.

Lives in app/ so it imports nothing from streamlit pages.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Make the edgar_pipeline backend importable from any sub-page.
APP_DIR = Path(__file__).resolve().parent
PIPELINE_ROOT = APP_DIR.parent
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

ASSETS_DIR = APP_DIR / "assets"
STYLE_FILE = ASSETS_DIR / "style.css"
WATCHLIST_OVERRIDE_FILE = APP_DIR / "watchlist_overrides.json"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSS loader
# ---------------------------------------------------------------------------
def load_css() -> str:
    """Return the contents of style.css for injection via st.markdown."""
    try:
        css = STYLE_FILE.read_text(encoding="utf-8")
        logger.debug("load_css: %d bytes from %s", len(css), STYLE_FILE)
        return css
    except FileNotFoundError:
        logger.warning("load_css: style.css missing at %s", STYLE_FILE)
        return ""


def inject_css(st) -> None:
    css = load_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
        logger.debug("inject_css: injected %d bytes", len(css))


# ---------------------------------------------------------------------------
# Watchlist override (we don't modify config.py at runtime)
# ---------------------------------------------------------------------------
def _load_overrides() -> dict:
    if WATCHLIST_OVERRIDE_FILE.exists():
        try:
            return json.loads(WATCHLIST_OVERRIDE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_overrides(data: dict) -> None:
    WATCHLIST_OVERRIDE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_effective_watchlist() -> list[str]:
    """Return the union of config.WATCHLIST + any UI-added tickers - removed ones."""
    import config

    base = list(dict.fromkeys([t.upper() for t in config.WATCHLIST]))
    overrides = _load_overrides()
    added = [t.upper() for t in overrides.get("added", [])]
    removed = set(t.upper() for t in overrides.get("removed", []))
    union = [t for t in base + added if t not in removed]
    final = list(dict.fromkeys(union))
    logger.debug(
        "get_effective_watchlist: base=%s added=%s removed=%s -> %s",
        base, added, list(removed), final,
    )
    return final


def add_to_watchlist(ticker: str) -> tuple[bool, str]:
    """Validate ticker exists in EDGAR, then add to override file."""
    ticker = (ticker or "").strip().upper()
    logger.info("add_to_watchlist: ticker=%r", ticker)
    if not ticker:
        return False, "Empty ticker"
    if ticker in get_effective_watchlist():
        logger.info("add_to_watchlist: %s already present, skipping", ticker)
        return False, f"{ticker} already in watchlist"

    # Validate via edgartools - make sure identity is set
    try:
        import config
        from edgar import Company, set_identity
        set_identity(f"{config.EDGAR_IDENTITY['name']} {config.EDGAR_IDENTITY['email']}")
        c = Company(ticker)
        name = getattr(c, "name", None) or getattr(c, "company_name", "") or ""
        if not name:
            logger.warning("add_to_watchlist: %s not found on EDGAR", ticker)
            return False, f"{ticker} not found on EDGAR"
    except Exception as e:  # noqa: BLE001
        logger.exception("add_to_watchlist: EDGAR lookup failed for %s", ticker)
        return False, f"Lookup failed: {e}"

    data = _load_overrides()
    added = list(dict.fromkeys([*data.get("added", []), ticker]))
    removed = [t for t in data.get("removed", []) if t != ticker]
    data["added"] = added
    data["removed"] = removed
    _save_overrides(data)
    logger.info("add_to_watchlist: persisted %s (%s)", ticker, name)
    return True, f"Added {ticker} ({name})"


def remove_from_watchlist(ticker: str) -> tuple[bool, str]:
    ticker = (ticker or "").strip().upper()
    logger.info("remove_from_watchlist: ticker=%r", ticker)
    if not ticker:
        return False, "Empty ticker"
    if ticker not in get_effective_watchlist():
        logger.info("remove_from_watchlist: %s not in current watchlist", ticker)
        return False, f"{ticker} not in watchlist"
    data = _load_overrides()
    added = [t for t in data.get("added", []) if t != ticker]
    removed = list(dict.fromkeys([*data.get("removed", []), ticker]))
    data["added"] = added
    data["removed"] = removed
    _save_overrides(data)
    logger.info("remove_from_watchlist: persisted removal of %s", ticker)
    return True, f"Removed {ticker}"


# ---------------------------------------------------------------------------
# File listing / mime
# ---------------------------------------------------------------------------
def get_mime_type(suffix: str) -> str:
    return {
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".zip": "application/zip",
        ".log": "text/plain",
    }.get(suffix.lower(), "application/octet-stream")


def list_output_files(directory: Path, extension: str | None = None) -> list[Path]:
    if not directory.exists():
        logger.debug("list_output_files: %s does not exist", directory)
        return []
    if extension:
        files = sorted(directory.glob(f"*{extension}"), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        files = sorted([p for p in directory.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    logger.debug("list_output_files: %s ext=%s -> %d files", directory.name, extension, len(files))
    return files


def parse_output_filename(path: Path) -> dict:
    """Parse TICKER_FORM_YYYYMMDD.ext -> components."""
    stem = path.stem
    parts = stem.split("_")
    ticker = parts[0] if parts else ""
    form = parts[1] if len(parts) > 1 else ""
    date_str = parts[2] if len(parts) > 2 else ""
    try:
        created = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        created = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    return {
        "ticker": ticker,
        "form": form,
        "created": created,
        "size_bytes": path.stat().st_size,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime),
    }


# ---------------------------------------------------------------------------
# Activity feed (parses pipeline.log tail)
# ---------------------------------------------------------------------------
def tail_log(n: int = 100) -> list[str]:
    import config
    path = config.LOG_PATH
    if not path.exists():
        logger.debug("tail_log: %s does not exist yet", path)
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        tail = lines[-n:]
        logger.debug("tail_log: returning last %d/%d lines of %s", len(tail), len(lines), path.name)
        return tail
    except OSError as e:
        logger.warning("tail_log: read failed for %s: %s", path, e)
        return []


def classify_log_line(line: str) -> str:
    low = line.lower()
    if "error" in low or "failed" in low or "❌" in line:
        return "err"
    if "warning" in low or "warn" in low:
        return "warn"
    if "saved" in low or "done" in low or "success" in low or "✓" in line:
        return "ok"
    if "info" in low:
        return "info"
    return "muted"


# ---------------------------------------------------------------------------
# Run history parsing
# ---------------------------------------------------------------------------
def extract_recent_runs(max_runs: int = 10) -> list[dict]:
    """Best-effort: scan pipeline.log for 'Pipeline started/finished' markers."""
    lines = tail_log(2000)
    runs: list[dict] = []
    current: dict | None = None
    for raw in lines:
        line = raw.strip()
        if "[START] Pipeline" in line or "Pipeline started" in line:
            if current:
                runs.append(current)
            current = {"start": line[:19], "lines": [line], "status": "running"}
        elif current is not None:
            current["lines"].append(line)
            if "[DONE]" in line or "completed successfully" in line.lower():
                current["status"] = "success"
                current["end"] = line[:19]
            elif "[ERROR]" in line or "failed" in line.lower():
                current["status"] = "failed"
                current["end"] = line[:19]
    if current:
        runs.append(current)
    return list(reversed(runs))[:max_runs]
