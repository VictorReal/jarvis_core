"""
calendar_notifier.py — Google Calendar → Telegram сповіщення для JARVIS
Перевіряє події кожні 5 хв, надсилає в Telegram за 30 і 10 хв до початку
"""

import threading
import time
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 5 * 60     # перевіряємо кожні 5 хв
NOTIFY_BEFORE = [30, 10]        # сповіщаємо за 30 і 10 хв


class CalendarNotifier:
    def __init__(self, calendar_module, notify_callback, tts_callback=None):
        """
        calendar_module  — CalendarModule
        notify_callback  — telegram.notify_owner(text)
        tts_callback     — safe_speak(text), опційно
        """
        self._cal     = calendar_module
        self._notify  = notify_callback
        self._speak   = tts_callback
        self._running = False
        self._thread  = None
        # Зберігаємо вже надіслані сповіщення щоб не дублювати
        # ключ: (event_title, start_raw, minutes_before)
        self._sent: set = set()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="CalendarNotifier"
        )
        self._thread.start()
        logger.info("[CALENDAR NOTIFIER] Запущено")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #

    def _loop(self):
        while self._running:
            try:
                self._check()
            except Exception as e:
                logger.warning(f"[CALENDAR NOTIFIER] Помилка: {e}")
            time.sleep(CHECK_INTERVAL_SEC)

    def _check(self):
        # Беремо події на найближчі 35 хв
        events = self._cal.get_upcoming(hours=1, max_results=10)
        now = datetime.now(timezone.utc)

        for event in events:
            start_raw = event.get("start_raw", "")
            if not start_raw:
                continue

            try:
                start_dt = datetime.fromisoformat(start_raw)
                # Приводимо до UTC якщо є timezone info
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            minutes_left = (start_dt - now).total_seconds() / 60
            title = event.get("title", "Event")
            loc   = event.get("location", "")

            for threshold in NOTIFY_BEFORE:
                # Вікно ±3 хв щоб не пропустити перевірку
                if threshold - 3 <= minutes_left <= threshold + 3:
                    key = (title, start_raw, threshold)
                    if key in self._sent:
                        continue

                    self._sent.add(key)
                    time_str = start_dt.strftime("%H:%M")
                    loc_str  = f" at {loc}" if loc else ""

                    msg = (
                        f"Sir, reminder: '{title}'{loc_str} "
                        f"starts in {threshold} minutes (at {time_str})."
                    )

                    logger.info(f"[CALENDAR NOTIFIER] {msg}")

                    # Telegram
                    try:
                        self._notify("[JARVIS] " + msg)
                    except Exception as e:
                        logger.warning(f"[CALENDAR NOTIFIER] Telegram error: {e}")

                    # Голос
                    if self._speak:
                        try:
                            self._speak(msg)
                        except Exception as e:
                            logger.warning(f"[CALENDAR NOTIFIER] TTS error: {e}")

        # Чистимо старі записи (старші за 2 год)
        if len(self._sent) > 200:
            self._sent.clear()
