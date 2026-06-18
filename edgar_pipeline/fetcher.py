"""Fetch SEC filings via the free `edgartools` library (5.x API).

Each filing is normalized into a dict with the four financial statements
(income, balance, cash flow, debt facts) as DataFrames and metadata
useful for downstream storage / Excel / report generation.

API path used (edgartools >= 5.0):
    company  = Company(ticker)
    filings  = company.get_filings(form="10-K")
    filing   = filings.latest(N)
    xbrl     = filing.xbrl()              # <-- a method now
    income   = xbrl.statements.income_statement().to_dataframe()
    balance  = xbrl.statements.balance_sheet().to_dataframe()
    cashflow = xbrl.statements.cash_flow_statement().to_dataframe()
    facts_df = xbrl.facts.search_facts("LongTermDebt")
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

import pandas as pd

from edgar import Company, set_identity

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity must be set before ANY Company() call (SEC requirement).
# ---------------------------------------------------------------------------
_IDENTITY_SET = False


def _ensure_identity() -> None:
    global _IDENTITY_SET
    if _IDENTITY_SET:
        return
    identity_string = f"{config.EDGAR_IDENTITY['name']} {config.EDGAR_IDENTITY['email']}"
    set_identity(identity_string)
    _IDENTITY_SET = True
    logger.info("EDGAR identity set: %s", identity_string)


# ---------------------------------------------------------------------------
# Statement extraction
# ---------------------------------------------------------------------------
def _statement_to_dataframe(xbrl: Any, kind: str) -> pd.DataFrame:
    """Return a clean DataFrame for one of: income / balance / cashflow.

    The XBRL output has dimension/segment rows we strip out so that only
    top-line consolidated values remain. Index = standardized label.
    """
    try:
        statements = xbrl.statements
        if kind == "income":
            stmt = statements.income_statement()
        elif kind == "balance":
            stmt = statements.balance_sheet()
        elif kind == "cashflow":
            stmt = statements.cash_flow_statement()
        else:
            return pd.DataFrame()
        raw = stmt.to_dataframe()
    except Exception as e:  # noqa: BLE001
        logger.warning("%s statement extraction failed: %s", kind, e)
        return pd.DataFrame()

    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    # Drop dimension breakdown rows - we want consolidated only
    if "dimension" in df.columns:
        df = df[df["dimension"] != True]  # noqa: E712
    if "abstract" in df.columns:
        df = df[df["abstract"] != True]  # noqa: E712

    label_col = "label" if "label" in df.columns else ("concept" if "concept" in df.columns else None)
    if label_col is None:
        return pd.DataFrame()

    # Period columns look like "2025-06-30 (FY)" - keep those + the label
    period_cols = [c for c in df.columns if re.search(r"\d{4}-\d{2}-\d{2}", str(c))]
    if not period_cols:
        # fall back: any numeric-looking column
        period_cols = [c for c in df.columns if df[c].dtype.kind in "fi" and c not in ("level", "weight", "preferred_sign")]
    if not period_cols:
        return pd.DataFrame()

    keep = [label_col] + period_cols
    out = df[keep].copy()
    # Deduplicate rows with the same label (keep first non-null version)
    out = out.groupby(label_col, as_index=False, sort=False).first()
    out = out.set_index(label_col)
    out.index.name = "concept"
    # Normalize period column names - strip "(FY)" / "(Q1)" suffix so
    # income, balance, and cash flow share the same period keys.
    rename_map: dict[str, str] = {}
    for c in period_cols:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", str(c))
        if m:
            rename_map[c] = m.group(1)
    out = out.rename(columns=rename_map)
    # Sort columns: most recent period first
    out = out[sorted(out.columns.tolist(), reverse=True)]
    return out


def _extract_debt_facts(xbrl: Any) -> pd.DataFrame:
    """Pull debt-related XBRL facts. Returns empty DF on failure."""
    keywords = ["LongTermDebt", "NotesPayable", "DebtCurrent", "LongTermDebtMaturity"]
    return _facts_pivot(xbrl, keywords, label="debt_facts")


def _facts_pivot(xbrl: Any, keywords: list[str], *, label: str = "facts") -> pd.DataFrame:
    """Generic: search_facts for each keyword, combine, dedupe, pivot
    concept x period. Returns empty DataFrame if nothing matches.
    """
    frames: list[pd.DataFrame] = []
    try:
        facts = xbrl.facts
    except Exception as e:  # noqa: BLE001
        logger.debug("xbrl.facts unavailable (%s): %s", label, e)
        return pd.DataFrame()

    for kw in keywords:
        try:
            df = facts.search_facts(kw)
            if isinstance(df, pd.DataFrame) and not df.empty:
                frames.append(df)
        except Exception as e:  # noqa: BLE001
            logger.debug("facts.search_facts(%s) failed [%s]: %s", kw, label, e)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=[c for c in combined.columns if c in ("concept", "value", "period_end", "period_instant")]
    )

    # Coalesce period_end (duration facts) and period_instant (point-in-time
    # facts like balance sheet items / debt maturity / lease commitments).
    if "period" not in combined.columns:
        pe = combined.get("period_end") if "period_end" in combined.columns else None
        pi = combined.get("period_instant") if "period_instant" in combined.columns else None
        if pe is not None and pi is not None:
            combined["period"] = pe.fillna(pi)
        elif pe is not None:
            combined["period"] = pe
        elif pi is not None:
            combined["period"] = pi

    if "period" in combined.columns and "numeric_value" in combined.columns and "concept" in combined.columns:
        try:
            pivot = combined.pivot_table(
                index="concept", columns="period", values="numeric_value", aggfunc="last"
            )
            # Drop NaN-column placeholders if any sneak in
            pivot = pivot.loc[:, pivot.columns.notna()]
            if len(pivot.columns) > 0:
                pivot = pivot[sorted(pivot.columns, reverse=True, key=str)]
            pivot.index.name = "concept"
            return pivot
        except Exception as e:  # noqa: BLE001
            logger.debug("%s pivot failed: %s", label, e)
    # Pivot didn't work - return empty rather than the raw facts table
    # (the raw table has dozens of XBRL metadata columns the Excel sheet
    # would try to render as periods).
    logger.debug("%s: no usable period column; returning empty", label)
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Richer concept-family extractors
# ---------------------------------------------------------------------------
def _extract_segment_data(xbrl: Any) -> pd.DataFrame:
    """Return revenue/cost rows broken down by product, segment, geography
    - the dimension rows the main statements throw away. Index is the
    human label, columns are periods.
    """
    try:
        raw = xbrl.statements.income_statement().to_dataframe()
    except Exception as e:  # noqa: BLE001
        logger.debug("segment extraction failed: %s", e)
        return pd.DataFrame()
    if raw is None or raw.empty or "dimension" not in raw.columns:
        return pd.DataFrame()

    dim = raw[raw["dimension"] == True].copy()  # noqa: E712
    if dim.empty:
        return pd.DataFrame()

    # Prepend the dimension axis short-name to disambiguate identical labels
    if "dimension_axis" in dim.columns:
        def _short(axis: object) -> str:
            s = str(axis or "").split(":")[-1]
            return s.replace("Axis", "").strip()
        dim["label_full"] = dim.apply(
            lambda r: f"{_short(r.get('dimension_axis'))}: {r.get('label','')}".strip(": "),
            axis=1,
        )
    else:
        dim["label_full"] = dim.get("label", "")

    period_cols = [c for c in dim.columns if re.search(r"\d{4}-\d{2}-\d{2}", str(c))]
    if not period_cols:
        return pd.DataFrame()

    # Normalize period headers (strip "(FY)" etc)
    rename_map = {c: re.search(r"(\d{4}-\d{2}-\d{2})", str(c)).group(1) for c in period_cols}
    out = dim[["label_full"] + period_cols].copy()
    out = out.rename(columns=rename_map)
    out = out.drop_duplicates(subset=["label_full"])
    out = out.set_index("label_full")
    out.index.name = "concept"
    out = out[sorted(out.columns.tolist(), reverse=True)]
    return out


def _extract_debt_maturity(xbrl: Any) -> pd.DataFrame:
    """Long-term debt maturity ladder: 1Y / 2Y / 3Y / 4Y / 5Y / thereafter."""
    keywords = [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
        "LongTermDebtMaturities",
    ]
    return _facts_pivot(xbrl, keywords, label="debt_maturity")


def _extract_lease_schedule(xbrl: Any) -> pd.DataFrame:
    """Operating + finance lease payment commitments by year."""
    keywords = [
        "LesseeOperatingLeaseLiabilityPaymentsDueNextTwelveMonths",
        "LesseeOperatingLeaseLiabilityPaymentsDueYearTwo",
        "LesseeOperatingLeaseLiabilityPaymentsDueYearThree",
        "LesseeOperatingLeaseLiabilityPaymentsDueYearFour",
        "LesseeOperatingLeaseLiabilityPaymentsDueYearFive",
        "LesseeOperatingLeaseLiabilityPaymentsDueAfterYearFive",
        "LesseeOperatingLeaseLiabilityPaymentsDue",
        "FinanceLeaseLiabilityPaymentsDueNextTwelveMonths",
        "FinanceLeaseLiabilityPaymentsDueYearTwo",
        "FinanceLeaseLiabilityPaymentsDueYearThree",
        "FinanceLeaseLiabilityPaymentsDueYearFour",
        "FinanceLeaseLiabilityPaymentsDueYearFive",
        "FinanceLeaseLiabilityPaymentsDueAfterYearFive",
        "OperatingLeaseRightOfUseAsset",
        "OperatingLeaseLiabilityCurrent",
        "OperatingLeaseLiabilityNoncurrent",
    ]
    return _facts_pivot(xbrl, keywords, label="leases")


def _extract_sbc_data(xbrl: Any) -> pd.DataFrame:
    """Stock-based compensation: expense, options outstanding, RSUs."""
    keywords = [
        "ShareBasedCompensation",
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsGrantsInPeriodGross",
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsGrantsInPeriod",
        "EmployeeServiceShareBasedCompensationNonvestedAwardsTotalCompensationCostNotYetRecognized",
    ]
    return _facts_pivot(xbrl, keywords, label="sbc")


def _extract_tax_detail(xbrl: Any) -> pd.DataFrame:
    """Income tax: current vs. deferred, federal/foreign/state, reconciliation."""
    keywords = [
        "CurrentFederalTaxExpenseBenefit",
        "CurrentForeignTaxExpenseBenefit",
        "CurrentStateAndLocalTaxExpenseBenefit",
        "DeferredFederalIncomeTaxExpenseBenefit",
        "DeferredForeignIncomeTaxExpenseBenefit",
        "DeferredStateAndLocalIncomeTaxExpenseBenefit",
        "IncomeTaxReconciliationIncomeTaxExpenseBenefitAtFederalStatutoryIncomeTaxRate",
        "IncomeTaxReconciliationForeignIncomeTaxRateDifferential",
        "EffectiveIncomeTaxRateContinuingOperations",
    ]
    return _facts_pivot(xbrl, keywords, label="tax_detail")


def _extract_filing_text_section(filing: Any, item_label: str, max_chars: int | None = None) -> str:
    """Find a 10-K item by header (e.g. 'Item 1A.', 'Item 7.') and return
    its FULL concatenated text. Stops at the next 'Item N.' header.
    Returns empty string on failure.

    max_chars=None means no cap - extract the entire section verbatim.
    The user explicitly asked for no caps on text extraction.
    """
    try:
        secs = filing.sections() if callable(getattr(filing, "sections", None)) else filing.sections
    except Exception as e:  # noqa: BLE001
        logger.debug("filing.sections() failed: %s", e)
        return ""
    if not isinstance(secs, list):
        return ""

    label_norm = item_label.lower().strip().rstrip(".")
    next_pat = re.compile(r"^\s*item\s+\d+[a-z]?\.\s+", re.IGNORECASE)

    buf: list[str] = []
    capturing = False
    for s in secs:
        if not isinstance(s, str) or not s.strip():
            continue
        low = s.lower().strip()
        if capturing:
            # Stop when we hit the next "Item N." header (but not the same one)
            if next_pat.match(s) and label_norm not in low:
                break
            buf.append(s)
            if max_chars is not None and sum(len(b) for b in buf) > max_chars:
                break
        else:
            if low.startswith(label_norm):
                capturing = True
                buf.append(s)

    out = "\n\n".join(buf)
    return out[:max_chars] if max_chars is not None else out


def extract_risk_factors_text(filing: Any) -> str:
    """Return Item 1A. Risk Factors text (full length, no truncation)."""
    return _extract_filing_text_section(filing, "Item 1A.")


def extract_mda_text(filing: Any) -> str:
    """Return Item 7. MD&A text (full length, no truncation)."""
    return _extract_filing_text_section(filing, "Item 7.")


# ---------------------------------------------------------------------------
# Retry-wrapped filings list fetch
# ---------------------------------------------------------------------------
def _fetch_filings_with_retry(ticker: str, form: str, limit: int):
    last_exc: Exception | None = None
    for attempt in range(1, config.RETRY_ATTEMPTS + 1):
        try:
            company = Company(ticker)
            filings = company.get_filings(form=form)
            latest = filings.latest(limit) if hasattr(filings, "latest") else filings.head(limit)
            if latest is None:
                return []
            # latest(1) may return a single Filing; latest(N>1) returns iterable
            if not hasattr(latest, "__iter__"):
                latest = [latest]
            return list(latest)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            logger.warning(
                "Attempt %d/%d for %s %s failed: %s",
                attempt, config.RETRY_ATTEMPTS, ticker, form, e,
            )
            if attempt < config.RETRY_ATTEMPTS:
                time.sleep(config.RETRY_DELAY)
    logger.error("All retries exhausted for %s %s: %s", ticker, form, last_exc)
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_company_filings(ticker: str, form: str = "10-K", limit: int = 5) -> list[dict]:
    """Fetch recent filings for a ticker and return parsed dicts.

    Each dict contains: ticker, form_type, period_of_report, filed_at,
    fetched_at, income_statement, balance_sheet, cash_flow_statement,
    debt_facts, raw_filing_url.
    """
    _ensure_identity()
    logger.info("Fetching %s filings for %s (limit=%d)", form, ticker, limit)

    filings = _fetch_filings_with_retry(ticker, form, limit)
    results: list[dict] = []

    for filing in filings:
        try:
            time.sleep(config.SEC_RATE_LIMIT_SLEEP)

            period = str(getattr(filing, "period_of_report", "") or "")
            filed_at = str(getattr(filing, "filing_date", "") or "")
            raw_url = (
                getattr(filing, "filing_url", None)
                or getattr(filing, "url", None)
                or getattr(filing, "homepage_url", None)
                or ""
            )

            xbrl = None
            try:
                xbrl = filing.xbrl()
            except Exception as e:  # noqa: BLE001
                logger.warning("xbrl() unavailable for %s %s: %s", ticker, period, e)

            income_df = balance_df = cashflow_df = debt_df = pd.DataFrame()
            segment_df = debt_maturity_df = lease_df = sbc_df = tax_df = pd.DataFrame()
            risk_text = mda_text = ""
            if xbrl is not None:
                income_df = _statement_to_dataframe(xbrl, "income")
                balance_df = _statement_to_dataframe(xbrl, "balance")
                cashflow_df = _statement_to_dataframe(xbrl, "cashflow")
                debt_df = _extract_debt_facts(xbrl)
                segment_df = _extract_segment_data(xbrl)
                debt_maturity_df = _extract_debt_maturity(xbrl)
                lease_df = _extract_lease_schedule(xbrl)
                sbc_df = _extract_sbc_data(xbrl)
                tax_df = _extract_tax_detail(xbrl)

            # Heavy text extraction is optional - skip on Q filings to save time.
            try:
                if form == "10-K":
                    risk_text = extract_risk_factors_text(filing)
                    mda_text = extract_mda_text(filing)
            except Exception as e:  # noqa: BLE001
                logger.warning("filing text extraction failed for %s: %s", ticker, e)

            results.append({
                "ticker": ticker.upper(),
                "form_type": form,
                "period_of_report": period,
                "filed_at": filed_at,
                "fetched_at": datetime.utcnow().isoformat(timespec="seconds"),
                "income_statement": income_df,
                "balance_sheet": balance_df,
                "cash_flow_statement": cashflow_df,
                "debt_facts": debt_df,
                "segment_data": segment_df,
                "debt_maturity": debt_maturity_df,
                "lease_schedule": lease_df,
                "sbc_data": sbc_df,
                "tax_detail": tax_df,
                "risk_factors_text": risk_text,
                "mda_text": mda_text,
                "raw_filing_url": str(raw_url),
            })
            logger.info(
                "  parsed %s %s @ %s (income=%s, bal=%s, cf=%s, debt=%s, seg=%s, mat=%s, lease=%s, sbc=%s, tax=%s, risk=%dchars, mda=%dchars)",
                ticker, form, period or "?",
                income_df.shape, balance_df.shape, cashflow_df.shape, debt_df.shape,
                segment_df.shape, debt_maturity_df.shape, lease_df.shape,
                sbc_df.shape, tax_df.shape, len(risk_text), len(mda_text),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Skipping a %s %s filing due to error: %s", ticker, form, e)
            continue

    logger.info("Fetched %d %s filings for %s", len(results), form, ticker)
    return results


def fetch_all_forms(
    ticker: str, forms: list[str] | None = None, limit: int | None = None
) -> list[dict]:
    forms = forms or config.FORMS
    limit = limit or config.FILING_LIMIT
    all_results: list[dict] = []
    for form in forms:
        all_results.extend(fetch_company_filings(ticker, form=form, limit=limit))
    return all_results
