"""File browser component with download buttons."""

from __future__ import annotations

import html as _html
import logging
from datetime import datetime
from pathlib import Path

import humanize
import streamlit as st

# Avoid relative imports — Streamlit pages can't always resolve them
import sys as _sys
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in _sys.path:
    _sys.path.insert(0, str(_APP_DIR))

from app_utils import get_mime_type, list_output_files, parse_output_filename  # noqa: E402

logger = logging.getLogger(__name__)


def render_file_table(
    directory: Path,
    extension: str,
    search: str = "",
    label_prefix: str = "",
    show_checkboxes: bool = False,
) -> list[Path]:
    """Render a styled table of files in `directory` matching `extension`.

    Returns the list of paths the user selected (via checkbox).
    """
    files = list_output_files(directory, extension)
    logger.debug(
        "render_file_table: dir=%s ext=%s search=%r matched=%d",
        directory.name, extension, search, len(files),
    )
    if search:
        s = search.lower()
        files = [p for p in files if s in p.name.lower()]
        logger.debug("render_file_table: post-search count=%d", len(files))

    if not files:
        st.info(f"No {extension} files yet in `{directory.name}/`.")
        return []

    # Header row
    st.markdown(
        '<div class="file-row" style="background:var(--surface-2); font-weight:700; color:var(--text-muted); text-transform:uppercase; font-size:11px; letter-spacing:0.06em;">'
        '<div>File</div><div>Ticker</div><div>Form</div><div>Size</div><div>Age</div><div>Download</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    selected: list[Path] = []
    for path in files:
        info = parse_output_filename(path)
        size_h = humanize.naturalsize(info["size_bytes"])
        age_h = humanize.naturaltime(datetime.now() - info["mtime"])

        cols = st.columns([2.0, 1.0, 1.0, 1.0, 1.2, 1.4])
        with cols[0]:
            if show_checkboxes:
                if st.checkbox(
                    path.name,
                    key=f"sel_{label_prefix}_{path.name}",
                    label_visibility="visible",
                ):
                    selected.append(path)
            else:
                st.markdown(
                    f'<div style="font-family: var(--mono); font-size:12px; color: var(--text);">{_html.escape(path.name)}</div>',
                    unsafe_allow_html=True,
                )
        cols[1].markdown(f'<span class="tag-pill">{_html.escape(info["ticker"])}</span>', unsafe_allow_html=True)
        cols[2].markdown(f'<span class="tag-pill">{_html.escape(info["form"])}</span>', unsafe_allow_html=True)
        cols[3].markdown(f'<span style="font-family: var(--mono); color: var(--text-muted);">{size_h}</span>', unsafe_allow_html=True)
        cols[4].markdown(f'<span style="font-family: var(--mono); color: var(--text-muted); font-size:12px;">{age_h}</span>', unsafe_allow_html=True)
        with cols[5]:
            try:
                data = path.read_bytes()
                st.download_button(
                    label=f"⬇ Download",
                    data=data,
                    file_name=path.name,
                    mime=get_mime_type(path.suffix),
                    key=f"dl_{label_prefix}_{path.name}_{int(path.stat().st_mtime)}",
                    use_container_width=True,
                )
            except OSError as e:
                st.caption(f"⚠ {e}")

    return selected
