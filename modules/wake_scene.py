"""
wake_scene.py — кінематографічний сценарій «wake up daddy's home».

Послідовність (Iron Man 1):
  1. Загоряння HUD — хвиля світла по панелях + спалах + імпульс стрічки
  2. Clash "Should I Stay or Should I Go" — фоном (тихо), local assets/clash.mp3
  3. «Welcome home, Sir.»
  4. Брифінг: час + погода + пошта + календар (реальні дані)
  5. Музика fade out

Викликається з main.handle_command, отримує jarvis-об'єкт (де є .brain.gmail,
.brain.calendar, .weather_alert) і функцію озвучки.
"""

import os
import time
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

CLASH_PATH = os.path.join("assets", "clash.mp3")
MUSIC_BG_VOLUME = 0.30
FADEOUT_MS = 4000


class WakeScene:
    def __init__(self, jarvis, speak_func):
        self.jarvis = jarvis
        # переданий об'єкт може бути JARVIS (має .brain) або сам Brain (має .gmail)
        inner = getattr(jarvis, "brain", None)
        self.brain = inner if inner is not None else jarvis
        self.speak = speak_func
        self._channel = None

    def play(self):
        try:
            self._fire_hud()
            self._start_music()
            # голос одразу — TTS генерується паралельно з анімацією/музикою
            full = "Welcome home, Sir. " + self._build_briefing()
            self.speak(full, "en")
            self._fade_music()
        except Exception as e:
            logger.warning(f"[WAKE] Помилка сценарію: {e}")

    def _fire_hud(self):
        try:
            from modules.hud_module import trigger_wake_scene, log_activity
            trigger_wake_scene()
            log_activity("Wake scene activated", "info")
        except Exception as e:
            logger.debug(f"[WAKE] HUD trigger: {e}")

    def _start_music(self):
        if not os.path.exists(CLASH_PATH):
            logger.info(f"[WAKE] Музика не знайдена: {CLASH_PATH}")
            return
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._sound = pygame.mixer.Sound(CLASH_PATH)
            self._channel = self._sound.play()
            if self._channel:
                self._channel.set_volume(MUSIC_BG_VOLUME)
            logger.info("[WAKE] Clash грає фоном")
        except Exception as e:
            logger.info(f"[WAKE] Музика error: {e}")

    def _fade_music(self):
        if self._channel:
            try:
                self._channel.fadeout(FADEOUT_MS)
            except Exception:
                pass

    def _build_briefing(self) -> str:
        parts = []
        hour = datetime.now().hour
        greeting = ("Good morning" if 5 <= hour < 12 else
                    "Good afternoon" if 12 <= hour < 18 else "Good evening")
        parts.append(greeting)
        # коротко: пошта + календар (без часу/дати/погоди)
        for fn in (self._mail, self._calendar):
            try:
                s = fn()
                if s:
                    parts.append(s)
            except Exception as e:
                logger.debug(f"[WAKE] briefing part: {e}")
        parts.append("all systems are online and standing by")
        return ", ".join(parts) + "."

    def _weather(self) -> str:
        wa = getattr(self.jarvis, "weather_alert", None)
        if wa is None:
            wa = getattr(self.brain, "weather_alert", None)
        try:
            if wa and hasattr(wa, "fetch_now"):
                raw = wa.fetch_now()
                if raw and "|" in raw:
                    return f"in {raw.split('|')[0]}, {raw.split('|')[1].strip()}"
                if raw:
                    return raw
        except Exception as e:
            logger.debug(f"[WAKE] weather module: {e}")
        # фолбек — прямий запит (працює навіть якщо модуля нема в переданому об'єкті)
        try:
            import requests
            r = requests.get("https://wttr.in/Vinnytsia?format=j1&lang=en", timeout=10)
            if r.status_code == 200:
                d = r.json()
                cur = d.get("current_condition", [{}])[0]
                desc = cur.get("weatherDesc", [{}])[0].get("value", "")
                temp = cur.get("temp_C", "?")
                feels = cur.get("FeelsLikeC", "?")
                area = d.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", "Vinnytsia")
                if desc:
                    return f"in {area}, {desc} {temp}\u00b0C, feels like {feels}\u00b0C"
        except Exception as e:
            logger.debug(f"[WAKE] weather fallback: {e}")
        return ""

    def _mail(self) -> str:
        gm = getattr(self.brain, "gmail", None)
        if gm and hasattr(gm, "get_unread"):
            emails = gm.get_unread(max_results=5)
            n = len(emails)
            if n == 0:
                return "you have no new mail"
            top = emails[0]["from"].split("<")[0].strip().strip('"')
            tail = f", the latest from {top}" if top else ""
            return f"you have {n} unread message{'s' if n != 1 else ''}{tail}"
        return ""

    def _calendar(self) -> str:
        cal = getattr(self.brain, "calendar", None)
        if cal and hasattr(cal, "get_upcoming"):
            events = cal.get_upcoming(hours=24, max_results=3)
            if not events:
                return "your calendar is clear for the next 24 hours"
            first = events[0]
            loc = f" at {first['location']}" if first.get("location") else ""
            extra = f", and {len(events) - 1} more" if len(events) > 1 else ""
            return f"your next event is {first['title']} at {first['start']}{loc}{extra}"
        return ""


def run_wake_scene(jarvis, speak_func):
    """Запуск сценарію в окремому потоці (не блокує обробник команд)."""
    threading.Thread(
        target=lambda: WakeScene(jarvis, speak_func).play(),
        daemon=True, name="WakeScene"
    ).start()