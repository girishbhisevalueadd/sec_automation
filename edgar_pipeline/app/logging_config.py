"""Centralized logging configuration for the Streamlit UI.

Call `setup_logging()` exactly once at the top of `streamlit_app.py`.
All other modules just do:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("...")

Log destinations:
    1. Console (stderr) - visible in the terminal that ran `streamlit run`.
    2. outputs/streamlit_ui.log - full UI log (UTF-8, rotated daily-style
       by sheer file size cap rather than time, so we don't need extra deps).
    3. outputs/pipeline.log - kept untouched; the backend keeps writing
       there via main.py / scheduler.py logging config.

Every log line includes:
    [HH:MM:SS] LEVEL  module.function:line  message

A small helper `@log_call` decorator logs function entries (with args)
and exits (with elapsed time / exceptions) at DEBUG level - drop it on
any function you want a stack trail of.
"""

from __future__ import annotations

import functools
import inspect
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_APP_DIR = Path(__file__).resolve().parent
_PIPELINE_ROOT = _APP_DIR.parent
_OUTPUTS_DIR = _PIPELINE_ROOT / "outputs"
UI_LOG_PATH = _OUTPUTS_DIR / "streamlit_ui.log"

# Make sure outputs/ exists even before config.py imports
_OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
_LOG_FORMAT = "[%(asctime)s] %(levelname)-7s %(name)s.%(funcName)s:%(lineno)d  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False


def setup_logging(level: int | str = "INFO") -> logging.Logger:
    """Initialize root logging for the Streamlit UI. Safe to call repeatedly."""
    global _CONFIGURED
    root = logging.getLogger()

    if _CONFIGURED:
        return root

    if isinstance(level, str):
        level = level.upper()

    root.setLevel(level if isinstance(level, int) else getattr(logging, level, logging.INFO))

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ---- Console handler (stderr) ----
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers)
    if not has_stream:
        sh = logging.StreamHandler(stream=sys.stderr)
        sh.setLevel(logging.INFO)
        sh.setFormatter(formatter)
        root.addHandler(sh)

    # ---- Rotating file handler (UI log) ----
    has_ui_file = any(
        isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith(UI_LOG_PATH.name)
        for h in root.handlers
    )
    if not has_ui_file:
        try:
            fh = logging.handlers.RotatingFileHandler(
                UI_LOG_PATH,
                maxBytes=2_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(formatter)
            root.addHandler(fh)
        except OSError as e:
            sys.stderr.write(f"[logging_config] WARN: could not attach file handler: {e}\n")

    # Quiet a few chatty third-party loggers
    for noisy in ("urllib3", "matplotlib", "fontTools"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    root.info("Streamlit UI logging initialized -> %s (level=%s)", UI_LOG_PATH, level)
    root.info(
        "Python %s on %s, cwd=%s",
        sys.version.split()[0], sys.platform, os.getcwd(),
    )
    return root


# ---------------------------------------------------------------------------
# Decorator helpers
# ---------------------------------------------------------------------------
def log_call(_func=None, *, level: int = logging.DEBUG, log_args: bool = True):
    """Decorator that logs function entry, exit, elapsed time, exceptions.

    Usage:
        @log_call
        def foo(x): ...

        @log_call(level=logging.INFO, log_args=False)
        def fast_path(...): ...
    """

    def _decorate(func):
        logger = logging.getLogger(func.__module__)
        qualname = func.__qualname__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if log_args:
                shown_args = ", ".join([
                    *(repr(a)[:60] for a in args),
                    *(f"{k}={v!r}"[:80] for k, v in kwargs.items()),
                ])
                logger.log(level, "→ %s(%s)", qualname, shown_args)
            else:
                logger.log(level, "→ %s(…)", qualname)
            t0 = time.perf_counter()
            try:
                out = func(*args, **kwargs)
            except Exception as e:
                dt = (time.perf_counter() - t0) * 1000
                logger.exception("✗ %s raised after %.1fms: %s", qualname, dt, e)
                raise
            dt = (time.perf_counter() - t0) * 1000
            if dt > 500:
                logger.info("← %s done in %.0fms", qualname, dt)
            else:
                logger.log(level, "← %s done in %.1fms", qualname, dt)
            return out

        return wrapper

    if _func is not None and callable(_func):
        return _decorate(_func)
    return _decorate


def get_logger(name: str | None = None) -> logging.Logger:
    """Shorthand wrapper for callers that want a consistent module logger."""
    if name is None:
        try:
            frame = inspect.stack()[1]
            mod = inspect.getmodule(frame.frame)
            name = mod.__name__ if mod else "edgar_pipeline.app"
        except Exception:
            name = "edgar_pipeline.app"
    return logging.getLogger(name)
