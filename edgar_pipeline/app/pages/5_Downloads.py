"""Downloads page - file browser + bulk ZIP download."""

from __future__ import annotations

import io
import logging
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import humanize
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_APP_DIR = Path(__file__).resolve().parent.parent
_PIPELINE_ROOT = _APP_DIR.parent
for _p in (_APP_DIR, _PIPELINE_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

logger = logging.getLogger(__name__)
logger.info("Page load: 5_Downloads")

from app_utils import inject_css, list_output_files  # noqa: E402
from components.sidebar import render_sidebar  # noqa: E402
from components.file_table import render_file_table  # noqa: E402

inject_css(st)
render_sidebar()

st.markdown('<h1 style="margin-top:0;">⬇️ Downloads</h1>', unsafe_allow_html=True)
st.caption("Browse and download every Excel model, Word report, and PDF generated.")

import config  # noqa: E402

tabs = st.tabs(["📊 Excel Models", "📝 Word Reports", "📑 PDFs"])

selected_for_zip: list[Path] = []

with tabs[0]:
    search = st.text_input("Search Excel files", placeholder="ticker, period, form …", key="dl_search_xlsx")
    enable_zip = st.checkbox("Enable multi-select for ZIP download", key="dl_zip_xlsx")
    sel = render_file_table(config.EXCEL_DIR, ".xlsx", search=search, label_prefix="xlsx", show_checkboxes=enable_zip)
    selected_for_zip += sel

with tabs[1]:
    search = st.text_input("Search Word reports", placeholder="ticker, period, form …", key="dl_search_docx")
    enable_zip = st.checkbox("Enable multi-select for ZIP download", key="dl_zip_docx")
    sel = render_file_table(config.REPORTS_DIR, ".docx", search=search, label_prefix="docx", show_checkboxes=enable_zip)
    selected_for_zip += sel

with tabs[2]:
    search = st.text_input("Search PDF reports", placeholder="ticker, period, form …", key="dl_search_pdf")
    enable_zip = st.checkbox("Enable multi-select for ZIP download", key="dl_zip_pdf")
    sel = render_file_table(config.REPORTS_DIR, ".pdf", search=search, label_prefix="pdf", show_checkboxes=enable_zip)
    selected_for_zip += sel

# ---------------------------------------------------------------------------
# Bulk ZIP download
# ---------------------------------------------------------------------------
if selected_for_zip:
    st.markdown('<div class="section-header">Bulk Download</div>', unsafe_allow_html=True)
    st.caption(f"{len(selected_for_zip)} files selected")

    def _zip_bytes(paths: list[Path]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                if p.exists():
                    zf.write(p, p.name)
        return buf.getvalue()

    logger.info("Downloads: building ZIP for %d selected files", len(selected_for_zip))
    z = _zip_bytes(selected_for_zip)
    logger.info("Downloads: ZIP built, %.1f KB", len(z) / 1024)
    st.download_button(
        "⬇ Download Selected as ZIP",
        data=z,
        file_name=f"edgar_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        mime="application/zip",
        type="primary",
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# Storage stats
# ---------------------------------------------------------------------------
st.markdown('<div class="section-header">Storage Stats</div>', unsafe_allow_html=True)

xlsx = list_output_files(config.EXCEL_DIR, ".xlsx")
docx = list_output_files(config.REPORTS_DIR, ".docx")
pdf = list_output_files(config.REPORTS_DIR, ".pdf")

n_xlsx, n_docx, n_pdf = len(xlsx), len(docx), len(pdf)
s_xlsx = sum(p.stat().st_size for p in xlsx)
s_docx = sum(p.stat().st_size for p in docx)
s_pdf = sum(p.stat().st_size for p in pdf)
total = s_xlsx + s_docx + s_pdf

c1, c2, c3, c4 = st.columns(4)
c1.metric("Excel", n_xlsx, humanize.naturalsize(s_xlsx))
c2.metric("Word", n_docx, humanize.naturalsize(s_docx))
c3.metric("PDF", n_pdf, humanize.naturalsize(s_pdf))
c4.metric("Total Size", humanize.naturalsize(total))

if total > 0:
    fig = go.Figure(go.Bar(
        x=["Excel", "Word", "PDF"],
        y=[s_xlsx, s_docx, s_pdf],
        marker_color=["#1D6FA4", "#0F9E75", "#F5A623"],
        text=[humanize.naturalsize(s_xlsx), humanize.naturalsize(s_docx), humanize.naturalsize(s_pdf)],
        textposition="auto",
    ))
    fig.update_layout(
        template="plotly_dark", height=240,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(28,35,51,0.4)",
        xaxis=dict(gridcolor="#2D3650"),
        yaxis=dict(gridcolor="#2D3650", title="Bytes"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
