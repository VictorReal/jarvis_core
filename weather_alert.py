"""
weather_alert.py — Фоновий моніторинг погоди для JARVIS
Перевіряє погоду кожні 30 хв, якщо з'явився дощ/гроза/сніг — голосовий алерт.
Також завантажує погоду при старті для HUD.
"""

import threading
import time
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# Тригери для алертів — якщо будь-яке з цих слів з'явилось у погоді
ALERT_KEYWORDS = [
    "rain", "drizzle", "storm", "thunder", "snow", "blizzard",
    "sleet", "hail", "freezing", "heavy", "fog", "tornado",
]

# Скільки хвилин між перевірками
CHECK_INTERVAL_MIN = 30


class WeatherAlert:
    def __init__(self, nav_module, tts_callback=None):
        """
        nav_module    — NavigationModule (для координат)
        tts_callback  — функція speak(text), якщо None — тільки print
        """
        self._nav = nav_module
        self._speak = tts_callback or (lambda t: print(f"[WEATHER ALERT] {t}"))
        self._running = False
        self._thread = None
        self._last_condition = None   # остання відома погода (рядок)

    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            return
        self._running = True
        # Перша перевірка — одразу, щоб HUD мав погоду при старті
        threading.Thread(target=self._initial_load, daemon=True).start()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WeatherAlert")
        self._thread.start()
        logger.info("[WEATHER] Моніторинг запущено")

    def stop(self):
        self._running = False

    def fetch_now(self, city: str = "") -> str:
        """Публічний метод — отримати погоду прямо зараз."""
        return self._fetch(city)

    # ------------------------------------------------------------------ #

    def _initial_load(self):
        """Завантажує погоду одразу при запуску і пушить у HUD."""
        time.sleep(5)   # чекаємо поки HUD і браузер підключились
        # Оновлюємо координати перед fetch — щоб не брати дефолтні
        try:
            self._nav.update_my_location()
        except Exception:
            pass
        weather = self._fetch()
        if weather:
            self._push_hud(weather)
            self._last_condition = weather
            logger.info(f"[WEATHER] Початкова погода: {weather}")

    def _loop(self):
        """Головний цикл — кожні 30 хв порівнює погоду."""
        # Перша перевірка через 30 хв (початкову вже зробив _initial_load)
        time.sleep(CHECK_INTERVAL_MIN * 60)
        while self._running:
            try:
                self._check()
            except Exception as e:
                logger.warning(f"[WEATHER] Помилка перевірки: {e}")
            time.sleep(CHECK_INTERVAL_MIN * 60)

    def _check(self):
        new = self._fetch()
        if not new:
            return

        self._push_hud(new)

        if self._last_condition is None:
            self._last_condition = new
            return

        # Перевіряємо чи з'явились нові тривожні умови
        old_lower = self._last_condition.lower()
        new_lower = new.lower()

        appeared = [kw for kw in ALERT_KEYWORDS
                    if kw in new_lower and kw not in old_lower]

        if appeared:
            condition_word = appeared[0].capitalize()
            alert = (
                f"Sir, weather update: {condition_word} conditions detected. "
                f"Current: {new.strip()}."
            )
            logger.info(f"[WEATHER ALERT] {alert}")
            self._speak(alert)

        self._last_condition = new

    def _fetch(self, city: str = "") -> str:
        """Завантажує погоду через wttr.in і повертає читабельний рядок."""
        try:
            if not city:
                coords = self._nav.current_coords
                city = str(coords[0]) + "," + str(coords[1])

            r = requests.get("https://wttr.in/" + city + "?format=j1&lang=en", timeout=6)
            if r.status_code != 200:
                return ""

            data = r.json()
            nearest  = data.get("nearest_area", [{}])[0]
            city_name = nearest.get("areaName",  [{}])[0].get("value", "")
            country   = nearest.get("country",   [{}])[0].get("value", "")
            cur       = data.get("current_condition", [{}])[0]
            desc      = cur.get("weatherDesc",   [{}])[0].get("value", "")
            temp      = cur.get("temp_C", "?")
            feels     = cur.get("FeelsLikeC", "?")
            wind_spd  = cur.get("windspeedKmph", "?")
            wind_dir  = cur.get("winddir16Point", "")
            humidity  = cur.get("humidity", "?")

            location = city_name + (", " + country if country else "")
            line1 = location
            line2 = desc + "  " + temp + "\xb0C (feels " + feels + "\xb0C)"
            line3 = "Wind: " + wind_dir + " " + wind_spd + " km/h  Humidity: " + humidity + "%"
            return line1 + "|" + line2 + "|" + line3

        except Exception as e:
            logger.debug("[WEATHER] fetch error: " + str(e))
        return ""

    def _push_hud(self, weather_text: str):
        try:
            from modules.hud_module import update_hud
            update_hud("weather", weather_text)
        except Exception:
            pass