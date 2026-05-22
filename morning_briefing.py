"""
morning_briefing.py — Ранковий брифінг для JARVIS
Автоматично при запуску (між 5:00 і 11:00): погода + календар + пошта
"""

import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MorningBriefing:
    def __init__(self, brain, tts_callback, telegram_callback=None):
        self._brain    = brain
        self._speak    = tts_callback
        self._telegram = telegram_callback

    def run_if_morning(self):
        """Запускає брифінг в окремому потоці якщо зараз ранок (5–11)."""
        hour = datetime.now().hour
        if 5 <= hour < 11:
            threading.Thread(target=self._run, daemon=True).start()
        else:
            logger.info(f"[BRIEFING] Не ранок ({hour}:xx) — брифінг пропущено")

    def run_now(self):
        """Примусовий запуск — для тестування або по команді."""
        threading.Thread(target=self._run, daemon=True).start()

    # ------------------------------------------------------------------ #

    def _run(self):
        """Збирає дані і зачитує брифінг."""
        time.sleep(8)   # чекаємо поки всі модулі підняться

        parts = []

        # 1. Привітання з часом
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning, Sir."
        elif hour < 18:
            greeting = "Good afternoon, Sir."
        else:
            greeting = "Good evening, Sir."

        parts.append(greeting)

        # 2. Погода
        try:
            from weather_alert import WeatherAlert
            weather_raw = self._brain.nav_module and self._get_weather()
            if weather_raw:
                # Беремо тільки перші два рядки (місто + температура)
                lines = weather_raw.split("|")
                if len(lines) >= 2:
                    parts.append(f"Weather: {lines[0]}, {lines[1].strip()}.")
                else:
                    parts.append(f"Weather: {weather_raw}.")
        except Exception as e:
            logger.warning(f"[BRIEFING] Weather error: {e}")

        # 3. Календар
        try:
            if self._brain.calendar:
                cal_summary = self._brain.calendar.get_upcoming_summary(hours=12)
                parts.append(cal_summary)
        except Exception as e:
            logger.warning(f"[BRIEFING] Calendar error: {e}")

        # 4. Пошта
        try:
            if self._brain.gmail:
                emails = self._brain.gmail.get_unread(max_results=3)
                if emails:
                    parts.append(f"You have {len(emails)} unread email(s).")
                else:
                    parts.append("No unread emails.")
        except Exception as e:
            logger.warning(f"[BRIEFING] Gmail error: {e}")

        # Зачитуємо все разом
        briefing = " ".join(parts)
        logger.info(f"[BRIEFING] {briefing}")
        self._speak(briefing)

        if self._telegram:
            try:
                tg_lines = [f"🌅 Morning Briefing — {datetime.now().strftime('%H:%M, %d %b')}"]
                for part in parts[1:]:
                    if part.startswith("Weather:"):
                        tg_lines.append(f"🌤 {part}")
                    elif "Upcoming" in part or "No events" in part:
                        tg_lines.append(f"📅 {part}")
                    elif "email" in part.lower():
                        tg_lines.append(f"📧 {part}")
                    else:
                        tg_lines.append(part)
                self._telegram("\n".join(tg_lines))
            except Exception as e:
                logger.warning(f"[BRIEFING] Telegram error: {e}")

    def _get_weather(self) -> str:
        """Отримує поточну погоду."""
        try:
            import requests as req
            self._brain.nav_module.update_my_location()
            coords = self._brain.nav_module.current_coords
            city = str(coords[0]) + "," + str(coords[1])
            r = req.get("https://wttr.in/" + city + "?format=j1&lang=en", timeout=6)
            if r.status_code != 200:
                return ""
            data = r.json()
            nearest  = data.get("nearest_area", [{}])[0]
            city_name = nearest.get("areaName", [{}])[0].get("value", "")
            country   = nearest.get("country",  [{}])[0].get("value", "")
            cur       = data.get("current_condition", [{}])[0]
            desc      = cur.get("weatherDesc", [{}])[0].get("value", "")
            temp      = cur.get("temp_C", "?")
            feels     = cur.get("FeelsLikeC", "?")
            location  = city_name + (", " + country if country else "")
            return location + "|" + desc + " " + temp + "\xb0C (feels " + feels + "\xb0C)"
        except Exception as e:
            logger.debug(f"[BRIEFING] weather fetch error: {e}")
            return ""