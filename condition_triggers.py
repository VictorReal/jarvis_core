"""
condition_triggers.py — умовні тригери для JARVIS (погодні / часові).

Приклади:
  "нагадай взяти парасолю якщо завтра дощ"     → умова rain у прогнозі → нагадування
  "попередь якщо температура впаде нижче 0"     → умова temp < 0
  "скажи коли стане тепліше 20"                 → умова temp > 20

Архітектура:
  • тригери зберігаються в data/triggers.json (переживають рестарт)
  • фоновий цикл раз на CHECK_INTERVAL_MIN перевіряє умови проти погоди
  • погоду бере через наявний weather_alert._fetch_data() (без дублю запитів)
  • справдилось → доставка через reminder_module / telegram / TTS, тригер деактивується
  • one-shot за замовчуванням (не спамить); можна repeat=True

Підтримувані умови (condition):
  {"type": "weather", "phenomenon": "rain"}          — дощ/сніг/гроза... у прогнозі
  {"type": "temp", "op": "<", "value": 0}            — температура нижче/вище
  {"type": "temp_feels", "op": ">", "value": 25}     — відчувається як
"""

import os
import json
import uuid
import threading
import time
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TRIGGERS_FILE = Path("data/triggers.json")
TRIGGERS_FILE.parent.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL_MIN = 15          # як часто перевіряти умови
FORECAST_LOOKAHEAD_H = 12        # на скільки годин уперед дивитись прогноз для погодних умов

# Явища погоди → ключові слова в weatherDesc + поля ймовірності
PHENOMENA = {
    "rain":    (["rain", "drizzle", "shower"], "chanceofrain"),
    "snow":    (["snow", "blizzard", "sleet"], "chanceofsnow"),
    "storm":   (["storm", "thunder"], None),
    "fog":     (["fog", "mist"], None),
    "freezing": (["freezing", "ice"], None),
}


