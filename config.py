"""
Configuration management for the posting service.
All settings are loaded from environment variables.
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the posting_service directory first, then parent
SERVICE_DIR = Path(__file__).parent
PROJECT_DIR = SERVICE_DIR.parent

# Try service-level .env first, fallback to project-level
env_path = SERVICE_DIR / ".env"
if not env_path.exists():
    env_path = PROJECT_DIR / ".env"
load_dotenv(env_path)


class Config:
    """Centralized configuration from environment variables."""

    # Meta API
    META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
    IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID", "")
    FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")

    # Platform toggles
    IG_ENABLED = os.getenv("IG_ENABLED", "true").lower() == "true"
    IG_POST_REEL = os.getenv("IG_POST_REEL", "true").lower() == "true"
    IG_POST_STORY = os.getenv("IG_POST_STORY", "true").lower() == "true"

    FB_ENABLED = os.getenv("FB_ENABLED", "true").lower() == "true"
    FB_POST_REEL = os.getenv("FB_POST_REEL", "true").lower() == "true"
    FB_POST_FEED = os.getenv("FB_POST_FEED", "true").lower() == "true"

    # GCS
    GCS_ENABLED = os.getenv("GCS_ENABLED", "false").lower() == "true"
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
    GCS_CREDENTIALS_JSON = os.getenv("GCS_CREDENTIALS_JSON", "")
    GCS_FOLDER_PREFIX = os.getenv("GCS_FOLDER_PREFIX", "reels")

    # Folders (prefer SERVICE_DIR since it's a standalone repo now)
    INPUT_FOLDER = SERVICE_DIR / os.getenv("INPUT_FOLDER", "input")
    PROCESSED_FOLDER = SERVICE_DIR / os.getenv("PROCESSED_FOLDER", "processed")

    # Schedule (IST times as HH:MM)
    SCHEDULE_TIME_1 = os.getenv("SCHEDULE_TIME_1", "18:00")  # 6 PM IST
    SCHEDULE_TIME_2 = os.getenv("SCHEDULE_TIME_2", "20:00")  # 8 PM IST

    # Database
    DB_PATH = SERVICE_DIR / os.getenv("DB_NAME", "posting_service.db")

    # Logging
    LOG_DIR = SERVICE_DIR / "logs"
    LOG_FILE = LOG_DIR / "posting_service.log"

    @classmethod
    def validate(cls):
        """Validate required config values are set."""
        issues = []
        if not cls.META_ACCESS_TOKEN or len(cls.META_ACCESS_TOKEN) < 50:
            issues.append("META_ACCESS_TOKEN is missing or too short")
        if not cls.IG_ACCOUNT_ID:
            issues.append("IG_ACCOUNT_ID is missing")
        if not cls.FB_PAGE_ID:
            issues.append("FB_PAGE_ID is missing")
        if cls.GCS_ENABLED and not cls.GCS_CREDENTIALS_JSON:
            issues.append("GCS_CREDENTIALS_JSON is missing but GCS_ENABLED=true")
        return issues
