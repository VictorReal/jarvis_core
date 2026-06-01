"""
reminder_module.py — Модуль нагадувань для JARVIS з персистенцією.

Особливості:
- threading.Timer для точного спрацьовування (без polling)
- JSON-файл (data/reminders.json) — пережиє рестарт системи
- При запуску: майбутні reminders продовжують відлік, прострочені — спрацьовують з затримкою
- HUD оновлюється на set/cancel/fire + ticker кожні 10 сек
- TTS retry до 3 разів якщо озвучка зайнята
"""

import os
import json
import uuid
import threading
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REMINDERS_FILE = Path("data/reminders.json")
REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)


class ReminderModule:
    def __init__(self, tts_callback=None):
        """
        tts_callback — функція speak(text) з main.py.
        Якщо None — print у консоль.
        """
        self._speak = tts_callback or (lambda text: print(f"\n[REMINDER] 🔔 {text}"))
        # id → {"timer": Timer, "message": str, "fire_at": datetime, "source": str}
        self._active: dict = {}
        self._lock = threading.Lock()
        self._ticker_running = False

        # Підняти збережені з диску
        self._load_from_disk()

    # ------------------------------------------------------------------ #
    #  ПУБЛІЧНИЙ API                                                       #
    # ------------------------------------------------------------------ #

    def set(self, message: str, seconds: int, source: str = "voice") -> str:
        """Встановлює нагадування через `seconds` секунд."""
        reminder_id = "r_" + uuid.uuid4().hex[:8]
        fire_at = datetime.now() + timedelta(seconds=max(seconds, 1))

        timer = threading.Timer(max(seconds, 1), self._fire, args=[reminder_id, message])
        timer.daemon = True
        timer.start()

        with self._lock:
            self._active[reminder_id] = {
                "timer":   timer,
                "message": message,
                "fire_at": fire_at,
                "source":  source,
            }

        self._save_to_disk()
        self._push_hud()
        self._start_hud_ticker()
        logger.info(f"[REMINDER] Встановлено '{message}' на {fire_at.strftime('%Y-%m-%d %H:%M:%S')} (id={reminder_id})")
        try:
            from modules.hud_module import log_activity
            log_activity(f"Reminder set: {message}", "reminder")
        except Exception:
            pass
        return reminder_id

    def cancel(self, reminder_id: str) -> bool:
        """Скасовує нагадування за id."""
        with self._lock:
            entry = self._active.pop(reminder_id, None)
        if entry:
            try:
                entry["timer"].cancel()
            except Exception:
                pass
            self._save_to_disk()
            self._push_hud()
            logger.info(f"[REMINDER] Скасовано {reminder_id}")
            return True
        return False

    def cancel_by_message(self, message_substring: str) -> int:
        """Скасовує всі нагадування що містять `message_substring` (case-insensitive)."""
        sub = message_substring.lower().strip()
        cancelled = []
        with self._lock:
            for rid, entry in list(self._active.items()):
                if sub in entry["message"].lower():
                    try:
                        entry["timer"].cancel()
                    except Exception:
                        pass
                    del self._active[rid]
                    cancelled.append(rid)
        if cancelled:
            self._save_to_disk()
            self._push_hud()
            logger.info(f"[REMINDER] Скасовано {len(cancelled)} за збігом '{message_substring}'")
        return len(cancelled)

    def list_active(self) -> list:
        """Список активних — для HUD та голосових запитів."""
        now = datetime.now()
        out = []
        with self._lock:
            for rid, entry in self._active.items():
                secs_left = max(0, int((entry["fire_at"] - now).total_seconds()))
                out.append({
                    "id":           rid,
                    "message":      entry["message"],
                    "fire_at":      entry["fire_at"].isoformat(),
                    "seconds_left": secs_left,
                    "time_left":    self._format_time_left(secs_left),
                    "source":       entry.get("source", "voice"),
                })
        out.sort(key=lambda x: x["seconds_left"])
        return out

    def clear_all(self) -> int:
        """Видалити всі нагадування."""
        with self._lock:
            count = len(self._active)
            for entry in self._active.values():
                try:
                    entry["timer"].cancel()
                except Exception:
                    pass
            self._active.clear()
        self._save_to_disk()
        self._push_hud()
        logger.info(f"[REMINDER] Очищено всі ({count})")
        return count

    # ------------------------------------------------------------------ #
    #  ПЕРСИСТЕНЦІЯ                                                        #
    # ------------------------------------------------------------------ #

    def _save_to_disk(self):
        """Зберігає поточний стан в JSON. Timer не серіалізуємо."""
        try:
            with self._lock:
                snapshot = [
                    {
                        "id":      rid,
                        "message": entry["message"],
                        "fire_at": entry["fire_at"].isoformat(),
                        "source":  entry.get("source", "voice"),
                    }
                    for rid, entry in self._active.items()
                ]
            with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[REMINDER] Помилка збереження: {e}")

    def _load_from_disk(self):
        """При запуску — підняти всі reminders з JSON, перепланувати Timer-и."""
        if not REMINDERS_FILE.exists():
            return
        try:
            with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"[REMINDER] Не вдалось завантажити {REMINDERS_FILE}: {e}")
            return

        if not data:
            return

        now = datetime.now()
        overdue_count = 0
        scheduled_count = 0

        for item in data:
            try:
                rid = item["id"]
                message = item["message"]
                fire_at = datetime.fromisoformat(item["fire_at"])
                source = item.get("source", "voice")

                delta = (fire_at - now).total_seconds()
                if delta <= 0:
                    # Прострочене — фаєримо з затримкою 8 сек щоб TTS встиг прокинутись
                    overdue_count += 1
                    overdue_secs = int(-delta)
                    timer = threading.Timer(
                        8 + overdue_count * 3,  # рознести в часі якщо їх декілька
                        self._fire_overdue,
                        args=[rid, message, overdue_secs]
                    )
                else:
                    # Майбутнє — продовжуємо відлік
                    scheduled_count += 1
                    timer = threading.Timer(delta, self._fire, args=[rid, message])

                timer.daemon = True
                timer.start()

                with self._lock:
                    self._active[rid] = {
                        "timer":   timer,
                        "message": message,
                        "fire_at": fire_at,
                        "source":  source,
                    }
            except Exception as e:
                logger.error(f"[REMINDER] Помилка завантаження {item}: {e}")

        logger.info(f"[REMINDER] Завантажено {scheduled_count} активних + {overdue_count} прострочених")
        self._start_hud_ticker()

    # ------------------------------------------------------------------ #
    #  HUD                                                                 #
    # ------------------------------------------------------------------ #

    def _push_hud(self):
        """Оновлення панелі нагадувань у HUD."""
        try:
            from modules.hud_module import update_reminders
            items = [
                {"message": r["message"], "time_left": r["time_left"]}
                for r in self.list_active()
            ]
            update_reminders(items)
        except Exception:
            pass

    def _start_hud_ticker(self):
        """Фоновий потік — оновлює таймер у HUD кожні 10 сек."""
        if self._ticker_running:
            return

        def _tick():
            self._ticker_running = True
            try:
                while True:
                    with self._lock:
                        has_active = bool(self._active)
                    if not has_active:
                        break
                    self._push_hud()
                    time.sleep(10)
            finally:
                self._ticker_running = False

        threading.Thread(target=_tick, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  FIRE                                                                #
    # ------------------------------------------------------------------ #

    def _fire(self, reminder_id: str, message: str):
        """Викликається Timer-ом коли час вийшов."""
        with self._lock:
            self._active.pop(reminder_id, None)
        self._save_to_disk()
        self._push_hud()

        alert = f"Sir, reminder: {message}"
        logger.info(f"[REMINDER] 🔔 {alert}")
        try:
            from modules.hud_module import log_activity
            log_activity(f"Reminder: {message}", "reminder")
        except Exception:
            pass
        self._speak_with_retry(alert)

    def _fire_overdue(self, reminder_id: str, message: str, overdue_seconds: int):
        """Прострочений reminder — повідомляє з вказівкою скільки минуло."""
        with self._lock:
            self._active.pop(reminder_id, None)
        self._save_to_disk()
        self._push_hud()

        if overdue_seconds < 3600:
            ago = f"{overdue_seconds // 60} minutes ago"
        elif overdue_seconds < 86400:
            ago = f"{overdue_seconds // 3600} hours ago"
        else:
            ago = f"{overdue_seconds // 86400} days ago"

        alert = f"Sir, missed reminder from {ago}: {message}"
        logger.info(f"[REMINDER] 🔔 (overdue) {alert}")
        self._speak_with_retry(alert)

    def _speak_with_retry(self, text: str, attempts: int = 3):
        for _ in range(attempts):
            try:
                self._speak(text)
                return
            except Exception as e:
                logger.warning(f"[REMINDER] TTS помилка: {e}")
                time.sleep(1)

    # ------------------------------------------------------------------ #
    #  УТИЛІТИ                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_time_left(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        if seconds < 86400:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            return f"{h}h {m}m" if m else f"{h}h"
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        return f"{d}d {h}h" if h else f"{d}d"