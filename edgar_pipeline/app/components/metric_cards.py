"""Animated KPI metric cards."""

from __future__ import annotations

import html as _html
import logging
from typing import Iterable

import streamlit as st

logger = logging.getLogger(__name__)


def render_metric_cards(metrics: Iterable[dict]) -> None:
    """Render a row of KPI cards.

    Each metric: {"label", "value", "delta" (optional), "icon" (optional)}
    """
    cards_html: list[str] = []
    metrics_list = list(metrics)
    logger.debug("render_metric_cards: rendering %d cards", len(metrics_list))
    for m in metrics_list:
        label = _html.escape(str(m.get("label", "")))
        value = _html.escape(str(m.get("value", "")))
        icon = _html.escape(str(m.get("icon", "")))
        delta_raw = str(m.get("delta", "")).strip()
        delta_html = ""
        if delta_raw:
            cls = "trend-flat"
            if delta_raw.startswith("+") or "▲" in delta_raw:
                cls = "trend-up"
            elif delta_raw.startswith("-") or "▼" in delta_raw:
                cls = "trend-down"
            delta_html = f'<div class="delta {cls}">{_html.escape(delta_raw)}</div>'

        # IMPORTANT: keep this string on one logical line with no leading
        # whitespace. Streamlit's markdown engine treats lines indented
        # by 4+ spaces as code blocks and renders the raw HTML as text.
        card = (
            f'<div class="metric-card">'
            f'<span class="icon">{icon}</span>'
            f'<div class="label">{label}</div>'
            f'<div class="kpi-number">{value}</div>'
            f'{delta_html}'
            f'</div>'
        )
        cards_html.append(card)

    grid_html = f'<div class="kpi-row">{"".join(cards_html)}</div>'
    st.markdown(grid_html, unsafe_allow_html=True)
