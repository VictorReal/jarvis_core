"""
weather_alert.py — Фоновий моніторинг погоди для JARVIS.

Можливості:
  • Погода при старті у HUD (надійно — з ретраями, не залежить від таймінгу браузера).
  • Поточні умови кожні 30 хв у HUD.
  • ЗАВЧАСНЕ попередження: дивиться погодинний прогноз і за ~годину до дощу/снігу/
    грози шле в Telegram "погода змінюється з X на Y".
"""

import threading
import time
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# Тривожні явища (підрядок у weatherDesc прогнозу)
ALERT_KEYWORDS = [
    "rain", "drizzle", "storm", "thunder", "snow", "blizzard",
    "sleet", "hail", "freezing", "fog", "tornado", "shower",
]

CHECK_INTERVAL_MIN = 30          # як часто оновлювати поточну погоду в HUD
FORECAST_LOOKAHEAD_H = 2         # на скільки годин уперед дивитись прогноз
ALERT_COOLDOWN_MIN = 90          # не повторювати той самий алерт частіше


class WeatherAlert:
    def __init__(self, nav_module, tts_callback=None, telegram_callback=None):
        self._nav = nav_module
        self._speak = tts_callback or (lambda t: print(f"[WEATHER ALERT] {t}"))
        self._telegram = telegram_callback
        self._running = False
        self._thread = None
        self._last_condition = None       # останній короткий desc поточної погоди
        self._last_alert_key = None       # який саме алерт уже слали
        self._last_alert_at = 0           # коли (epoch) слали останній алерт

    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._initial_load, daemon=True, name="WeatherInit").start()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WeatherAlert")
        self._thread.start()
        logger.info("[WEATHER] Моніторинг запущено")

    def stop(self):
        self._running = False

    def fetch_now(self, city: str = "") -> str:
        return self._fetch(city)

    # ------------------------------------------------------------------ #

    def _initial_load(self):
        """
        Надійне завантаження погоди при старті.
        Проблема раніше: emit летів до того, як браузер підключив socket, тож
        погода з'являлась лише після оновлення/першого діалогу. Рішення —
        отримати погоду рано і кілька разів запушити (push зберігає в hud_state,
        тож кожен новий клієнт одразу побачить актуальне).
        """
        # Коротка пауза + оновлення координат (не блокуюче — у своєму потоці)
        time.sleep(2)
        try:
            self._nav.update_my_location()
        except Exception as e:
            logger.info(f"[WEATHER] update_my_location при старті: {e}")

        # Наполегливий ретрай: wttr.in на старті часто моргає / повільний,
        # бо одночасно вантажиться багато модулів. Пробуємо кілька разів.
        data = None
        for attempt in range(6):
            data = self._fetch_data()
            if data:
                break
            logger.info(f"[WEATHER] Старт: спроба {attempt+1}/6 невдала, повтор за 10с")
            time.sleep(10)
        if not data:
            logger.warning("[WEATHER] Початкова погода недоступна після 6 спроб — "
                           "цикл оновлення спробує далі")
            return

        weather = self._format_current(data)
        if not weather:
            return
        self._last_condition = self._current_desc(data)

        # Кілька пушів з інтервалом — щоб точно застати момент, коли браузер
        # під'єднав socket (push зберігає в hud_state → нові клієнти бачать одразу).
        for delay in (0, 3, 5, 10):
            if not self._running:
                break
            if delay:
                time.sleep(delay)
            self._push_hud(weather)
        logger.info(f"[WEATHER] Початкова погода: {weather}")

    def _loop(self):
        """Головний цикл — поточна погода + завчасні попередження."""
        time.sleep(CHECK_INTERVAL_MIN * 60)
        while self._running:
            try:
                self._check()
            except Exception as e:
                logger.warning(f"[WEATHER] Помилка перевірки: {e}")
            time.sleep(CHECK_INTERVAL_MIN * 60)

    def _check(self):
        data = self._fetch_data()
        if not data:
            return

        # 1) оновлюємо HUD поточною погодою
        weather = self._format_current(data)
        if weather:
            self._push_hud(weather)

        cur_desc = self._current_desc(data)

        # 2) дивимось прогноз на найближчі години — чи насувається тривожне явище
        upcoming = self._upcoming_alert(data)
        if upcoming:
            when_label, fc_desc = upcoming
            self._maybe_alert(cur_desc, fc_desc, when_label)

        self._last_condition = cur_desc

    # ------------------------------------------------------------------ #
    # Алерти
    # ------------------------------------------------------------------ #

    def _maybe_alert(self, current_desc: str, forecast_desc: str, when_label: str):
        """Шле завчасне попередження, якщо тривожне явище ще не анонсоване."""
        key = forecast_desc.lower().strip()
        now = time.time()

        # антидубль: той самий тип явища нещодавно вже анонсували
        if key == self._last_alert_key and (now - self._last_alert_at) < ALERT_COOLDOWN_MIN * 60:
            return

        cur = (current_desc or "current conditions").strip()
        when_phrase = when_label if when_label.startswith("in") else when_label
        msg_voice = (
            f"Sir, weather change ahead. {forecast_desc} expected {when_label}. "
            f"Currently {cur}."
        )
        msg_tg = (
            f"\U0001f327\ufe0f Weather change {when_phrase}\n"
            f"From: {cur}\n"
            f"To: {forecast_desc}"
        )
        logger.info(f"[WEATHER ALERT] {msg_tg}")
        try:
            from modules.hud_module import log_activity
            log_activity(f"Weather: {forecast_desc} {when_label}", "weather")
        except Exception:
            pass
        try:
            self._speak(msg_voice)
        except Exception:
            pass
        if self._telegram:
            try:
                self._telegram(msg_tg)
            except Exception as e:
                logger.warning(f"[WEATHER] Telegram alert failed: {e}")

        self._last_alert_key = key
        self._last_alert_at = now

    def _upcoming_alert(self, data: dict):
        """
        Дивиться погодинний прогноз на FORECAST_LOOKAHEAD_H годин уперед.
        Повертає (when_label, desc) для першого тривожного явища, або None.
        wttr.in дає 3-годинні блоки: time = "0","300","600"... (год*100).
        """
        try:
            today = data.get("weather", [{}])[0]
            hourly = today.get("hourly", [])
            if not hourly:
                return None

            now_h = datetime.now().hour
            for block in hourly:
                try:
                    block_h = int(block.get("time", "0")) // 100
                except ValueError:
                    continue
                diff = block_h - now_h
                # тільки найближчі блоки попереду (1..lookahead год)
                if diff <= 0 or diff > FORECAST_LOOKAHEAD_H:
                    continue
                desc = block.get("weatherDesc", [{}])[0].get("value", "").strip()
                chance_rain = int(block.get("chanceofrain", "0") or 0)
                chance_snow = int(block.get("chanceofsnow", "0") or 0)
                desc_l = desc.lower()
                triggered = any(kw in desc_l for kw in ALERT_KEYWORDS)
                # додатково: висока ймовірність опадів навіть якщо desc нейтральний
                if not triggered and (chance_rain >= 60 or chance_snow >= 60):
                    triggered = True
                if triggered:
                    when_label = "within the hour" if diff == 1 else f"in about {diff} hours"
                    return (when_label, desc or "precipitation")
            return None
        except Exception as e:
            logger.debug(f"[WEATHER] forecast parse error: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Отримання / форматування
    # ------------------------------------------------------------------ #

    def _fetch_data(self, city: str = "") -> dict | None:
        """Сирий JSON від wttr.in. Пробує координати, потім фолбек на назву міста."""
        targets = []
        if city:
            targets.append(city)
        else:
            coords = self._nav.current_coords
            if coords and coords[0] is not None:
                targets.append(f"{coords[0]},{coords[1]}")
            # фолбек: назва міста (якщо координатний запит не вдасться)
            targets.append("Vinnytsia")

        for target in targets:
            try:
                r = requests.get(f"https://wttr.in/{target}?format=j1&lang=en", timeout=15)
                if r.status_code != 200:
                    logger.info(f"[WEATHER] wttr.in статус {r.status_code} для {target}")
                    continue
                data = r.json()
                # перевірка що є реальні дані
                if data.get("current_condition"):
                    return data
            except Exception as e:
                logger.info(f"[WEATHER] fetch error ({target}): {e}")
                continue
        return None

    def _current_desc(self, data: dict) -> str:
        try:
            cur = data.get("current_condition", [{}])[0]
            return cur.get("weatherDesc", [{}])[0].get("value", "").strip()
        except Exception:
            return ""

    def _format_current(self, data: dict) -> str:
        """Формує рядок для HUD: 'Місто|Опис TEMP°C (feels X°C)|Wind ... Humidity ...'."""
        try:
            nearest   = data.get("nearest_area", [{}])[0]
            city_name = nearest.get("areaName", [{}])[0].get("value", "")
            country   = nearest.get("country", [{}])[0].get("value", "")
            cur       = data.get("current_condition", [{}])[0]
            desc      = cur.get("weatherDesc", [{}])[0].get("value", "")
            temp      = cur.get("temp_C", "?")
            feels     = cur.get("FeelsLikeC", "?")
            wind_spd  = cur.get("windspeedKmph", "?")
            wind_dir  = cur.get("winddir16Point", "")
            humidity  = cur.get("humidity", "?")
            # не пушимо явно биту погоду
            if temp == "?" and not desc:
                return ""
            location = city_name + (", " + country if country else "")
            line1 = location
            line2 = desc + "  " + temp + "\xb0C (feels " + feels + "\xb0C)"
            line3 = "Wind: " + wind_dir + " " + wind_spd + " km/h  Humidity: " + humidity + "%"
            return line1 + "|" + line2 + "|" + line3
        except Exception as e:
            logger.info(f"[WEATHER] format error: {e}")
            return ""

    # сумісність зі старим кодом, який міг кликати _fetch()
    def _fetch(self, city: str = "") -> str:
        data = self._fetch_data(city)
        return self._format_current(data) if data else ""

    def _push_hud(self, weather_text: str):
        if not weather_text:
            return
        try:
            from modules.hud_module import update_hud
            update_hud("weather", weather_text)
        except Exception as e:
            logger.debug(f"[WEATHER] push_hud error: {e}")