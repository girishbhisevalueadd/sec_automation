"""Weekly scheduler - runs the full pipeline every Monday at 07:00."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import schedule

import config

logger = logging.getLogger(__name__)


def _job():
    from main import run_full_pipeline_for_watchlist
    start = datetime.now()
    logger.info("=" * 60)
    logger.info("Scheduled pipeline run started at %s", start.isoformat(timespec="seconds"))
    try:
        summary = run_full_pipeline_for_watchlist()
        logger.info("Pipeline summary: %s", summary)
    except Exception as e:  # noqa: BLE001
        logger.exception("Scheduled run errored: %s", e)
    finally:
        end = datetime.now()
        logger.info("Scheduled run finished at %s (elapsed=%s)", end.isoformat(timespec="seconds"), end - start)


def start():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[logging.FileHandler(config.LOG_PATH), logging.StreamHandler()],
    )
    schedule.every().monday.at("07:00").do(_job)
    logger.info("Scheduler armed: Monday 07:00 local time. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    start()
