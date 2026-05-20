"""
vision_module.py — Google Cloud Vision API для JARVIS
Аналізує зображення: описує вміст, читає текст (OCR), визначає об'єкти
"""

import os
import base64
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)


class VisionModule:
    def __init__(self):
        self._api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY не задано в .env")
        self._url = "https://vision.googleapis.com/v1/images:annotate?key=" + self._api_key

    # ------------------------------------------------------------------ #

    def analyze_file(self, path: str) -> str:
        """Аналізує зображення з файлу. Повертає опис для Джарвіса."""
        try:
            data = Path(path).read_bytes()
            return self._analyze(base64.b64encode(data).decode())
        except FileNotFoundError:
            return f"Sir, I couldn't find the file at {path}."
        except Exception as e:
            logger.error(f"[VISION] analyze_file error: {e}")
            return f"Sir, vision analysis failed: {e}"

    def analyze_latest_screenshot(self) -> str:
        """Аналізує останній скріншот з папки ./screenshots/"""
        screenshots_dir = Path("screenshots")
        if not screenshots_dir.exists():
            return "Sir, no screenshots directory found."

        files = sorted(screenshots_dir.glob("*.png"), key=lambda f: f.stat().st_mtime)
        if not files:
            return "Sir, no screenshots found."

        latest = files[-1]
        logger.info(f"[VISION] Аналізую: {latest}")
        result = self.analyze_file(str(latest))
        return f"Screenshot analysis, Sir: {result}"

    def read_text(self, path: str) -> str:
        """OCR — читає текст з зображення."""
        try:
            data = Path(path).read_bytes()
            return self._ocr(base64.b64encode(data).decode())
        except Exception as e:
            return f"Sir, text recognition failed: {e}"

    # ------------------------------------------------------------------ #

    def _analyze(self, b64: str) -> str:
        """Надсилає зображення в Vision API, повертає опис."""
        from api_guard import guard
        if not guard.check("vision"):
            return "Sir, Vision API monthly limit reached. I'll resume next month."
        payload = {
            "requests": [{
                "image": {"content": b64},
                "features": [
                    {"type": "LABEL_DETECTION",      "maxResults": 8},
                    {"type": "OBJECT_LOCALIZATION",  "maxResults": 5},
                    {"type": "IMAGE_PROPERTIES",     "maxResults": 3},
                    {"type": "SAFE_SEARCH_DETECTION"},
                ]
            }]
        }
        r = requests.post(self._url, json=payload, timeout=15)
        r.raise_for_status()
        guard.increment("vision")
        resp = r.json()["responses"][0]

        labels  = [a["description"] for a in resp.get("labelAnnotations", [])]
        objects = [o["name"] for o in resp.get("localizedObjectAnnotations", [])]

        parts = []
        if objects:
            parts.append("Objects detected: " + ", ".join(dict.fromkeys(objects)))
        if labels:
            parts.append("Scene: " + ", ".join(labels[:5]))

        return ". ".join(parts) if parts else "I couldn't identify anything specific, Sir."

    def _ocr(self, b64: str) -> str:
        """OCR через TEXT_DETECTION."""
        from api_guard import guard
        if not guard.check("vision"):
            return "Sir, Vision API monthly limit reached. I'll resume next month."
        payload = {
            "requests": [{
                "image": {"content": b64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }
        r = requests.post(self._url, json=payload, timeout=15)
        r.raise_for_status()
        guard.increment("vision")
        resp = r.json()["responses"][0]

        annotations = resp.get("textAnnotations", [])
        if not annotations:
            return "No text found in the image, Sir."

        # Перший елемент — весь текст разом
        full_text = annotations[0]["description"].strip()
        # Обрізаємо якщо дуже довгий
        if len(full_text) > 500:
            full_text = full_text[:500] + "..."
        return full_text