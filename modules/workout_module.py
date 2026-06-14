"""
workout_module.py — облік силових тренувань для JARVIS + дані для мʼязової мапи.

Принцип:
  • Користувач каже/пише вправу ("жим лежачи", "присідання", "тяга").
  • Словник EXERCISE_MAP розкладає вправу на мʼязові групи.
  • Лог зберігається в data/workouts.json.
  • Для мапи: для кожної групи рахуємо, КОЛИ востаннє її тренували →
    колір (≤24год зелений, ≤48 жовтий, ≤72 червоний, далі не замальовано).
  • Невідома вправа → fallback на LLM (визначає групи), результат кешується.

Дані локальні, без зовнішніх API. У стилі money/mood модулів.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

WORKOUTS_FILE = Path("data/workouts.json")

# ── Канонічні мʼязові групи (мають збігатися з id зон у SVG) ──────────────
# спереду
FRONT_GROUPS = ["chest", "abs", "obliques", "shoulders", "biceps", "forearms",
                "quads", "calves_front"]
# ззаду
BACK_GROUPS = ["traps", "lats", "rhomboids", "lower_back", "rear_delts", "triceps",
               "glutes", "hamstrings", "calves_back"]
ALL_GROUPS = FRONT_GROUPS + BACK_GROUPS

# Людські назви груп для відповіді (без технічних id з "_").
# calves_front + calves_back → одне "calves" (front/back — деталь мапи).
_DISPLAY_NAMES = {
    "calves_front": "calves", "calves_back": "calves",
    "lower_back": "lower back", "rear_delts": "rear delts",
    "rhomboids": "rhomboids",
}

def _humanize_groups(groups: list) -> str:
    """id груп → чистий список людських назв, без дублів, зі збереженням порядку."""
    seen = []
    for g in groups:
        name = _DISPLAY_NAMES.get(g, g)
        if name not in seen:
            seen.append(name)
    return ", ".join(seen)

# ── Словник вправ → мʼязові групи ─────────────────────────────────────────
# Ключі — у нижньому регістрі, і укр і англ варіанти. Значення — групи.
EXERCISE_MAP = {
    # ГРУДИ
    "bench press": ["chest", "triceps", "shoulders"],
    "жим лежачи": ["chest", "triceps", "shoulders"],
    "жим штанги лежачи": ["chest", "triceps", "shoulders"],
    "incline bench": ["chest", "shoulders", "triceps"],
    "жим під кутом": ["chest", "shoulders", "triceps"],
    "dumbbell press": ["chest", "triceps", "shoulders"],
    "жим гантелей": ["chest", "triceps", "shoulders"],
    "push ups": ["chest", "triceps", "shoulders"],
    "віджимання": ["chest", "triceps", "shoulders"],
    "отжимания": ["chest", "triceps", "shoulders"],
    "fly": ["chest"],
    "розведення": ["chest"],
    "dips": ["chest", "triceps"],
    "брусся": ["chest", "triceps"],
    "бруси": ["chest", "triceps"],

    # СПИНА
    "pull ups": ["lats", "biceps", "traps"],
    "підтягування": ["lats", "biceps", "traps"],
    "подтягивания": ["lats", "biceps", "traps"],
    "deadlift": ["lower_back", "hamstrings", "glutes", "traps", "lats"],
    "станова тяга": ["lower_back", "hamstrings", "glutes", "traps", "lats"],
    "станова": ["lower_back", "hamstrings", "glutes", "traps", "lats"],
    "становая": ["lower_back", "hamstrings", "glutes", "traps", "lats"],
    "деадліфт": ["lower_back", "hamstrings", "glutes", "traps", "lats"],
    "дедліфт": ["lower_back", "hamstrings", "glutes", "traps", "lats"],
    "row": ["lats", "biceps", "traps", "rear_delts", "rhomboids"],
    "тяга": ["lats", "biceps", "traps", "rear_delts", "rhomboids"],
    "тяга штанги": ["lats", "biceps", "traps", "rear_delts", "rhomboids"],
    "тяга в нахилі": ["lats", "biceps", "traps", "rear_delts", "rhomboids"],
    "lat pulldown": ["lats", "biceps"],
    "тяга верхнього блоку": ["lats", "biceps"],

    # ПЛЕЧІ
    "overhead press": ["shoulders", "triceps", "rear_delts"],
    "армійський жим": ["shoulders", "triceps", "rear_delts"],
    "жим стоячи": ["shoulders", "triceps", "rear_delts"],
    "shoulder press": ["shoulders", "triceps", "rear_delts"],
    "lateral raise": ["shoulders", "rear_delts"],
    "махи": ["shoulders", "rear_delts"],
    "махи гантелями": ["shoulders", "rear_delts"],
    "rear delt fly": ["rear_delts", "traps"],
    "розводка в нахилі": ["rear_delts", "traps"],
    "зворотна розводка": ["rear_delts", "traps"],
    "reverse fly": ["rear_delts", "traps"],
    "face pull": ["rear_delts", "traps"],
    "shrugs": ["traps"],
    "шраги": ["traps"],

    # РУКИ
    "bicep curl": ["biceps", "forearms"],
    "підйом на біцепс": ["biceps", "forearms"],
    "згинання на біцепс": ["biceps", "forearms"],
    "curl": ["biceps", "forearms"],
    "біцепс": ["biceps"],
    "hammer curl": ["biceps", "forearms"],
    "молот": ["biceps", "forearms"],
    "tricep extension": ["triceps"],
    "розгинання на трицепс": ["triceps"],
    "трицепс": ["triceps"],
    "french press": ["triceps"],
    "французький жим": ["triceps"],

    # НОГИ
    "squat": ["quads", "glutes", "hamstrings"],
    "присідання": ["quads", "glutes", "hamstrings"],
    "присідання зі штангою": ["quads", "glutes", "hamstrings"],
    "приседания": ["quads", "glutes", "hamstrings"],
    "leg press": ["quads", "glutes"],
    "жим ногами": ["quads", "glutes"],
    "lunges": ["quads", "glutes", "hamstrings"],
    "випади": ["quads", "glutes", "hamstrings"],
    "leg curl": ["hamstrings"],
    "згинання ніг": ["hamstrings"],
    "leg extension": ["quads"],
    "розгинання ніг": ["quads"],
    "calf raise": ["calves_front", "calves_back"],
    "підйом на носки": ["calves_front", "calves_back"],
    "ікри": ["calves_front", "calves_back"],
    "litky": ["calves_front", "calves_back"],
    "литки": ["calves_front", "calves_back"],

    # ПРЕС / КОР
    "crunches": ["abs", "obliques"],
    "скручування": ["abs", "obliques"],
    "press": ["abs", "obliques"],
    "прес": ["abs", "obliques"],
    "plank": ["abs", "obliques", "lower_back"],
    "планка": ["abs", "obliques", "lower_back"],
    "leg raise": ["abs", "obliques"],
    "підйом ніг": ["abs", "obliques"],
    "russian twist": ["obliques", "abs"],
    "російські скручування": ["obliques", "abs"],
    "side plank": ["obliques", "abs"],
    "бічна планка": ["obliques", "abs"],
    "косі": ["obliques"],
    "obliques": ["obliques"],

    # ПРЯМІ НАЗВИ ГРУП (якщо просто кажуть "тренував груди")
    "груди": ["chest"], "chest": ["chest"],
    "спина": ["lats", "traps", "lower_back", "rear_delts", "rhomboids"],
    "back": ["lats", "traps", "lower_back", "rear_delts", "rhomboids"],
    "lower back": ["lower_back"], "low back": ["lower_back"],
    "нижня спина": ["lower_back"], "низ спини": ["lower_back"],
    "поперек": ["lower_back"], "lower_back": ["lower_back"],
    "плечі": ["shoulders", "rear_delts"], "shoulders": ["shoulders", "rear_delts"],
    "ноги": ["quads", "hamstrings", "glutes", "calves_front", "calves_back"],
    "legs": ["quads", "hamstrings", "glutes", "calves_front", "calves_back"],
    # англійські однослівні назви груп/мʼязів (щоб 'add biceps' розпізнавалось)
    "biceps": ["biceps"], "bicep": ["biceps"],
    "triceps": ["triceps"], "tricep": ["triceps"],
    "abs": ["abs", "obliques"], "core": ["abs", "obliques"],
    "forearms": ["forearms"], "forearm": ["forearms"],
    "quads": ["quads"], "quadriceps": ["quads"],
    "hamstrings": ["hamstrings"], "hamstring": ["hamstrings"],
    "glutes": ["glutes"], "calves": ["calves_front", "calves_back"],
    "lats": ["lats"], "traps": ["traps"], "trapezius": ["traps"],
    "rhomboids": ["rhomboids"], "rhomboid": ["rhomboids"],
    "ромбоподібні": ["rhomboids"], "ромби": ["rhomboids"], "ромбовидні": ["rhomboids"],
    "obliques": ["obliques"],
    "hands": ["biceps", "triceps", "forearms"],
    "arms": ["biceps", "triceps", "forearms"],
    "руки": ["biceps", "triceps", "forearms"],
}


class WorkoutModule:
    def __init__(self, llm=None):
        self._llm = llm  # для fallback-розпізнавання невідомих вправ

    # ------------------------------------------------------------------ #
    #  Розбір вправи → групи
    # ------------------------------------------------------------------ #

    def resolve_strict(self, exercise_text: str) -> list:
        """СТРОГИЙ резолвер для детекції наміру: лише точні збіги ключів
        EXERCISE_MAP по ЦІЛИХ словах/фразах (без підрядкових збігів, щоб
        'tomorrow' не матчив 'row'). Використовується перехоплювачем для
        слабких тригерів (add/plus), де треба впевнено відрізнити тренування
        від інших команд (add event, add reminder)."""
        import re as _re
        t = exercise_text.lower().strip()
        if t in EXERCISE_MAP:
            return EXERCISE_MAP[t]
        hits = []
        matched_keys = []
        # довші ключі першими — щоб "lower back" зматчився раніше за "back"
        for key in sorted(EXERCISE_MAP, key=len, reverse=True):
            # пропускаємо ключ, якщо він підрядок уже зматченого довшого ключа
            if any(key in mk and key != mk for mk in matched_keys):
                continue
            if _re.search(r"(?<!\w)" + _re.escape(key) + r"(?!\w)", t):
                hits.extend(EXERCISE_MAP[key])
                matched_keys.append(key)
        return list(dict.fromkeys(hits))

    def _resolve_groups(self, exercise_text: str) -> list:
        """Вправа (текст) → список мʼязових груп. Спершу словник, потім LLM."""
        t = exercise_text.lower().strip()

        # точний збіг
        if t in EXERCISE_MAP:
            return EXERCISE_MAP[t]
        # частковий збіг (текст містить ключ).
        # Довші ключі першими, щоб "lower back" зматчився раніше за "back",
        # і коротший підрядок уже зматченого ключа не домішувався.
        hits = []
        matched_keys = []
        for key in sorted(EXERCISE_MAP, key=len, reverse=True):
            if any(key in mk and key != mk for mk in matched_keys):
                continue
            if key in t:
                hits.extend(EXERCISE_MAP[key])
                matched_keys.append(key)
        if hits:
            return list(dict.fromkeys(hits))

        # укр-відмінки: нормалізуємо слова (спину→спин, трицепса→трицепс) і
        # шукаємо ключ, корінь якого збігається з коренем слова
        norm_words = [self._ua_stem(w) for w in t.split()]
        for key, groups in EXERCISE_MAP.items():
            key_stem = self._ua_stem(key)
            if any(key_stem and key_stem == w for w in norm_words):
                hits.extend(groups)
        if hits:
            return list(dict.fromkeys(hits))

        # fallback на LLM
        if self._llm is not None:
            return self._resolve_via_llm(exercise_text)
        return []

    @staticmethod
    def _ua_stem(word: str) -> str:
        """Грубий стемінг укр-слова: відкидає типові відмінкові закінчення.
        Не лінгвістично точний — досить, щоб 'спину'→'спин', 'грудей'→'груд'."""
        word = word.strip().lower()
        if len(word) <= 4:
            return word
        for end in ("ами", "ями", "ого", "ему", "ів", "ам", "ям", "ах", "ях",
                    "ою", "ею", "ей", "ів", "и", "у", "ю", "а", "я", "е", "і", "о"):
            if word.endswith(end) and len(word) - len(end) >= 3:
                return word[:-len(end)]
        return word

    def _resolve_via_llm(self, exercise_text: str) -> list:
        """LLM визначає групи для невідомої вправи."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            groups_list = ", ".join(ALL_GROUPS)
            resp = self._llm.invoke([
                SystemMessage(content=(
                    "You map a gym exercise to muscle groups. "
                    f"Valid groups ONLY: {groups_list}. "
                    "Reply with a comma-separated list of the groups worked, nothing else."
                )),
                HumanMessage(content=exercise_text),
            ])
            raw = resp.content.strip().lower()
            found = [g for g in ALL_GROUPS if g in raw]
            return found
        except Exception as e:
            logger.warning(f"[WORKOUT] LLM resolve error: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Логування
    # ------------------------------------------------------------------ #

    def _load(self) -> list:
        try:
            if WORKOUTS_FILE.exists():
                return json.loads(WORKOUTS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[WORKOUT] load error: {e}")
        return []

    def _save(self, data: list):
        try:
            WORKOUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            WORKOUTS_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[WORKOUT] save error: {e}")

    def log_workout(self, exercise_text: str) -> str:
        """Логує тренування. exercise_text може містити кілька вправ через кому/і."""
        # розбиваємо на окремі вправи
        import re
        parts = re.split(r"[,;]| and | і | та ", exercise_text.lower())
        all_groups = []
        logged = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            groups = self._resolve_groups(part)
            if groups:
                all_groups.extend(groups)
                logged.append(part)

        all_groups = list(dict.fromkeys(all_groups))
        if not all_groups:
            return f"Sir, I couldn't identify the muscle groups for '{exercise_text}'."

        data = self._load()
        data.append({
            "time": datetime.now().isoformat(),
            "exercise": exercise_text.strip(),
            "groups": all_groups,
        })
        self._save(data)
        return f"Logged, Sir. Worked: {_humanize_groups(all_groups)}."

    # ------------------------------------------------------------------ #
    #  Дані для мапи: остання активність кожної групи → колір
    # ------------------------------------------------------------------ #

    def get_muscle_map(self) -> dict:
        """Для кожної групи: години з останнього тренування + колір-стан.
        Повертає {group: {"hours": float|None, "state": "fresh|mid|old|none"}}."""
        data = self._load()
        now = datetime.now()
        last_seen = {}  # group → найсвіжіший datetime

        for entry in data:
            try:
                t = datetime.fromisoformat(entry["time"])
            except Exception:
                continue
            for g in entry.get("groups", []):
                if g not in last_seen or t > last_seen[g]:
                    last_seen[g] = t

        result = {}
        for g in ALL_GROUPS:
            if g not in last_seen:
                result[g] = {"hours": None, "state": "none"}
                continue
            hours = (now - last_seen[g]).total_seconds() / 3600
            if hours <= 24:
                state = "fresh"     # зелений
            elif hours <= 48:
                state = "mid"       # жовтий
            elif hours <= 72:
                state = "old"       # червоний
            else:
                state = "none"      # не замальовано
            result[g] = {"hours": round(hours, 1), "state": state}
        return result

    def get_telegram_report(self) -> str:
        """Детальний текстовий звіт для Telegram (non-markdown).
        Групи за станами свіжості + коли востаннє тренувались."""
        m = self.get_muscle_map()
        worked = [(g, v) for g, v in m.items() if v["state"] != "none"]
        if not worked:
            return "🏋️ WORKOUT MAP\nNo workouts logged in the last 72h, Sir."

        # людські назви груп
        names = {
            "chest": "Chest", "abs": "Abs", "obliques": "Obliques",
            "shoulders": "Shoulders", "biceps": "Biceps", "forearms": "Forearms",
            "quads": "Quads", "calves_front": "Calves (front)", "traps": "Traps", "rhomboids": "Rhomboids",
            "lats": "Lats", "lower_back": "Lower back", "rear_delts": "Rear delts",
            "triceps": "Triceps", "glutes": "Glutes", "hamstrings": "Hamstrings",
            "calves_back": "Calves (back)",
        }

        def fmt(group, info):
            h = info.get("hours")
            label = names.get(group, group)
            if h is None:
                return f"  • {label}"
            if h < 1:
                ago = "just now"
            elif h < 24:
                ago = f"{int(h)}h ago"
            else:
                ago = f"{int(h // 24)}d {int(h % 24)}h ago"
            return f"  • {label} — {ago}"

        fresh = [(g, v) for g, v in worked if v["state"] == "fresh"]
        mid = [(g, v) for g, v in worked if v["state"] == "mid"]
        old = [(g, v) for g, v in worked if v["state"] == "old"]

        lines = ["🏋️ WORKOUT MAP — recent training"]
        lines.append(f"{len(worked)} muscle groups trained in the last 72h.")
        if fresh:
            lines.append("")
            lines.append("🟢 Fresh (≤24h):")
            lines.extend(fmt(g, v) for g, v in fresh)
        if mid:
            lines.append("")
            lines.append("🟡 Recovering (≤48h):")
            lines.extend(fmt(g, v) for g, v in mid)
        if old:
            lines.append("")
            lines.append("🔴 Fading (≤72h):")
            lines.extend(fmt(g, v) for g, v in old)

        # групи, що давно не тренувались (рекомендація)
        rested = [names.get(g, g) for g, v in m.items() if v["state"] == "none"]
        if rested:
            lines.append("")
            lines.append(f"💤 Rested / overdue: {', '.join(rested)}")

        return "\n".join(lines)

    def get_summary(self) -> str:
        """Короткий підсумок для голосу/Telegram."""
        m = self.get_muscle_map()
        worked = [g for g, v in m.items() if v["state"] != "none"]
        if not worked:
            return "No recent workouts logged, Sir."
        fresh = [g for g, v in m.items() if v["state"] == "fresh"]
        msg = f"Sir, {len(worked)} muscle groups trained recently."
        if fresh:
            msg += f" Today: {', '.join(fresh)}."
        return msg


_workout_instance = None

def get_workout(llm=None) -> "WorkoutModule":
    global _workout_instance
    if _workout_instance is None:
        _workout_instance = WorkoutModule(llm=llm)
    elif llm is not None:
        _workout_instance._llm = llm
    return _workout_instance