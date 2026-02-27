"""
Main posting orchestrator.
Syncs input folders, builds captions, and posts to all platforms.
"""

import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional

from .config import Config
from .database import Database
from .meta_api import MetaAPI
from .content_parser import parse_content_folder

logger = logging.getLogger(__name__)


class Poster:
    """Orchestrates syncing, caption building, and multi-platform posting."""

    def __init__(self):
        self.db = Database()
        self.api = MetaAPI()
        self.input_folder = Config.INPUT_FOLDER
        self.processed_folder = Config.PROCESSED_FOLDER

        # Ensure processed folder exists
        self.processed_folder.mkdir(parents=True, exist_ok=True)

    def get_video_duration(self, video_path: Path) -> float:
        """Get video duration using ffprobe (fast) or fallback."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.debug(f"ffprobe failed: {e}")

        # Fallback to moviepy
        try:
            from moviepy import VideoFileClip
            with VideoFileClip(str(video_path)) as clip:
                return clip.duration
        except Exception as e:
            logger.warning(f"Could not get duration for {video_path.name}: {e}")

        return 0.0

    def find_video_file(self, folder: Path) -> Optional[Path]:
        """Find the video file in a content folder."""
        for pattern in ["final_video*.mp4", "*.mp4"]:
            videos = list(folder.glob(pattern))
            if videos:
                return videos[0]
        return None

    def sync_input_folder(self):
        """Scan input folder and add new posts to database."""
        if not self.input_folder.exists():
            logger.error(f"Input folder not found: {self.input_folder}")
            return

        # Clean stale entries first
        removed = self.db.remove_missing_posts()
        if removed > 0:
            logger.info(f"Cleaned up {removed} stale database entries")

        folders = sorted([f for f in self.input_folder.iterdir() if f.is_dir()])
        new_count = 0

        for folder in folders:
            # Skip if already in DB
            if self.db.get_post_id(folder.name):
                continue

            video_path = self.find_video_file(folder)
            if not video_path:
                continue

            # Parse content (JSON or TXT)
            content = parse_content_folder(folder)

            # Get duration
            duration = self.get_video_duration(video_path)

            # Add to DB
            post_id = self.db.add_post(folder.name, video_path, content, duration)
            if post_id:
                new_count += 1
                logger.info(
                    f"Added to DB: {folder.name} "
                    f"(title: '{content.get('title', '')[:40]}...', duration: {duration:.1f}s)"
                )

        logger.info(f"Sync complete: {new_count} new posts added, {len(folders)} total folders")

    def post_to_platforms(self, post_id: int, folder_name: str, video_path: str,
                          reel_caption: str, story_caption: str, duration: float) -> Dict[str, bool]:
        """Post to all enabled platforms, skipping already-published ones."""
        video_path = Path(video_path)
        results = {}

        # Get already-published platforms to avoid duplicates on retry
        already_published = self.db.get_published_platforms(post_id)
        if already_published:
            logger.info(f"Already published on: {', '.join(already_published)} — skipping these")

        # Verify file exists
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return results

        # Re-check duration if it was 0
        if duration == 0 or duration is None:
            duration = self.get_video_duration(video_path)
            logger.info(f"Re-detected duration: {duration:.1f}s")

        # Validate token
        if not self.api.is_token_valid():
            logger.error("Invalid META_ACCESS_TOKEN — please update .env with a real token")
            logger.error("Get one from: https://developers.facebook.com/tools/explorer/")
            return results

        # Upload to GCS
        video_url = self.api.upload_to_gcs(video_path, folder_name)
        if not video_url:
            logger.error("GCS upload failed — cannot proceed")
            return results

        # ── Instagram Reel ──
        if "ig_reel" in already_published:
            logger.info("⏭ Skipping Instagram Reel (already published)")
            results["ig_reel"] = True
        elif Config.IG_ENABLED and Config.IG_POST_REEL and duration <= 180:
            logger.info(f"▶ Posting to Instagram Reel (duration: {duration:.1f}s)")
            logger.info(f"  Caption: {reel_caption[:100]}...")
            container_id = self.api.create_ig_reel_container(video_url, reel_caption)
            if container_id and self.api.check_container_status(container_id) == "FINISHED":
                success = self.api.publish_ig_media(container_id)
                results["ig_reel"] = success
                self.db.update_status(post_id, "ig_reel", "PUBLISHED" if success else "FAILED")
            else:
                self.db.update_status(post_id, "ig_reel", "FAILED", "Container creation/processing failed")
                results["ig_reel"] = False
        elif duration > 180:
            logger.info(f"⏭ Skipping Instagram Reel (duration {duration:.1f}s > 180s)")
            self.db.update_status(post_id, "ig_reel", "SKIPPED", "Duration > 180s")

        # ── Instagram Story (only if <= 60s) ──
        if "ig_story" in already_published:
            logger.info("⏭ Skipping Instagram Story (already published)")
            results["ig_story"] = True
        elif Config.IG_ENABLED and Config.IG_POST_STORY and duration <= 60:
            logger.info(f"▶ Posting to Instagram Story (duration: {duration:.1f}s)")
            logger.info(f"  Story title: {story_caption[:80]}")
            container_id = self.api.create_ig_story_container(video_url, story_caption)
            if container_id and self.api.check_container_status(container_id) == "FINISHED":
                success = self.api.publish_ig_media(container_id)
                results["ig_story"] = success
                self.db.update_status(post_id, "ig_story", "PUBLISHED" if success else "FAILED")
            else:
                self.db.update_status(post_id, "ig_story", "FAILED", "Container creation/processing failed")
                results["ig_story"] = False
        elif duration > 60:
            logger.info(f"⏭ Skipping Instagram Story (duration {duration:.1f}s > 60s)")
            self.db.update_status(post_id, "ig_story", "SKIPPED", "Duration > 60s")

        # ── Facebook Reel ──
        if "fb_reel" in already_published:
            logger.info("⏭ Skipping Facebook Reel (already published)")
            results["fb_reel"] = True
        elif Config.FB_ENABLED and Config.FB_POST_REEL and duration <= 180:
            logger.info(f"▶ Posting to Facebook Reel (duration: {duration:.1f}s)")
            logger.info(f"  Caption: {reel_caption[:100]}...")
            success = self.api.create_fb_reel(video_url, reel_caption)
            results["fb_reel"] = success
            self.db.update_status(post_id, "fb_reel", "PUBLISHED" if success else "FAILED")
        elif duration > 180:
            logger.info(f"⏭ Skipping Facebook Reel (duration {duration:.1f}s > 180s)")
            self.db.update_status(post_id, "fb_reel", "SKIPPED", "Duration > 180s")

        # ── Facebook Feed ──
        if "fb_feed" in already_published:
            logger.info("⏭ Skipping Facebook Feed (already published)")
            results["fb_feed"] = True
        elif Config.FB_ENABLED and Config.FB_POST_FEED:
            logger.info(f"▶ Posting to Facebook Feed")
            logger.info(f"  Caption: {reel_caption[:100]}...")
            success = self.api.create_fb_feed_video(video_url, reel_caption)
            results["fb_feed"] = success
            self.db.update_status(post_id, "fb_feed", "PUBLISHED" if success else "FAILED")

        return results

    def run_daily_post(self):
        """Main function: sync, pick next, post, move to processed."""
        logger.info("=" * 80)
        logger.info("POSTING SERVICE — Daily Run Started")
        logger.info(f"  Time: {__import__('datetime').datetime.now().isoformat()}")
        logger.info(f"  Posts today: {self.db.get_posts_today()}")
        logger.info("=" * 80)

        # Sync input folder
        self.sync_input_folder()

        # Get next pending post
        post = self.db.get_next_pending_post()
        if not post:
            logger.warning("No pending posts found (all published or files missing)")
            return

        post_id, folder_name, video_path, reel_caption, story_caption, duration = post
        logger.info(f"Selected post: {folder_name}")
        logger.info(f"  Duration: {duration:.1f}s")
        logger.info(f"  Reel caption: {reel_caption[:120]}...")
        logger.info(f"  Story caption: {story_caption[:80]}")

        # Post to all platforms
        results = self.post_to_platforms(
            post_id, folder_name, video_path, reel_caption, story_caption, duration
        )

        # Update scheduler state
        self.db.update_scheduler_state(folder_name)

        # Log results
        logger.info("=" * 80)
        logger.info("POSTING RESULTS:")
        for platform, success in results.items():
            status = "✓ SUCCESS" if success else "✗ FAILED"
            logger.info(f"  {platform}: {status}")
        logger.info("=" * 80)

        # Move to processed if all succeeded
        if results and all(results.values()):
            try:
                src = Path(video_path).parent
                dst = self.processed_folder / folder_name
                src.rename(dst)
                logger.info(f"Moved to processed: {folder_name}")
            except Exception as e:
                logger.error(f"Failed to move folder: {e}")
        elif not results:
            logger.warning(f"No platforms were posted to — keeping {folder_name} in input")
        else:
            failed = [p for p, s in results.items() if not s]
            logger.warning(f"Some platforms failed ({', '.join(failed)}) — keeping {folder_name} in input for retry")
