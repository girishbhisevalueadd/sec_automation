"""Animated status pill badges."""

from __future__ import annotations

import streamlit as st


_LABELS = {
    "idle": "Idle",
    "running": "Running",
    "success": "Success",
    "failed": "Failed",
    "partial": "Partial",
}


def render_status_badge(status: str, label: str | None = None) -> None:
    """Render a colored pill with optional label. 'running' pulses."""
    status = (status or "idle").lower()
    if status not in _LABELS:
        status = "idle"
    text = label or _LABELS[status]
    html = (
        f'<span class="status-badge {status}">'
        f'<span class="dot"></span>{text}'
        f'</span>'
    )
    st.markdown(html, unsafe_allow_html=True)


def badge_html(status: str, label: str | None = None) -> str:
    status = (status or "idle").lower()
    if status not in _LABELS:
        status = "idle"
    text = label or _LABELS[status]
    return (
        f'<span class="status-badge {status}">'
        f'<span class="dot"></span>{text}'
        f'</span>'
    )
