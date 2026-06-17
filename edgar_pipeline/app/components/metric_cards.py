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

        cards_html.append(
            f'''
            <div class="metric-card">
                <span class="icon">{icon}</span>
                <div class="label">{label}</div>
                <div class="kpi-number">{value}</div>
                {delta_html}
            </div>
            '''
        )

    grid_html = f'<div class="kpi-row">{"".join(cards_html)}</div>'
    st.markdown(grid_html, unsafe_allow_html=True)
