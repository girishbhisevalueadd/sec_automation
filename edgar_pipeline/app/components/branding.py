"""Page-level branding banner: 'Prepared by Vivek Pol · ValueAdd Research …'.

Every Streamlit page calls render_page_branding() right after its title so
the user's name and company name are visible on Home, Dashboard, Run
Pipeline, Financials, Charts, Downloads, and Logs.
"""

from __future__ import annotations

import html as _html
import logging
import sys
from pathlib import Path

import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

logger = logging.getLogger(__name__)


def render_page_branding() -> None:
    """Render a compact "Prepared by Vivek Pol · ValueAdd Research …" banner.

    Reads REPORT_AUTHOR and REPORT_COMPANY from config.py so updating one
    field in config rebrands every page automatically.
    """
    import config

    author = getattr(config, "REPORT_AUTHOR", "Vivek Pol")
    company = getattr(config, "REPORT_COMPANY", "ValueAdd Research And Analytics Solutions LLP")

    # Logo on the left (if present), text on the right.
    logo_html = ""
    logo_path = getattr(config, "LOGO_PATH", None)
    if logo_path and Path(logo_path).exists():
        # Inline base64 embed so it works without serving static files.
        import base64
        try:
            mime = "image/png" if str(logo_path).lower().endswith(".png") else "image/jpeg"
            with open(logo_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            logo_html = (
                f'<img src="data:{mime};base64,{b64}" '
                f'style="height:28px; vertical-align:middle; margin-right:10px;" alt="logo"/>'
            )
        except OSError as e:  # noqa: BLE001
            logger.warning("Could not embed logo in page branding: %s", e)

    html = (
        '<div style="margin-top:-6px; margin-bottom:14px; padding:8px 14px; '
        'background: linear-gradient(90deg, rgba(29,111,164,0.10) 0%, rgba(15,158,117,0.06) 100%); '
        'border-left: 3px solid var(--accent-blue); border-radius: 4px; '
        'display: flex; align-items: center;">'
        f'{logo_html}'
        '<div style="font-size:12px; line-height:1.4;">'
        f'<span style="color: var(--text-muted);">Prepared by</span> '
        f'<b style="color: var(--text);">{_html.escape(author)}</b>'
        f'<span style="color: var(--text-muted);"> &nbsp;·&nbsp; </span>'
        f'<span style="color: var(--text);">{_html.escape(company)}</span>'
        '</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