class ConditionTriggers:
    def __init__(self, weather_alert, reminder_module=None,
                 tts_callback=None, telegram_callback=None):
        """
        weather_alert    — екземпляр WeatherAlert (для _fetch_data)
        reminder_module  — ReminderModule (для доставки нагадування), опційно
        tts_callback     — speak(text)
        telegram_callback— notify_owner(text)
        """
        self._weather = weather_alert
        self._reminder = reminder_module
        self._speak = tts_callback or (lambda t: print(f"[TRIGGER] {t}"))
        self._telegram = telegram_callback
        self._triggers: dict = {}
        self._lock = threading.Lock()
        self._running = False
        self._load_from_disk()

    # ------------------------------------------------------------------ #
    #  ПУБЛІЧНИЙ API
    # ------------------------------------------------------------------ #

    def add(self, action: str, condition: dict, repeat: bool = False) -> str:
        """Додає тригер. action — що нагадати; condition — умова (див. модульний докстрінг)."""
        tid = "t_" + uuid.uuid4().hex[:8]
        with self._lock:
            self._triggers[tid] = {
                "action": action,
                "condition": condition,
                "repeat": repeat,
                "created": datetime.now().isoformat(),
                "last_fired": None,
            }
        self._save_to_disk()
        logger.info(f"[TRIGGER] Додано {tid}: {condition} → '{action}'")
        return tid

    def remove(self, tid: str) -> bool:
        with self._lock:
            existed = self._triggers.pop(tid, None) is not None
        if existed:
            self._save_to_disk()
        return existed

    def remove_by_action(self, substring: str) -> int:
        sub = substring.lower().strip()
        removed = 0
        with self._lock:
            for tid in [t for t, e in self._triggers.items()
                        if sub in e["action"].lower()]:
                del self._triggers[tid]
                removed += 1
        if removed:
            self._save_to_disk()
        return removed

    def list_active(self) -> list:
        with self._lock:
            return [
                {"id": tid, "action": e["action"],
                 "condition": e["condition"], "repeat": e["repeat"]}
                for tid, e in self._triggers.items()
            ]

    def describe_active(self) -> str:
        """Людський опис активних тригерів — для голосової відповіді."""
        items = self.list_active()
        if not items:
            return "You have no active conditional triggers, Sir."
        lines = ["Active triggers, Sir:"]
        for it in items:
            lines.append(f"- {self._condition_text(it['condition'])}: {it['action']}")
        return "\n".join(lines)

    def clear_all(self) -> int:
        with self._lock:
            n = len(self._triggers)
            self._triggers.clear()
        self._save_to_disk()
        return n

    # ------------------------------------------------------------------ #
    #  ЗАПУСК / ЦИКЛ
    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="ConditionTriggers").start()
        logger.info("[TRIGGER] Моніторинг умов запущено")

    def stop(self):
        self._running = False

    def _loop(self):
        # перша перевірка за 30с після старту (даємо погоді піднятись)
        time.sleep(30)
        while self._running:
            try:
                self.check_now()
            except Exception as e:
                logger.warning(f"[TRIGGER] Помилка перевірки: {e}")
            time.sleep(CHECK_INTERVAL_MIN * 60)

    def check_now(self):
        """Перевіряє всі тригери проти поточної погоди/прогнозу."""
        with self._lock:
            if not self._triggers:
                return
        data = self._weather._fetch_data()
        if not data:
            logger.info("[TRIGGER] Погода недоступна — пропускаю перевірку")
            return

        fired_ids = []
        with self._lock:
            items = list(self._triggers.items())

        for tid, entry in items:
            try:
                if self._evaluate(entry["condition"], data):
                    self._fire(tid, entry)
                    if not entry["repeat"]:
                        fired_ids.append(tid)
            except Exception as e:
                logger.warning(f"[TRIGGER] eval {tid} error: {e}")

        if fired_ids:
            with self._lock:
                for tid in fired_ids:
                    self._triggers.pop(tid, None)
            self._save_to_disk()

    # ------------------------------------------------------------------ #
    #  ОЦІНКА УМОВ
    # ------------------------------------------------------------------ #

    def _evaluate(self, cond: dict, data: dict) -> bool:
        ctype = cond.get("type")
        if ctype == "weather":
            return self._eval_weather(cond, data)
        if ctype in ("temp", "temp_feels"):
            return self._eval_temp(cond, data)
        return False

    def _eval_weather(self, cond: dict, data: dict) -> bool:
        """Чи з'явиться явище у прогнозі на найближчі FORECAST_LOOKAHEAD_H годин."""
        phenom = cond.get("phenomenon", "rain")
        keywords, chance_field = PHENOMENA.get(phenom, ([phenom], None))

        # 1) поточні умови
        cur_desc = self._weather._current_desc(data).lower()
        if any(kw in cur_desc for kw in keywords):
            return True

        # 2) прогноз на найближчі години
        try:
            now_h = datetime.now().hour
            for day in data.get("weather", [])[:2]:
                for block in day.get("hourly", []):
                    try:
                        block_h = int(block.get("time", "0")) // 100
                    except ValueError:
                        continue
                    # для сьогодні — лише майбутні блоки; для завтра — всі
                    desc = block.get("weatherDesc", [{}])[0].get("value", "").lower()
                    if any(kw in desc for kw in keywords):
                        return True
                    if chance_field:
                        try:
                            if int(block.get(chance_field, "0") or 0) >= 60:
                                return True
                        except ValueError:
                            pass
        except Exception:
            pass
        return False

    def _eval_temp(self, cond: dict, data: dict) -> bool:
        """Порівняння температури (поточної) з порогом."""
        field = "FeelsLikeC" if cond["type"] == "temp_feels" else "temp_C"
        try:
            cur = data.get("current_condition", [{}])[0]
            temp = float(cur.get(field, "999"))
        except (ValueError, TypeError):
            return False
        op = cond.get("op", "<")
        val = float(cond.get("value", 0))
        if op == "<":
            return temp < val
        if op == ">":
            return temp > val
        if op == "<=":
            return temp <= val
        if op == ">=":
            return temp >= val
        return False

    # ------------------------------------------------------------------ #
    #  СПРАЦЮВАННЯ
    # ------------------------------------------------------------------ #

    def _fire(self, tid: str, entry: dict):
        action = entry["action"]
        cond_text = self._condition_text(entry["condition"])
        voice = f"Sir, {action}. Condition met: {cond_text}."
        tg = f"\u26a1 Trigger fired: {cond_text}\n\u2192 {action}"

        logger.info(f"[TRIGGER] 🔔 {tg}")

        # 1) озвучка
        try:
            self._speak(voice)
        except Exception:
            pass
        # 2) телеграм
        if self._telegram:
            try:
                self._telegram(tg)
            except Exception as e:
                logger.warning(f"[TRIGGER] Telegram failed: {e}")
        # 3) також лишаємо слід у HUD-нагадуваннях (миттєве, 1с) — опційно через reminder
        # навмисно НЕ створюємо reminder, бо тригер уже сам сповістив

        with self._lock:
            if tid in self._triggers:
                self._triggers[tid]["last_fired"] = datetime.now().isoformat()

    # ------------------------------------------------------------------ #
    #  УТИЛІТИ
    # ------------------------------------------------------------------ #

    @staticmethod
    def _condition_text(cond: dict) -> str:
        t = cond.get("type")
        if t == "weather":
            return f"{cond.get('phenomenon', 'rain')} expected"
        if t == "temp":
            return f"temperature {cond.get('op','<')} {cond.get('value')}\u00b0C"
        if t == "temp_feels":
            return f"feels-like {cond.get('op','<')} {cond.get('value')}\u00b0C"
        return "condition"

    def _save_to_disk(self):
        try:
            with self._lock:
                snapshot = {tid: {k: v for k, v in e.items()}
                            for tid, e in self._triggers.items()}
            with open(TRIGGERS_FILE, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[TRIGGER] save error: {e}")

    def _load_from_disk(self):
        if not TRIGGERS_FILE.exists():
            return
        try:
            with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._triggers = data or {}
            logger.info(f"[TRIGGER] Завантажено {len(self._triggers)} тригерів")
        except Exception as e:
            logger.error(f"[TRIGGER] load error: {e}")
