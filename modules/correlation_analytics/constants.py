"""
Константи модуля крос-кореляції.
Зведення sleep × steps × mood × spending у єдину денну таблицю + аналіз зв'язків.
"""

# Метрики, які зводимо в єдину денну таблицю. Ключ → людська назва для графіків.
METRICS = {
    "steps":      "Steps",
    "sleep_h":    "Sleep (h)",
    "resting_hr": "Resting HR",
    "mood":       "Mood",
    "spending":   "Spending",
    "workout":    "Workout",
    "alcohol":    "Alcohol",
}

# Кольори (узгоджено з HUD / health visualizer)
COLORS = {
    "bg":     "#0a0e1a",
    "panel":  "#0f1626",
    "grid":   "#1c2942",
    "text":   "#a8c5e8",
    "title":  "#e8f0ff",
    "cyan":   "#00d4ff",
    "blue":   "#3a6df0",
    "purple": "#9b59b6",
    "green":  "#00ff88",
    "orange": "#ff9500",
    "red":    "#ff3b30",
    "yellow": "#ffd400",
    "pink":   "#ff5dbb",
}

# Поріг |r|, вище якого зв'язок вважаємо вартим уваги у висновках
CORR_NOTABLE = 0.25
CORR_STRONG  = 0.45

# Мінімум спільних днів, щоб кореляція мала сенс
MIN_OVERLAP_DAYS = 10

# Кеш
CACHE_DIR = "data/correlation/cache"

# Людські описи пар для висновків (напрям + інтерпретація).
# Формат: (metric_a, metric_b): (позитивна_інтерпретація, негативна_інтерпретація)
PAIR_INSIGHTS = {
    ("sleep_h", "steps"): (
        "More sleep tends to go with more activity the same day.",
        "More sleep tends to go with less activity — possibly recovery days.",
    ),
    ("sleep_h", "mood"): (
        "Better sleep is linked to better mood.",
        "More sleep coincides with lower mood — worth watching.",
    ),
    ("steps", "mood"): (
        "More activity is linked to better mood.",
        "More activity coincides with lower mood.",
    ),
    ("sleep_h", "resting_hr"): (
        "More sleep goes with higher resting HR.",
        "More sleep goes with lower resting HR — a good recovery sign.",
    ),
    ("steps", "spending"): (
        "Busier, more active days come with higher spending.",
        "More active days come with lower spending.",
    ),
    ("mood", "spending"): (
        "Higher mood days come with higher spending.",
        "Lower mood days come with higher spending — possible stress spending.",
    ),
    ("resting_hr", "mood"): (
        "Higher resting HR goes with higher mood.",
        "Higher resting HR (stress/fatigue) goes with lower mood.",
    ),
    # --- Тренування ---
    ("workout", "sleep_h"): (
        "On workout days you tend to sleep more — training aids sleep.",
        "On workout days you tend to sleep less — watch recovery.",
    ),
    ("workout", "mood"): (
        "Workout days come with better mood — training lifts you.",
        "Workout days come with lower mood — possibly over-training.",
    ),
    ("workout", "resting_hr"): (
        "Workout days show higher resting HR (training load).",
        "Workout days show lower resting HR — good cardiovascular sign.",
    ),
    ("workout", "steps"): (
        "Workout days are also higher-step days, as expected.",
        "Workout days have fewer steps — gym over walking.",
    ),
    ("workout", "alcohol"): (
        "You drink more on workout days — worth a glance.",
        "You drink less on workout days — training displaces drinking.",
    ),
    # --- Алкоголь ---
    ("alcohol", "sleep_h"): (
        "More drinking goes with more time in bed — but not better sleep.",
        "More drinking goes with less sleep — alcohol shortens your night.",
    ),
    ("alcohol", "mood"): (
        "Higher drinking days go with higher mood (short-term).",
        "Higher drinking days go with lower mood — possible after-effect.",
    ),
    ("alcohol", "resting_hr"): (
        "More drinking goes with higher resting HR — alcohol stresses the heart.",
        "More drinking goes with lower resting HR.",
    ),
}
