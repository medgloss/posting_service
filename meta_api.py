"""
Meta Graph API wrapper for Instagram and Facebook posting.
Also handles GCS upload and signed URL generation.
"""

import os
import json
import logging
import time
import requests
from pathlib import Path
from datetime import timedelta
from typing import Optional

from .config import Config

logger = logging.getLogger(__name__)


class MetaAPI:
    """Handles all Meta Graph API interactions and GCS uploads."""

    API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

    def __init__(self):
        self.access_token = Config.META_ACCESS_TOKEN
        self.ig_account_id = Config.IG_ACCOUNT_ID
        self.fb_page_id = Config.FB_PAGE_ID
        self.page_access_token = None
        self.gcs_bucket = None

        self._init_gcs()
        self._get_page_access_token()

    def _init_gcs(self):
        """Initialize Google Cloud Storage client."""
        if not Config.GCS_ENABLED:
            logger.info("GCS is disabled")
            return
        try:
            creds_json = Config.GCS_CREDENTIALS_JSON
            bucket_name = Config.GCS_BUCKET_NAME
            if creds_json and bucket_name:
                creds_dict = json.loads(creds_json)
                from google.oauth2 import service_account
                from google.cloud import storage

                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict
                )
                client = storage.Client(
                    credentials=credentials, project=creds_dict.get("project_id")
                )
                self.gcs_bucket = client.bucket(bucket_name)
                logger.info(f"GCS initialized: bucket={bucket_name}")
        except Exception as e:
            logger.error(f"Failed to init GCS: {e}")

    def _get_page_access_token(self):
        """Get Page Access Token from User Access Token."""
        if not self.access_token or not self.fb_page_id:
            logger.warning("Missing access token or FB page ID")
            return

        try:
            url = f"{self.BASE_URL}/{self.fb_page_id}"
            params = {"fields": "access_token", "access_token": self.access_token}
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            self.page_access_token = data.get("access_token")
            if self.page_access_token:
                logger.info("Got Page Access Token successfully")
            else:
                logger.warning("No page access token in response, using user token")
                self.page_access_token = self.access_token
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to get Page Access Token: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            self.page_access_token = self.access_token

    # ── GCS Helpers ──────────────────────────────────────────────

    def upload_to_gcs(self, video_path: Path, folder_name: str) -> Optional[str]:
        """Upload video to GCS and return a signed URL (7-day expiry)."""
        if not self.gcs_bucket:
            logger.error("GCS not initialized — cannot upload")
            return None

        try:
            blob_path = f"{Config.GCS_FOLDER_PREFIX}/{folder_name}/{video_path.name}"
            blob = self.gcs_bucket.blob(blob_path)
            blob.upload_from_filename(str(video_path))
            signed_url = blob.generate_signed_url(
                expiration=timedelta(days=7), method="GET", version="v4"
            )
            logger.info(f"Uploaded to GCS: {blob_path}")
            return signed_url
        except Exception as e:
            logger.error(f"GCS upload failed: {e}")
            return None

    # ── Instagram ────────────────────────────────────────────────

    def create_ig_reel_container(self, video_url: str, caption: str) -> Optional[str]:
        """Create an Instagram Reel container."""
        token = self.page_access_token or self.access_token
        url = f"{self.BASE_URL}/{self.ig_account_id}/media"
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": token,
        }
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            container_id = response.json().get("id")
            logger.info(f"IG Reel container created: {container_id}")
            return container_id
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to create IG Reel container: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return None

    def create_ig_story_container(
        self, video_url: str, caption: str = ""
    ) -> Optional[str]:
        """Create an Instagram Story container. Caption = title only."""
        token = self.page_access_token or self.access_token
        url = f"{self.BASE_URL}/{self.ig_account_id}/media"
        params = {
            "media_type": "STORIES",
            "video_url": video_url,
            "access_token": token,
        }
        # Instagram Stories API doesn't support caption field directly, 
        # but we pass it for logging and potential future use
        if caption:
            logger.info(f"Story title: {caption[:80]}")
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            container_id = response.json().get("id")
            logger.info(f"IG Story container created: {container_id}")
            return container_id
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to create IG Story container: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return None

    def check_container_status(
        self, container_id: str, max_attempts: int = 30
    ) -> str:
        """Poll container status until FINISHED, ERROR, or TIMEOUT."""
        token = self.page_access_token or self.access_token
        url = f"{self.BASE_URL}/{container_id}"
        params = {"fields": "status_code,status", "access_token": token}
        for attempt in range(max_attempts):
            try:
                response = requests.get(url, params=params)
                data = response.json()
                status = data.get("status_code")
                logger.info(
                    f"Container {container_id} status: {status} (attempt {attempt+1}/{max_attempts})"
                )
                if status == "FINISHED":
                    return "FINISHED"
                elif status == "ERROR":
                    logger.error(f"Container error: {data}")
                    return "ERROR"
            except Exception as e:
                logger.error(f"Error checking container status: {e}")
            time.sleep(10)
        return "TIMEOUT"

    def publish_ig_media(self, container_id: str) -> bool:
        """Publish a prepared Instagram media container."""
        token = self.page_access_token or self.access_token
        url = f"{self.BASE_URL}/{self.ig_account_id}/media_publish"
        params = {"creation_id": container_id, "access_token": token}
        try:
            response = requests.post(url, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to publish IG media: HTTP {response.status_code}")
                logger.error(f"Response body: {response.text}")
                return False
            logger.info(f"IG media published: {response.json()}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish IG media: {e}")
            return False

    # ── Facebook ─────────────────────────────────────────────────

    def create_fb_reel(self, video_url: str, caption: str) -> bool:
        """Create and publish a Facebook Reel (3-step process)."""
        token = self.page_access_token or self.access_token
        if not token:
            logger.error("No access token available for FB Reel")
            return False

        # Step 1: Initialize upload
        url = f"{self.BASE_URL}/{self.fb_page_id}/video_reels"
        params = {"upload_phase": "START", "access_token": token}
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            video_id = response.json().get("video_id")
            logger.info(f"FB Reel upload started: {video_id}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to start FB Reel: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return False

        # Step 2: Upload video
        upload_url = f"https://rupload.facebook.com/video-upload/{self.API_VERSION}/{video_id}"
        headers = {"Authorization": f"OAuth {token}", "file_url": video_url}
        try:
            response = requests.post(upload_url, headers=headers)
            response.raise_for_status()
            logger.info("FB Reel video uploaded successfully")
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to upload FB Reel video: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return False

        # Step 3: Publish
        params = {
            "upload_phase": "FINISH",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
            "access_token": token,
        }
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            logger.info("FB Reel published successfully")
            return True
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to publish FB Reel: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return False

    def create_fb_feed_video(self, video_url: str, caption: str) -> bool:
        """Post a video to the Facebook Page feed."""
        token = self.page_access_token or self.access_token
        if not token:
            logger.error("No access token available for FB Feed")
            return False

        url = f"{self.BASE_URL}/{self.fb_page_id}/videos"
        params = {
            "file_url": video_url,
            "description": caption,
            "access_token": token,
        }
        try:
            response = requests.post(url, params=params)
            response.raise_for_status()
            logger.info(f"FB Feed video published: {response.json()}")
            return True
        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to create FB Feed video: {e}")
            if e.response:
                logger.error(f"Response: {e.response.text}")
            return False

    def is_token_valid(self) -> bool:
        """Check if the Meta access token appears valid."""
        if not self.access_token:
            return False
        if "YOUR_" in self.access_token.upper():
            return False
        if len(self.access_token) < 50:
            return False
        return True
