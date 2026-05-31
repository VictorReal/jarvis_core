"""
constants.py — Samsung Health коди (sleep stages, exercise types, інші мапи)
"""

# Фази сну (коди Samsung Health)
SLEEP_STAGES = {
    40001: "AWAKE",
    40002: "LIGHT",
    40003: "DEEP",
    40004: "REM",
}

SLEEP_STAGE_COLORS = {
    "AWAKE":  "#e74c3c",  # червоний
    "LIGHT":  "#3498db",  # світло-синій
    "DEEP":   "#2c3e50",  # темно-синій
    "REM":    "#9b59b6",  # фіолетовий
}

# Найпопулярніші типи тренувань Samsung Health
EXERCISE_TYPES = {
    0:     "Other",
    1001:  "Walking",
    1002:  "Running",
    11007: "Cycling",
    13001: "Swimming",
    14001: "Hiking",
    15006: "Strength training",
    10007: "Indoor cycling",
    11002: "Mountain biking",
}

# Норми (за рекомендаціями WHO + Samsung)
GOAL_DAILY_STEPS    = 10000
GOAL_SLEEP_HOURS    = 7.5
GOAL_ACTIVE_MINUTES = 30  # помірної інтенсивності

# Діапазони пульсу
HR_RESTING_MAX = 60
HR_ACTIVE_MIN  = 120
