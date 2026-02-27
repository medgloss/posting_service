"""
SQLite database for tracking post state and scheduler runs.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime, date

from .config import Config

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for tracking post status."""

    def __init__(self):
        self.db_path = Config.DB_PATH
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_name TEXT UNIQUE NOT NULL,
                video_path TEXT NOT NULL,
                title TEXT,
                description TEXT,
                hashtags TEXT,
                reel_caption TEXT,
                story_caption TEXT,
                duration REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS post_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                status TEXT NOT NULL,
                published_at TEXT,
                error_message TEXT,
                FOREIGN KEY (post_id) REFERENCES posts(id),
                UNIQUE(post_id, platform)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_run TEXT,
                last_posted_folder TEXT,
                posts_today INTEGER DEFAULT 0,
                today_date TEXT
            )
        """)

        # Initialize scheduler state if not exists
        cursor.execute("INSERT OR IGNORE INTO scheduler_state (id) VALUES (1)")

        conn.commit()
        conn.close()
        logger.info(f"Database initialized: {self.db_path}")

    def add_post(self, folder_name, video_path, content: dict, duration: float):
        """Add a new post entry to the database."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO posts 
                   (folder_name, video_path, title, description, hashtags, reel_caption, story_caption, duration) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    folder_name,
                    str(video_path),
                    content.get("title", ""),
                    content.get("description", ""),
                    content.get("hashtags", ""),
                    content.get("reel_caption", ""),
                    content.get("story_caption", ""),
                    duration,
                ),
            )
            post_id = cursor.lastrowid
            conn.commit()
            return post_id
        except Exception as e:
            logger.error(f"Error adding post: {e}")
            return None
        finally:
            conn.close()

    def get_post_id(self, folder_name: str):
        """Get post ID by folder name."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM posts WHERE folder_name = ?", (folder_name,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_next_pending_post(self):
        """
        Get the next post that hasn't been fully published across all platforms.
        Returns (post_id, folder_name, video_path, reel_caption, story_caption, duration) or None.
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Get posts that don't have all 4 platforms published
        # Platforms: ig_reel, ig_story, fb_reel, fb_feed
        cursor.execute("""
            SELECT p.id, p.folder_name, p.video_path, p.reel_caption, p.story_caption, p.duration
            FROM posts p
            WHERE NOT EXISTS (
                SELECT 1 FROM post_status ps 
                WHERE ps.post_id = p.id 
                AND ps.platform IN ('ig_reel', 'ig_story', 'fb_reel', 'fb_feed')
                AND ps.status = 'PUBLISHED'
                GROUP BY ps.post_id
                HAVING COUNT(*) >= 4
            )
            ORDER BY p.created_at ASC
        """)
        results = cursor.fetchall()
        conn.close()

        # Find first post where video file still exists
        for result in results:
            post_id, folder_name, video_path, reel_caption, story_caption, duration = result
            if Path(video_path).exists():
                return result
            else:
                logger.warning(f"Skipping {folder_name} — video file missing: {video_path}")

        return None

    def get_published_platforms(self, post_id: int) -> set:
        """Get the set of platforms already published for a post."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT platform FROM post_status WHERE post_id = ? AND status = 'PUBLISHED'",
            (post_id,),
        )
        platforms = {row[0] for row in cursor.fetchall()}
        conn.close()
        return platforms

    def update_status(self, post_id: int, platform: str, status: str, error_message: str = None):
        """Update or insert post status for a platform."""
        conn = self._get_conn()
        cursor = conn.cursor()
        published_at = datetime.now().isoformat() if status == "PUBLISHED" else None
        cursor.execute(
            """INSERT OR REPLACE INTO post_status (post_id, platform, status, published_at, error_message)
               VALUES (?, ?, ?, ?, ?)""",
            (post_id, platform, status, published_at, error_message),
        )
        conn.commit()
        conn.close()

    def remove_missing_posts(self):
        """Remove posts from DB where video file no longer exists."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, folder_name, video_path FROM posts")
        posts = cursor.fetchall()

        removed = 0
        for post_id, folder_name, video_path in posts:
            if not Path(video_path).exists():
                cursor.execute("DELETE FROM post_status WHERE post_id = ?", (post_id,))
                cursor.execute("DELETE FROM posts WHERE id = ?", (post_id,))
                logger.info(f"Removed stale DB entry: {folder_name}")
                removed += 1

        conn.commit()
        conn.close()
        return removed

    def update_scheduler_state(self, last_posted_folder: str):
        """Update scheduler state. Resets posts_today counter if new day."""
        conn = self._get_conn()
        cursor = conn.cursor()

        today = date.today().isoformat()

        # Check if it's a new day — reset counter
        cursor.execute("SELECT today_date FROM scheduler_state WHERE id = 1")
        row = cursor.fetchone()
        current_date = row[0] if row else None

        if current_date != today:
            # New day — reset counter
            cursor.execute(
                """UPDATE scheduler_state 
                   SET last_run = ?, last_posted_folder = ?, posts_today = 1, today_date = ?
                   WHERE id = 1""",
                (datetime.now().isoformat(), last_posted_folder, today),
            )
        else:
            cursor.execute(
                """UPDATE scheduler_state 
                   SET last_run = ?, last_posted_folder = ?, posts_today = posts_today + 1
                   WHERE id = 1""",
                (datetime.now().isoformat(), last_posted_folder),
            )

        conn.commit()
        conn.close()

    def get_posts_today(self) -> int:
        """Get number of posts made today."""
        conn = self._get_conn()
        cursor = conn.cursor()
        today = date.today().isoformat()
        cursor.execute(
            "SELECT posts_today FROM scheduler_state WHERE id = 1 AND today_date = ?",
            (today,),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
