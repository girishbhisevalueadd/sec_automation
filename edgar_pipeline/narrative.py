"""Optional Claude-powered narrative generator.

If `ANTHROPIC_API_KEY` is not set or the call fails, returns a
placeholder block so the rest of the pipeline keeps running.
"""

from __future__ import annotations

import logging

import pandas as pd

import config

logger = logging.getLogger(__name__)


PLACEHOLDER_NARRATIVE = """
EXECUTIVE SUMMARY
Narrative auto-generation is disabled (no ANTHROPIC_API_KEY set). The
financial tables and ratio panel below contain the core observations.

REVENUE TREND ANALYSIS
[Placeholder] Refer to the Income Statement tab and Revenue Growth YoY row
of Key Ratios for the multi-year revenue trajectory.

MARGIN ANALYSIS
[Placeholder] Gross, operating, and net margin rows in Key Ratios show how
profitability has trended across the periods in scope.

BALANCE SHEET STRENGTH
[Placeholder] Current ratio, debt/equity, and total assets vs. equity offer
a first read on solvency and liquidity.

CASH FLOW QUALITY
[Placeholder] Operating cash flow, capex, and the derived free cash flow
metric in Key Ratios indicate the company's cash generation profile.

KEY RISKS
[Placeholder] Customary risks for the sector: revenue concentration, FX
exposure, regulatory changes, refinancing risk on debt maturities.

OUTLOOK
[Placeholder] Outlook commentary requires forward-looking judgment beyond
the historical filings stored in this pipeline.
""".strip()


def _format_df_as_text(df: pd.DataFrame, max_rows: int = 25) -> str:
    if df is None or df.empty:
        return "(no data)"
    work = df.head(max_rows).copy()
    return work.to_string(max_cols=8, float_format=lambda v: f"{v:,.0f}" if pd.notna(v) else "")


def _build_prompt(ticker: str, summary_dict: dict[str, pd.DataFrame], ratios_df: pd.DataFrame) -> str:
    parts = [
        f"You are a senior equity research analyst. Write a professional research note on {ticker.upper()}.",
        "Use the financial data below (sourced from SEC EDGAR filings). Cite specific numbers.",
        "Target length: 600-800 words. Sections (use ALL-CAPS headers exactly):",
        "EXECUTIVE SUMMARY, REVENUE TREND ANALYSIS, MARGIN ANALYSIS,",
        "BALANCE SHEET STRENGTH, CASH FLOW QUALITY, KEY RISKS, OUTLOOK.",
        "",
        "=== INCOME STATEMENT (USD) ===",
        _format_df_as_text(summary_dict.get("income", pd.DataFrame())),
        "",
        "=== BALANCE SHEET (USD) ===",
        _format_df_as_text(summary_dict.get("balance", pd.DataFrame())),
        "",
        "=== CASH FLOW STATEMENT (USD) ===",
        _format_df_as_text(summary_dict.get("cashflow", pd.DataFrame())),
        "",
        "=== KEY RATIOS ===",
        _format_df_as_text(ratios_df.reset_index() if ratios_df is not None else pd.DataFrame()),
    ]
    return "\n".join(parts)


def generate_narrative(
    ticker: str,
    summary_dict: dict[str, pd.DataFrame],
    ratios_df: pd.DataFrame,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        logger.info("ANTHROPIC_API_KEY not set - returning placeholder narrative.")
        return PLACEHOLDER_NARRATIVE

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed - returning placeholder.")
        return PLACEHOLDER_NARRATIVE

    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        prompt = _build_prompt(ticker, summary_dict, ratios_df)
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenate all text blocks
        text_parts = []
        for block in msg.content:
            text = getattr(block, "text", None)
            if text:
                text_parts.append(text)
        narrative = "\n".join(text_parts).strip()
        if not narrative:
            logger.warning("Claude returned empty content - returning placeholder.")
            return PLACEHOLDER_NARRATIVE
        return narrative
    except Exception as e:  # noqa: BLE001
        logger.warning("Claude narrative call failed: %s - returning placeholder.", e)
        return PLACEHOLDER_NARRATIVE
