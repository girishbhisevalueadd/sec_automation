"""SQLite persistence layer for the edgar_pipeline.

Two tables: `filings` (one row per ticker/form/period) and
`financial_data` (long-format line items linked back to `filings.id`).
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable

import pandas as pd

import config

logger = logging.getLogger(__name__)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS filings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        form_type TEXT NOT NULL,
        period TEXT NOT NULL,
        filed_at TEXT,
        fetched_at TEXT,
        raw_url TEXT,
        UNIQUE(ticker, form_type, period)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filing_id INTEGER NOT NULL,
        stmt_type TEXT NOT NULL,
        concept TEXT,
        value REAL,
        unit TEXT,
        period TEXT,
        FOREIGN KEY(filing_id) REFERENCES filings(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_findata_filing ON financial_data(filing_id)",
    "CREATE INDEX IF NOT EXISTS idx_findata_stmt ON financial_data(stmt_type)",
    "CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker)",
]


@contextmanager
def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't already exist."""
    with get_connection() as conn:
        for stmt in SCHEMA:
            conn.execute(stmt)
    logger.info("SQLite schema ready at %s", config.DB_PATH)


def filing_exists(ticker: str, form_type: str, period: str) -> bool:
    if not period:
        return False
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM filings WHERE ticker=? AND form_type=? AND period=?",
            (ticker.upper(), form_type, period),
        ).fetchone()
    return row is not None


def _melt_statement(df: pd.DataFrame, stmt_type: str) -> list[tuple]:
    """Convert a wide statement DataFrame to long-format rows.

    Returns list of (stmt_type, concept, value, unit, period) tuples.
    Best-effort — gracefully handles arbitrary edgartools shapes.
    """
    if df is None or df.empty:
        return []

    work = df.copy()
    # Identify the concept column
    concept_col: str | None = None
    for candidate in ("concept", "Concept", "label", "Label", "line_item"):
        if candidate in work.columns:
            concept_col = candidate
            break
    if concept_col is None:
        # The concept is on the index - flatten it
        work = work.reset_index()
        concept_col = work.columns[0]

    # Only keep period-like columns (e.g. "2025-06-30 (FY)" or "2025-06-30")
    import re as _re
    period_cols = [c for c in work.columns if c != concept_col and _re.search(r"\d{4}", str(c))]
    if not period_cols:
        period_cols = [c for c in work.columns if c != concept_col]
    rows: list[tuple] = []
    for _, r in work.iterrows():
        concept_val = str(r[concept_col]) if pd.notna(r[concept_col]) else ""
        for pcol in period_cols:
            val = r[pcol]
            try:
                fval = float(val) if val not in (None, "", "—") else None
            except (TypeError, ValueError):
                fval = None
            rows.append((stmt_type, concept_val, fval, None, str(pcol)))
    return rows


def save_filing(filing_dict: dict) -> int:
    """Upsert a filing record and its statement line items. Returns filing_id."""
    init_db()
    ticker = filing_dict["ticker"].upper()
    form_type = filing_dict["form_type"]
    period = str(filing_dict.get("period_of_report") or "")
    filed_at = str(filing_dict.get("filed_at") or "")
    fetched_at = filing_dict.get("fetched_at") or datetime.utcnow().isoformat(timespec="seconds")
    raw_url = filing_dict.get("raw_filing_url", "")

    with get_connection() as conn:
        # Upsert filings row
        conn.execute(
            """
            INSERT INTO filings (ticker, form_type, period, filed_at, fetched_at, raw_url)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, form_type, period) DO UPDATE SET
              filed_at=excluded.filed_at,
              fetched_at=excluded.fetched_at,
              raw_url=excluded.raw_url
            """,
            (ticker, form_type, period, filed_at, fetched_at, raw_url),
        )
        row = conn.execute(
            "SELECT id FROM filings WHERE ticker=? AND form_type=? AND period=?",
            (ticker, form_type, period),
        ).fetchone()
        filing_id = int(row["id"])

        # Wipe old line items for this filing then re-insert
        conn.execute("DELETE FROM financial_data WHERE filing_id=?", (filing_id,))

        all_rows: list[tuple] = []
        all_rows += [
            (filing_id, *r) for r in _melt_statement(filing_dict.get("income_statement"), "income")
        ]
        all_rows += [
            (filing_id, *r) for r in _melt_statement(filing_dict.get("balance_sheet"), "balance")
        ]
        all_rows += [
            (filing_id, *r) for r in _melt_statement(filing_dict.get("cash_flow_statement"), "cashflow")
        ]
        all_rows += [
            (filing_id, *r) for r in _melt_statement(filing_dict.get("debt_facts"), "debt")
        ]
        if all_rows:
            conn.executemany(
                """
                INSERT INTO financial_data (filing_id, stmt_type, concept, value, unit, period)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                all_rows,
            )
    logger.info("Saved filing %s %s %s (id=%s, lines=%d)",
                ticker, form_type, period, filing_id, len(all_rows))
    return filing_id


def load_statements(
    ticker: str,
    stmt_type: str,
    periods: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return a wide DataFrame: rows=concept, columns=period."""
    init_db()
    params: list = [ticker.upper(), stmt_type]
    sql = (
        "SELECT f.period AS filing_period, fd.concept, fd.value, fd.period "
        "FROM financial_data fd "
        "JOIN filings f ON f.id = fd.filing_id "
        "WHERE f.ticker = ? AND fd.stmt_type = ?"
    )
    if periods:
        plist = list(periods)
        sql += f" AND fd.period IN ({','.join('?' for _ in plist)})"
        params.extend(plist)

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        return df

    # Pivot to concept x period
    pivot = df.pivot_table(
        index="concept", columns="period", values="value", aggfunc="last"
    )
    # Sort columns (periods) descending
    try:
        pivot = pivot[sorted(pivot.columns, reverse=True)]
    except Exception:  # noqa: BLE001
        pass
    return pivot


def get_filing_history(ticker: str) -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT ticker, form_type, period, filed_at, fetched_at, raw_url "
            "FROM filings WHERE ticker=? ORDER BY filed_at DESC",
            conn,
            params=(ticker.upper(),),
        )


def db_status() -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT ticker, form_type, COUNT(*) AS filings, "
            "MIN(period) AS earliest, MAX(period) AS latest "
            "FROM filings GROUP BY ticker, form_type ORDER BY ticker, form_type",
            conn,
        )
