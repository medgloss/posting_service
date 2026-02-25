"""
Content parser for social media content files.
Parses social_media_content.json (primary) or social_media_content.txt (fallback)
to extract title, description, and hashtags for each platform.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def parse_content_folder(folder_path: Path) -> Dict[str, str]:
    """
    Parse content from a folder, returning structured content dict.
    
    Tries JSON first, then TXT fallback.
    
    Returns:
        {
            "title": "...",
            "description": "...",
            "hashtags": "#Tag1 #Tag2 ...",
            "reel_caption": "Title\\n\\nDescription\\n\\n#Tag1 #Tag2",
            "story_caption": "Title"
        }
    """
    json_path = folder_path / "social_media_content.json"
    txt_path = folder_path / "social_media_content.txt"
    
    content = None
    
    # Try JSON first (preferred — structured data)
    if json_path.exists():
        content = _parse_json(json_path)
    
    # Fallback to TXT
    if content is None and txt_path.exists():
        content = _parse_txt(txt_path)
    
    # If nothing found, return empty
    if content is None:
        logger.warning(f"No content files found in {folder_path.name}")
        return {
            "title": "",
            "description": "",
            "hashtags": "",
            "reel_caption": "",
            "story_caption": "",
        }
    
    # Build platform-specific captions
    content["reel_caption"] = _build_reel_caption(content)
    content["story_caption"] = content["title"]
    
    return content


def _parse_json(json_path: Path) -> Optional[Dict[str, str]]:
    """Parse social_media_content.json file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Use instagram_facebook section
        ig_fb = data.get("instagram_facebook", {})
        
        title = ig_fb.get("title", "").strip()
        description = ig_fb.get("description", "").strip()
        hashtags_list = ig_fb.get("hashtags", [])
        
        # Format hashtags with # prefix
        hashtags = " ".join(
            f"#{tag}" if not tag.startswith("#") else tag
            for tag in hashtags_list
        )
        
        logger.info(f"Parsed JSON content: title='{title[:50]}...', {len(hashtags_list)} hashtags")
        return {"title": title, "description": description, "hashtags": hashtags}
    
    except Exception as e:
        logger.error(f"Failed to parse JSON {json_path}: {e}")
        return None


def _parse_txt(txt_path: Path) -> Optional[Dict[str, str]]:
    """Parse social_media_content.txt file (fallback)."""
    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        title = ""
        description = ""
        hashtags = ""
        
        # Extract Instagram/Facebook section
        ig_section = ""
        if "INSTAGRAM / FACEBOOK" in content or "📱" in content:
            # Find the IG/FB section
            lines = content.split("\n")
            in_section = False
            section_lines = []
            
            for line in lines:
                if "INSTAGRAM" in line or "📱" in line:
                    in_section = True
                    continue
                if in_section and ("YOUTUBE" in line or "🎬" in line or "======" in line):
                    break
                if in_section:
                    section_lines.append(line)
            
            ig_section = "\n".join(section_lines)
        else:
            ig_section = content
        
        # Parse Title
        title_match = re.search(r"Title:\s*(.+?)(?:\n|$)", ig_section)
        if title_match:
            title = title_match.group(1).strip()
        
        # Parse Description
        desc_match = re.search(
            r"Description:\s*\n(.+?)(?=\nHashtags:|\n\n\n|\Z)", ig_section, re.DOTALL
        )
        if desc_match:
            description = desc_match.group(1).strip()
        
        # Parse Hashtags
        hash_match = re.search(r"Hashtags:\s*\n(.+?)(?:\n\n|\Z)", ig_section, re.DOTALL)
        if hash_match:
            hashtags = hash_match.group(1).strip()
        
        logger.info(f"Parsed TXT content: title='{title[:50]}...'")
        return {"title": title, "description": description, "hashtags": hashtags}
    
    except Exception as e:
        logger.error(f"Failed to parse TXT {txt_path}: {e}")
        return None


def _build_reel_caption(content: Dict[str, str]) -> str:
    """
    Build full caption for reels and feed posts.
    Format: Title\n\nDescription\n\nHashtags
    """
    parts = []
    
    if content.get("title"):
        parts.append(content["title"])
    
    if content.get("description"):
        parts.append(content["description"])
    
    if content.get("hashtags"):
        parts.append(content["hashtags"])
    
    return "\n\n".join(parts)
