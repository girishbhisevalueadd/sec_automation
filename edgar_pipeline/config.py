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
FORMS: list[str] = ["10-K", "10-Q"]
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
REPORT_PREPARED_BY: str = EDGAR_IDENTITY["name"]
REPORT_FOOTER: str = "Confidential | ValueAdd Research"
DATA_SOURCE_FOOTER: str = "Source: SEC EDGAR via edgartools | ValueAdd Research"

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
