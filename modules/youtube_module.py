"""
youtube_module.py — пошук відео через YouTube Data API v3 для JARVIS.

Потрібен безкоштовний ключ у .env:
    YOUTUBE_API_KEY=...
(console.cloud.google.com → YouTube Data API v3 → Enable → Credentials → API key)

Квота: ~10000 одиниць/день, пошук ≈ 100 одиниць → ~100 пошуків/день.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YouTubeModule:
    def __init__(self):
        self._key = os.getenv("YOUTUBE_API_KEY")

    def available(self) -> bool:
        return bool(self._key)

    def search(self, query: str, max_results: int = 5) -> dict:
        """
        Шукає відео. Повертає dict:
          {"ok": True, "items": [{videoId, title, channel, thumbnail}], "query": ...}
          {"ok": False, "error": "..."}
        """
        if not self._key:
            return {"ok": False, "error": "YOUTUBE_API_KEY not set in .env"}
        if not query or not query.strip():
            return {"ok": False, "error": "Empty query"}

        try:
            params = {
                "part": "snippet",
                "q": query.strip(),
                "type": "video",
                "maxResults": max(1, min(int(max_results), 10)),
                "key": self._key,
            }
            r = requests.get(SEARCH_URL, params=params, timeout=10)
            if r.status_code == 403:
                return {"ok": False, "error": "API quota exceeded or key invalid"}
            if r.status_code != 200:
                return {"ok": False, "error": f"YouTube API status {r.status_code}"}
            data = r.json()
            items = []
            for it in data.get("items", []):
                vid = it.get("id", {}).get("videoId")
                sn = it.get("snippet", {})
                if not vid:
                    continue
                thumbs = sn.get("thumbnails", {})
                thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
                items.append({
                    "videoId": vid,
                    "title": sn.get("title", ""),
                    "channel": sn.get("channelTitle", ""),
                    "thumbnail": thumb,
                })
            return {"ok": True, "items": items, "query": query.strip()}
        except Exception as e:
            logger.warning(f"[YOUTUBE] search error: {e}")
            return {"ok": False, "error": str(e)}