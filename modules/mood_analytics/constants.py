"""
Константи модуля настрою.
Тут зосереджено все що може мінятись: шкала, теги, шляхи, кольори, час запитів.
"""
import os

# ── Шляхи ────────────────────────────────────────────────────────────
# data/mood/moods.csv — окремий рядок на кожен запис (зручно для time-series + cross-correlation)
DATA_DIR  = os.path.join("data", "mood")
CSV_PATH  = os.path.join(DATA_DIR, "moods.csv")
CACHE_DIR = os.path.join(DATA_DIR, "cache")  # кеш для PNG-чартів

# Колонки CSV (порядок фіксований — parser на нього спирається)
CSV_COLUMNS = ["timestamp", "date", "time_of_day", "score", "tags", "note", "source"]

# ── Шкала ────────────────────────────────────────────────────────────
SCORE_MIN = 1
SCORE_MAX = 10

# ── Теги настрою ─────────────────────────────────────────────────────
# Канонічний список. Telegram inline-кнопки і валідація голосового вводу беруть звідси.
MOOD_TAGS = [
    "energetic", "happy", "calm", "focused", "productive",
    "tired", "anxious", "stressed", "sad", "angry",
    "bored", "lonely", "sick", "motivated", "grateful",
]

# Які теги вважаються "негативними" — для аналізу настрою (% позитиву)
NEGATIVE_TAGS = {"tired", "anxious", "stressed", "sad", "angry", "bored", "lonely", "sick"}

# ── Час доби запису ──────────────────────────────────────────────────
TIME_OF_DAY = ("morning", "evening", "adhoc")

# Межі для авто-визначення часу доби (коли source=voice/hud без явного маркера)
MORNING_HOURS = range(4, 12)   # 04:00–11:59 → morning
EVENING_HOURS = range(18, 24)  # 18:00–23:59 → evening
# решта → adhoc

# ── Час авто-запитів (для майбутнього scheduler; поки не використовується) ──
MORNING_PROMPT_HOUR = 9
EVENING_PROMPT_HOUR  = 21

# ── Кольори для чартів (узгоджено з HUD --hud-accent) ────────────────
COLOR_ACCENT   = "#00d4ff"
COLOR_ACCENT2  = "#00ff88"
COLOR_WARN     = "#ff6600"
COLOR_BAD      = "#ff2200"
COLOR_BG       = "#0a0a0a"
COLOR_GRID     = "#1a3a4a"
COLOR_TEXT     = "#7fd4e8"

# Градієнт оцінки → колір (для барів/точок)
def score_color(score: float) -> str:
    """Повертає колір залежно від оцінки 1-10."""
    if score >= 7:
        return COLOR_ACCENT2
    if score >= 4:
        return COLOR_ACCENT
    return COLOR_BAD


def normalize_time_of_day(value: str, hour: int = None) -> str:
    """Нормалізує time_of_day. Якщо value невалідний — визначає за годиною."""
    if value in TIME_OF_DAY:
        return value
    if hour is not None:
        if hour in MORNING_HOURS:
            return "morning"
        if hour in EVENING_HOURS:
            return "evening"
    return "adhoc"
