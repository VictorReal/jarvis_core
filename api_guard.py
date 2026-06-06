"""
api_guard.py — Захист від перевищення лімітів Google API
Зберігає лічильники в api_usage.json, скидає щомісяця.
Використання:
    from api_guard import guard
    if not guard.check("vision"):
        return "Sir, Vision API monthly limit reached."
    # робимо запит
    guard.increment("vision")
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

USAGE_FILE = Path("api_usage.json")

# Місячні ліміти — після яких зупиняємось (80% від безкоштовного)
# Можна змінити вручну
LIMITS = {
    "vision":     800,    # 80% від 1000 безкоштовних
    "directions": 500,    # консервативно, у нас $300 кредиту
    "places":     800,    # геопошук (Places Text Search New), консервативно
    "youtube":    8000,   # 80% від 10000 units/день * 30
    "gmail":      5000,   # дуже щедро, практично безлімітно
    "calendar":   5000,
}


class ApiGuard:
    def __init__(self):
        self._data = self._load()

    # ------------------------------------------------------------------ #

    def check(self, api: str) -> bool:
        """
        Перевіряє чи можна робити запит.
        True — можна. False — ліміт вичерпано.
        """
        self._maybe_reset()
        limit = LIMITS.get(api)
        if limit is None:
            return True  # невідомий API — не блокуємо

        used = self._data["usage"].get(api, 0)
        if used >= limit:
            logger.warning(
                f"[API GUARD] {api.upper()} ліміт вичерпано: {used}/{limit} цього місяця"
            )
            return False
        return True

    def increment(self, api: str, count: int = 1):
        """Збільшує лічильник після успішного запиту."""
        self._maybe_reset()
        self._data["usage"][api] = self._data["usage"].get(api, 0) + count
        self._save()

    def status(self) -> str:
        """Повертає рядок зі статусом використання всіх API."""
        self._maybe_reset()
        month = self._data.get("month", "?")
        lines = [f"API usage for {month}:"]
        for api, limit in LIMITS.items():
            used = self._data["usage"].get(api, 0)
            pct  = round(used / limit * 100) if limit else 0
            lines.append(f"  {api:12} {used:5}/{limit}  ({pct}%)")
        return "\n".join(lines)

    def reset(self, api: str = ""):
        """Скидає лічильник — для ручного скидання."""
        if api:
            self._data["usage"][api] = 0
        else:
            self._data["usage"] = {}
        self._save()
        logger.info(f"[API GUARD] Скинуто: {api or 'all'}")

    # ------------------------------------------------------------------ #

    def _current_month(self) -> str:
        return datetime.now().strftime("%Y-%m")

    def _maybe_reset(self):
        """Скидає лічильники якщо настав новий місяць."""
        current = self._current_month()
        if self._data.get("month") != current:
            logger.info(f"[API GUARD] Новий місяць {current} — скидаємо лічильники")
            self._data = {"month": current, "usage": {}}
            self._save()

    def _load(self) -> dict:
        try:
            if USAGE_FILE.exists():
                data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
                if "month" in data and "usage" in data:
                    return data
        except Exception as e:
            logger.warning(f"[API GUARD] Помилка читання: {e}")
        return {"month": self._current_month(), "usage": {}}

    def _save(self):
        try:
            USAGE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[API GUARD] Помилка збереження: {e}")


# Singleton — імпортується один раз, використовується скрізь
guard = ApiGuard()