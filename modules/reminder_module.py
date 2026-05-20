"""
reminder_module.py — Модуль нагадувань для JARVIS
Підтримує: голосовий алерт, текстовий лог, кілька паралельних нагадувань
"""

import threading
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ReminderModule:
    def __init__(self, tts_callback=None):
        """
        tts_callback — функція speak(text) з твого main.py
        Якщо None — просто print в консоль.
        """
        self._speak = tts_callback or (lambda text: print(f"\n[REMINDER] 🔔 {text}"))
        self._active: dict[str, threading.Timer] = {}  # id → Timer
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  Публічний API                                                        #
    # ------------------------------------------------------------------ #

    def set(self, message: str, seconds: int) -> str:
        """
        Встановлює нагадування через `seconds` секунд з текстом `message`.
        Повертає людино-читаний рядок для Джарвіса.
        """
        reminder_id = f"r_{int(time.time())}"
        fire_at = datetime.now() + timedelta(seconds=seconds)

        timer = threading.Timer(seconds, self._fire, args=[reminder_id, message])
        timer.daemon = True
        timer.start()

        with self._lock:
            self._active[reminder_id] = timer

        logger.info(f"[REMINDER] Встановлено '{message}' о {fire_at.strftime('%H:%M:%S')}")
        return reminder_id

    def cancel(self, reminder_id: str) -> bool:
        """Скасовує нагадування за id."""
        with self._lock:
            timer = self._active.pop(reminder_id, None)
        if timer:
            timer.cancel()
            logger.info(f"[REMINDER] Скасовано {reminder_id}")
            return True
        return False

    def list_active(self) -> list[dict]:
        """Повертає список активних нагадувань (для HUD або голосу)."""
        with self._lock:
            return [{"id": k, "alive": v.is_alive()} for k, v in self._active.items()]

    # ------------------------------------------------------------------ #
    #  Внутрішнє                                                           #
    # ------------------------------------------------------------------ #

    def _fire(self, reminder_id: str, message: str):
        """Викликається Timer-ом коли час вийшов."""
        with self._lock:
            self._active.pop(reminder_id, None)

        alert = f"Sir, reminder: {message}"
        logger.info(f"[REMINDER] 🔔 {alert}")

        # Голосовий алерт (3 спроби якщо TTS зайнятий)
        for _ in range(3):
            try:
                self._speak(alert)
                break
            except Exception as e:
                logger.warning(f"[REMINDER] TTS помилка: {e}")
                time.sleep(1)
