#!/usr/bin/env python3
"""
Posting Service Scheduler — Entry Point

Runs continuously using APScheduler with two daily cron jobs:
  - Job 1: 6:00 PM IST (12:30 UTC)
  - Job 2: 8:00 PM IST (14:30 UTC)

Each job posts one reel to IG Reels, IG Story, FB Reels, and FB Feed.

Usage:
  python -m posting_service.scheduler             # Run scheduler (continuous)
  python -m posting_service.scheduler --test       # Test mode: sync only, no posting
  python -m posting_service.scheduler --run-now    # Post immediately, then exit
"""

import sys
import signal
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Config
from .poster import Poster


def setup_logging():
    """Configure rotating log files + console output."""
    log_dir = Config.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = Config.LOG_FILE

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Rotating file handler: 5MB per file, keep 10 backups
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return logging.getLogger(__name__)


def run_scheduled_post():
    """Callback for scheduled jobs — posts one reel."""
    logger = logging.getLogger(__name__)
    try:
        logger.info("━" * 60)
        logger.info("SCHEDULED JOB TRIGGERED")
        logger.info("━" * 60)
        poster = Poster()
        poster.run_daily_post()
    except Exception as e:
        logger.error(f"Scheduled job failed: {e}", exc_info=True)


def main():
    logger = setup_logging()

    logger.info("=" * 80)
    logger.info("POSTING SERVICE STARTING")
    logger.info("=" * 80)

    # Validate config
    issues = Config.validate()
    if issues:
        for issue in issues:
            logger.warning(f"Config issue: {issue}")

    logger.info(f"Input folder:  {Config.INPUT_FOLDER}")
    logger.info(f"Processed:     {Config.PROCESSED_FOLDER}")
    logger.info(f"Database:      {Config.DB_PATH}")
    logger.info(f"Log file:      {Config.LOG_FILE}")
    logger.info(f"IG enabled:    {Config.IG_ENABLED} (reel={Config.IG_POST_REEL}, story={Config.IG_POST_STORY})")
    logger.info(f"FB enabled:    {Config.FB_ENABLED} (reel={Config.FB_POST_REEL}, feed={Config.FB_POST_FEED})")
    logger.info(f"Schedule:      {Config.SCHEDULE_TIME_1} IST, {Config.SCHEDULE_TIME_2} IST")

    # ── --test mode ──
    if "--test" in sys.argv:
        logger.info("Running in TEST mode — sync only, no posting")
        poster = Poster()
        poster.sync_input_folder()
        logger.info("Test complete")
        return

    # ── --run-now mode ──
    if "--run-now" in sys.argv:
        logger.info("Running in RUN-NOW mode — posting immediately")
        poster = Poster()
        poster.run_daily_post()
        logger.info("Run-now complete")
        return

    # ── Normal scheduler mode ──
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except ImportError:
        logger.error("APScheduler not installed. Install with: pip install apscheduler")
        logger.error("Falling back to simple sleep loop...")
        _fallback_loop(logger)
        return

    ist = pytz.timezone("Asia/Kolkata")
    scheduler = BlockingScheduler(timezone=ist)

    # Parse schedule times
    h1, m1 = Config.SCHEDULE_TIME_1.split(":")
    h2, m2 = Config.SCHEDULE_TIME_2.split(":")

    # Job 1: 6 PM IST
    scheduler.add_job(
        run_scheduled_post,
        CronTrigger(hour=int(h1), minute=int(m1), timezone=ist),
        id="post_6pm",
        name="Daily Post - 6 PM IST",
        misfire_grace_time=3600,  # 1 hour grace period
    )

    # Job 2: 8 PM IST
    scheduler.add_job(
        run_scheduled_post,
        CronTrigger(hour=int(h2), minute=int(m2), timezone=ist),
        id="post_8pm",
        name="Daily Post - 8 PM IST",
        misfire_grace_time=3600,
    )

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping scheduler...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("Scheduler started. Waiting for scheduled times...")
    logger.info(f"  Next post at: {Config.SCHEDULE_TIME_1} IST and {Config.SCHEDULE_TIME_2} IST")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


def _fallback_loop(logger):
    """Simple fallback if APScheduler isn't available — checks every minute."""
    import datetime
    import pytz

    ist = pytz.timezone("Asia/Kolkata")
    posted_times = set()

    logger.info("Fallback loop started. Checking every 60s...")

    while True:
        try:
            now = datetime.datetime.now(ist)
            current_time = now.strftime("%H:%M")

            if current_time in (Config.SCHEDULE_TIME_1, Config.SCHEDULE_TIME_2):
                today_key = f"{now.date()}_{current_time}"
                if today_key not in posted_times:
                    posted_times.add(today_key)
                    run_scheduled_post()

            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Fallback loop stopped")
            break
        except Exception as e:
            logger.error(f"Fallback loop error: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
