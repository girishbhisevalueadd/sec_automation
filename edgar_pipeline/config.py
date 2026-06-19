"""Configuration for the edgar_pipeline.

Centralizes watchlist, output paths, EDGAR identity, and runtime defaults.
All output directories are auto-created on import so the rest of the
pipeline can assume they exist.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Watchlist - tickers processed by `fetch-all` / `run-all`
# ---------------------------------------------------------------------------
WATCHLIST: list[str] = ["AAPL", "MSFT", "INFY"]

# ---------------------------------------------------------------------------
# SEC EDGAR requires a contact identity header on every request
# ---------------------------------------------------------------------------
EDGAR_IDENTITY: dict[str, str] = {
    "name": "ValueAdd Research",
    "email": "analytics@valueadd.com",
}

# ---------------------------------------------------------------------------
# Filing fetch defaults
# ---------------------------------------------------------------------------
# Default form types pulled by the pipeline. The pipeline_runner can be
# asked for any subset of these via the UI multi-select or CLI --form
# option. Each form is pulled separately and merged into one combined
# Excel/Word/PDF report (period columns are tagged with the form_type).
#
# Note: 8-K and DEF 14A often have no XBRL financial-statement data;
# they're included so any disclosures they DO carry are stored, and so
# the run history records every filing for completeness. Empty
# statement extractions degrade gracefully (the sheet is just empty).
FORMS: list[str] = [
    "10-K",         # annual report
    "10-Q",         # quarterly report
    "10-K/A",       # 10-K amendment
    "10-Q/A",       # 10-Q amendment
    "20-F",         # foreign private issuer annual
    "6-K",          # foreign private issuer current report
    "8-K",          # current report (material events)
    "DEF 14A",      # proxy statement (exec comp, board info)
]
# Default subset used when the user picks "Default" in the UI or runs
# `python main.py run --form default`. These are the two highest-signal
# forms for financial analysis.
DEFAULT_RUN_FORMS: list[str] = ["10-K", "10-Q"]
FILING_LIMIT: int = 5

# Per-request politeness delay (seconds) to respect SEC rate limits
SEC_RATE_LIMIT_SLEEP: float = 0.5
RETRY_ATTEMPTS: int = 3
RETRY_DELAY: int = 5

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
OUTPUT_DIR: Path = BASE_DIR / "outputs"
EXCEL_DIR: Path = OUTPUT_DIR / "excel"
REPORTS_DIR: Path = OUTPUT_DIR / "reports"
DB_DIR: Path = OUTPUT_DIR / "db"
DB_PATH: Path = DB_DIR / "financials.db"
LOG_PATH: Path = OUTPUT_DIR / "pipeline.log"

AUTO_CREATE_DIRS: bool = True

if AUTO_CREATE_DIRS:
    for _d in (OUTPUT_DIR, EXCEL_DIR, REPORTS_DIR, DB_DIR):
        _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Optional Claude API key for narrative generation
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL: str = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Reporting metadata
# ---------------------------------------------------------------------------
# REPORT_AUTHOR appears after "Prepared by" in the Word + PDF cover page.
# REPORT_COMPANY is the full firm name used on covers, footers, and sidebars.
REPORT_AUTHOR: str = "Vivek Pol"
REPORT_COMPANY: str = "ValueAdd Research And Analytics Solutions LLP"
# Kept for backward compatibility - now points at the full company name.
REPORT_PREPARED_BY: str = REPORT_COMPANY
REPORT_FOOTER: str = f"Confidential | {REPORT_COMPANY}"
DATA_SOURCE_FOOTER: str = f"Source: SEC EDGAR via edgartools | {REPORT_COMPANY}"
# Logo embedded on the Word + PDF + Excel cover page and shown in the
# Streamlit sidebar. Auto-discovers .png / .jpg / .jpeg variants so the
# user can drop in whichever format they have on hand.
def _find_logo() -> Path | None:
    for ext in (".png", ".jpg", ".jpeg"):
        candidate = BASE_DIR / f"valueadd_logo{ext}"
        if candidate.exists():
            return candidate
    return None

LOGO_PATH: Path | None = _find_logo()

# ---------------------------------------------------------------------------
# Excel styling constants
# ---------------------------------------------------------------------------
COLOR_HEADER_FILL = "1D4E89"
COLOR_HEADER_TEXT = "FFFFFF"
COLOR_SUBTOTAL_FILL = "D6E4F0"
COLOR_ALT_ROW_FILL = "F8F9FA"

# Indian number system custom format (lakhs / crores)
INDIAN_NUMBER_FORMAT = (
    '[>=10000000]##","##","##","##0;[>=100000]##","##","##0;##,##0'
)
# International standard number format
INTL_NUMBER_FORMAT = "#,##0;(#,##0);-"
