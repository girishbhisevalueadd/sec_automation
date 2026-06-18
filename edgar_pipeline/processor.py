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


# ---------------------------------------------------------------------------
# Canonical statement order
# ---------------------------------------------------------------------------
# SQLite's pivot returns rows in alphabetical order. For an income statement
# that means "Cost of sales" comes before "Revenue" and "Net income" sits
# in the middle, which makes the Excel hard to read. These lists encode the
# natural top-to-bottom order of each statement; rows are matched by
# case-insensitive substring against their label/concept and assigned a
# rank. Unmatched rows fall to the end, preserving their original sequence.

INCOME_ORDER = [
    "revenue", "net sales", "total revenue", "sales",
    "cost of revenue", "cost of sales", "cost of goods", "cost of services",
    "gross profit", "gross margin",
    "research and development",
    "sales and marketing", "selling expense",
    "general and administrative", "selling, general",
    "total operating expense", "operating expense",
    "operating income", "income from operations", "operating loss",
    "other income", "other expense", "interest expense", "interest income",
    "income before", "pretax income", "pre-tax income", "earnings before",
    "provision for income tax", "income tax", "tax expense",
    "net income", "net earnings", "net profit", "profit/loss", "net loss",
    "basic (in dollars per share)", "diluted (in dollars per share)",
    "basic", "diluted",
    "weighted average shares", "weighted-average shares", "earnings per share",
]

BALANCE_ORDER = [
    # Current assets
    "cash and cash equivalents", "cash and equivalents", "cash",
    "marketable securities", "short-term investments",
    "accounts receivable", "receivables",
    "inventories", "inventory",
    "vendor non-trade receivables",
    "prepaid", "other current asset",
    "total current assets",
    # Non-current assets
    "property, plant", "property and equipment", "fixed assets",
    "operating lease right", "right-of-use",
    "goodwill", "intangible",
    "long-term investments", "equity investments",
    "deferred income tax", "deferred tax asset",
    "other long-term asset", "other non-current asset",
    "total non-current asset", "total noncurrent asset",
    "total assets",
    # Current liabilities
    "accounts payable",
    "accrued", "other current liabilit",
    "current portion of long-term debt", "short-term debt", "commercial paper",
    "current operating lease",
    "deferred revenue", "unearned revenue",
    "total current liabilit",
    # Non-current liabilities
    "term debt", "long-term debt", "long-term borrowings",
    "operating lease liabilit",
    "long-term income tax", "deferred tax liabilit",
    "other long-term liabilit", "other non-current liabilit",
    "total non-current liabilit", "total noncurrent liabilit",
    "total liabilities",
    "commitments and contingencies",
    # Equity
    "common stock", "paid-in capital", "additional paid-in",
    "retained earnings", "accumulated deficit",
    "accumulated other comprehensive",
    "treasury stock",
    "noncontrolling", "minority interest",
    "total stockholders' equity", "stockholders' equity",
    "total shareholders' equity", "shareholders' equity",
    "total equity",
    "total liabilities and equity",
    "total liabilities and stockholders",
    "total liabilities and shareholders",
]

CASHFLOW_ORDER = [
    # Opening cash
    "cash and cash equivalents, beginning",
    "cash, cash equivalents and restricted cash, beginning",
    "cash, cash equivalents, and restricted cash and cash equivalents, beginning",
    "cash, cash equivalents, and restricted cash, beginning",
    # Operating
    "net income", "net earnings",
    "depreciation", "amortization",
    "stock-based compensation", "share-based compensation",
    "deferred income tax", "deferred tax",
    "other operating",
    "accounts receivable", "inventories", "vendor non-trade receivables",
    "accounts payable", "other current and non-current asset",
    "other current asset",
    "other current and non-current liabilit", "other current liabilit",
    "other long-term liabilit",
    "deferred revenue", "unearned revenue",
    "net cash from operations", "net cash provided by operating",
    "cash generated by operating", "cash from operations",
    "operating activities",
    # Investing
    "purchases of investments", "purchases of marketable securities",
    "purchases of non-marketable securities",
    "proceeds from maturities", "sales of investments",
    "proceeds from sales of marketable securities",
    "proceeds from non-marketable securities",
    "additions to property and equipment",
    "payments for acquisition of property",
    "capital expenditure",
    "acquisition of companies", "business acquisitions",
    "payments made in connection with business acquisitions",
    "other investing",
    "net cash used in investing", "cash generated by investing",
    "cash generated by/(used in) investing", "cash used in investing",
    "investing activities",
    # Financing
    "proceeds from issuance of common stock", "common stock issued",
    "common stock repurchased", "repurchases of common stock",
    "common stock cash dividends",
    "payments for dividends", "payments for taxes related to net share settlement",
    "dividends paid", "dividends",
    "proceeds from issuance of term debt", "proceeds from issuance of debt",
    "repayments of term debt", "repayments of debt",
    "proceeds from/(repayments of) commercial paper",
    "proceeds from issuance (repayments) of commercial paper",
    "other financing",
    "net cash used in financing", "cash used in financing", "financing activities",
    # Reconciliation
    "effect of foreign exchange", "effect of exchange rate",
    "net change in cash",
    "increase/(decrease) in cash, cash equivalents, and restricted cash",
    "increase/(decrease) in cash, cash equivalents and restricted cash",
    "decrease in cash, cash equivalents and restricted cash",
    # Closing cash
    "cash, cash equivalents, and restricted cash and cash equivalents, ending",
    "cash, cash equivalents and restricted cash, ending",
    "cash and cash equivalents, end",
    # Supplemental
    "cash paid for income tax", "cash paid for interest",
    "other",
]

DEBT_ORDER = [
    "long-term debt",
    "long-term debt noncurrent",
    "short-term debt",
    "notes payable",
    "current portion of long-term debt",
    "debt current",
    "long-term debt maturity",
]


def _canonical_order(stmt_type: str) -> list[str]:
    return {
        "income": INCOME_ORDER,
        "balance": BALANCE_ORDER,
        "cashflow": CASHFLOW_ORDER,
        "debt": DEBT_ORDER,
    }.get(stmt_type, [])


def reorder_statement(df: pd.DataFrame, stmt_type: str) -> pd.DataFrame:
    """Reorder rows so they flow in natural statement order rather than
    alphabetical. Rows whose label/index doesn't match any canonical
    keyword are appended at the end in their original relative order.
    """
    if df is None or df.empty:
        return df
    order = _canonical_order(stmt_type)
    if not order:
        return df

    def _rank(label: str) -> int:
        low = str(label).lower()
        for i, kw in enumerate(order):
            if kw.lower() in low:
                return i
        return len(order) + 1_000  # unmatched -> end

    ranks = [(i, _rank(idx)) for i, idx in enumerate(df.index)]
    # Stable sort: equal ranks keep original order
    sorted_pairs = sorted(ranks, key=lambda p: (p[1], p[0]))
    new_order = [p[0] for p in sorted_pairs]
    return df.iloc[new_order]


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
            # Re-order rows so they flow top-to-bottom like a real
            # statement instead of alphabetically (SQLite pivot side
            # effect). See INCOME_ORDER / BALANCE_ORDER / CASHFLOW_ORDER.
            df = reorder_statement(df, stmt)
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
