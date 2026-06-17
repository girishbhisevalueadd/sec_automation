"""Normalize statements, build multi-period summary tables, and compute ratios."""

from __future__ import annotations

import logging
import re
from typing import Iterable

import numpy as np
import pandas as pd

import storage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Number system conversion helpers
# ---------------------------------------------------------------------------
def to_intl_millions(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) / 1_000_000


def to_indian_lakhs(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) / 100_000


# ---------------------------------------------------------------------------
# Concept matching
# ---------------------------------------------------------------------------
CONCEPT_MAP: dict[str, list[str]] = {
    # Income statement
    "revenue": [
        "Revenue", "Revenues", "Total revenue", "Net revenue",
        "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax",
    ],
    "cost_of_revenue": [
        "Cost of revenue", "Cost of goods sold", "Cost of sales",
        "CostOfRevenue", "CostOfGoodsSold", "CostOfGoodsAndServicesSold",
    ],
    "gross_profit": ["Gross margin", "Gross profit", "GrossProfit"],
    "operating_income": [
        "Operating income", "Income from operations",
        "OperatingIncomeLoss", "IncomeFromOperations",
    ],
    "interest_expense": ["Interest expense", "InterestExpense"],
    "net_income": [
        "Net income", "Net income (loss)", "Net earnings",
        "NetIncomeLoss", "ProfitLoss",
    ],
    # Balance sheet
    "current_assets": ["Total current assets", "Current assets", "AssetsCurrent"],
    "total_assets": ["Total assets", "Assets"],
    "current_liabilities": [
        "Total current liabilities", "Current liabilities", "LiabilitiesCurrent",
    ],
    "total_liabilities": ["Total liabilities", "Liabilities"],
    "stockholders_equity": [
        "Total stockholders' equity", "Stockholders' equity",
        "Total equity", "StockholdersEquity",
    ],
    "long_term_debt": ["Long-term debt", "LongTermDebt", "LongTermDebtNoncurrent"],
    "short_term_debt": [
        "Current portion of long-term debt", "Short-term borrowings",
        "DebtCurrent", "ShortTermBorrowings",
    ],
    "cash": [
        "Cash and cash equivalents", "Cash and equivalents",
        "CashAndCashEquivalentsAtCarryingValue", "Cash",
    ],
    # Cash flow
    "operating_cash_flow": [
        "Net cash from operations", "Net cash provided by operating activities",
        "Cash from operations", "NetCashProvidedByUsedInOperatingActivities",
    ],
    "capex": [
        "Additions to property and equipment", "Capital expenditures",
        "Purchases of property and equipment",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ],
    "investing_cash_flow": [
        "Net cash used in investing", "Net cash from investing activities",
        "NetCashProvidedByUsedInInvestingActivities",
    ],
    "financing_cash_flow": [
        "Net cash used in financing", "Net cash from financing activities",
        "NetCashProvidedByUsedInFinancingActivities",
    ],
}


def _humanize(concept: str) -> str:
    """Convert CamelCase XBRL concept to a human-readable label."""
    if not concept:
        return ""
    s = re.sub(r"(?<!^)(?=[A-Z])", " ", str(concept))
    return s.strip().title()


def _find_first_matching_row(df: pd.DataFrame, candidates: list[str]) -> pd.Series | None:
    """Find the first row whose concept matches any candidate."""
    if df is None or df.empty:
        return None
    concept_index = df.index.astype(str)
    for cand in candidates:
        # exact match
        for idx in concept_index:
            if cand.lower() == str(idx).lower():
                return df.loc[idx]
        # contains match
        for idx in concept_index:
            if cand.lower() in str(idx).lower():
                return df.loc[idx]
    return None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def normalize_statement(df: pd.DataFrame, stmt_type: str) -> pd.DataFrame:
    """Clean up an arbitrary statement DataFrame.

    - Trim/lowercase column names (preserving period columns as-is)
    - Coerce numeric values
    - Add a human-readable 'label' column
    - Sort columns (period) descending
    """
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()
    work.columns = [str(c).strip() for c in work.columns]

    # Coerce numeric where possible
    for col in work.columns:
        if work[col].dtype == object:
            work[col] = pd.to_numeric(work[col], errors="ignore")

    if "label" not in work.columns:
        work["label"] = [_humanize(str(i)) for i in work.index]

    # Sort period-like columns descending
    period_cols = [c for c in work.columns if c != "label" and re.search(r"\d{4}", str(c))]
    other_cols = [c for c in work.columns if c not in period_cols]
    period_cols_sorted = sorted(period_cols, reverse=True)
    work = work[other_cols + period_cols_sorted]
    return work


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------
def _add_intl_columns(df: pd.DataFrame) -> pd.DataFrame:
    """For every period column, add a sibling '<period> (USD M)' column."""
    if df.empty:
        return df
    out = df.copy()
    period_cols = [c for c in df.columns if c != "label"]
    for c in period_cols:
        out[f"{c} (USD M)"] = out[c].apply(to_intl_millions)
    return out


