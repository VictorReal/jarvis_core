"""
youtube_module.py — YouTube Data API для JARVIS
Шукає відео, повертає назву, канал, тривалість, посилання
"""

import os
import logging
import webbrowser
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class YouTubeModule:
    def __init__(self):
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY не задано в .env")
        self._service = build("youtube", "v3", developerKey=api_key)

    def search(self, query: str, max_results: int = 3) -> list[dict]:
        """
        Шукає відео по запиту.
        Повертає список {title, channel, video_id, url}
        """
        try:
            response = self._service.search().list(
                q=query,
                part="snippet",
                maxResults=max_results,
                type="video",
                relevanceLanguage="en",
            ).execute()

            results = []
            for item in response.get("items", []):
                vid_id = item["id"]["videoId"]
                snippet = item["snippet"]
                results.append({
                    "title":   snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "video_id": vid_id,
                    "url":     "https://www.youtube.com/watch?v=" + vid_id,
                })
            return results

        except Exception as e:
            logger.error(f"[YOUTUBE] search error: {e}")
            return []

    def search_and_open(self, query: str) -> str:
        """Шукає і відкриває перше відео в браузері."""
        results = self.search(query, max_results=1)
        if not results:
            return f"Sir, I couldn't find any videos for '{query}'."

        video = results[0]
        webbrowser.open(video["url"])
        logger.info(f"[YOUTUBE] Відкрито: {video['title']}")
        return (
            f"Opening '{video['title']}' by {video['channel']}, Sir."
        )

    def search_summary(self, query: str) -> str:
        """Повертає список знайдених відео для Джарвіса."""
        results = self.search(query, max_results=3)
        if not results:
            return f"Sir, no videos found for '{query}'."

        lines = [f"Top results for '{query}', Sir:"]
        for i, v in enumerate(results, 1):
            lines.append(f"{i}. '{v['title']}' by {v['channel']} — {v['url']}")
        return " ".join(lines)