def build_summary_table(ticker: str, periods: int = 5) -> dict[str, pd.DataFrame]:
    """Pull stored statements from SQLite and return wide summary tables."""
    stmt_types = ["income", "balance", "cashflow", "debt"]
    summary: dict[str, pd.DataFrame] = {}
    for stmt in stmt_types:
        df = storage.load_statements(ticker, stmt)
        if not df.empty:
            # Limit to N most recent periods
            if len(df.columns) > periods:
                df = df.iloc[:, :periods]
            df = df.copy()
            df["label"] = [_humanize(str(i)) for i in df.index]
            # Move label to first column
            cols = ["label"] + [c for c in df.columns if c != "label"]
            df = df[cols]
        summary[stmt] = df
    return summary


# ---------------------------------------------------------------------------
# Ratio computation
# ---------------------------------------------------------------------------
def _row_values(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    """Return the matched concept's period series, or NaN series."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    work = df.drop(columns=["label"], errors="ignore")
    row = _find_first_matching_row(work, candidates)
    if row is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(row, errors="coerce")


def calculate_ratios(summary_dict: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Compute a small ratio panel: rows=metric, cols=period."""
    inc = summary_dict.get("income", pd.DataFrame())
    bal = summary_dict.get("balance", pd.DataFrame())
    cfs = summary_dict.get("cashflow", pd.DataFrame())

    revenue = _row_values(inc, CONCEPT_MAP["revenue"])
    cogs = _row_values(inc, CONCEPT_MAP["cost_of_revenue"])
    gross = _row_values(inc, CONCEPT_MAP["gross_profit"])
    op_inc = _row_values(inc, CONCEPT_MAP["operating_income"])
    net_inc = _row_values(inc, CONCEPT_MAP["net_income"])
    interest = _row_values(inc, CONCEPT_MAP["interest_expense"])

    cur_assets = _row_values(bal, CONCEPT_MAP["current_assets"])
    cur_liab = _row_values(bal, CONCEPT_MAP["current_liabilities"])
    total_assets = _row_values(bal, CONCEPT_MAP["total_assets"])
    equity = _row_values(bal, CONCEPT_MAP["stockholders_equity"])
    lt_debt = _row_values(bal, CONCEPT_MAP["long_term_debt"])
    st_debt = _row_values(bal, CONCEPT_MAP["short_term_debt"])

    op_cf = _row_values(cfs, CONCEPT_MAP["operating_cash_flow"])
    capex = _row_values(cfs, CONCEPT_MAP["capex"])

    # If gross isn't present try revenue - cogs
    if gross.empty and not revenue.empty and not cogs.empty:
        gross = revenue.sub(cogs, fill_value=np.nan)

    # Combined periods across all rows
    period_index = sorted(
        set().union(*[s.index for s in [revenue, net_inc, total_assets, equity, op_cf] if not s.empty]),
        reverse=True,
    )

    def safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
        a = a.reindex(period_index).astype(float)
        b = b.reindex(period_index).astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            return a.div(b.replace(0, np.nan))

    ratios: dict[str, pd.Series] = {}

    # Revenue growth YoY
    rev_indexed = revenue.reindex(period_index).astype(float)
    yoy = rev_indexed.copy() * np.nan
    for i in range(len(period_index) - 1):
        cur, prev = rev_indexed.iloc[i], rev_indexed.iloc[i + 1]
        if pd.notna(cur) and pd.notna(prev) and prev != 0:
            yoy.iloc[i] = (cur - prev) / abs(prev) * 100
    ratios["Revenue Growth YoY (%)"] = yoy

    ratios["Gross Margin (%)"] = safe_div(gross, revenue) * 100
    ratios["Operating Margin (%)"] = safe_div(op_inc, revenue) * 100
    ratios["Net Margin (%)"] = safe_div(net_inc, revenue) * 100
    ratios["EBITDA Margin (%) [proxy = OpInc/Rev]"] = safe_div(op_inc, revenue) * 100
    ratios["Current Ratio"] = safe_div(cur_assets, cur_liab)

    total_debt = lt_debt.reindex(period_index, fill_value=0).fillna(0) + st_debt.reindex(
        period_index, fill_value=0
    ).fillna(0)
    ratios["Debt / Equity"] = safe_div(total_debt, equity)
    ratios["Interest Coverage (x)"] = safe_div(op_inc, interest)
    ratios["Return on Equity (%)"] = safe_div(net_inc, equity) * 100
    ratios["Return on Assets (%)"] = safe_div(net_inc, total_assets) * 100

    fcf = op_cf.reindex(period_index, fill_value=np.nan).astype(float).sub(
        capex.reindex(period_index, fill_value=np.nan).astype(float).abs(), fill_value=np.nan
    )
    ratios["Free Cash Flow (USD)"] = fcf

    result = pd.DataFrame(ratios).T
    # Round nicely
    result = result.round(2)
    result.index.name = "Metric"
    return result
