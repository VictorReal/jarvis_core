"""
parser.py — Універсальний завантажник Samsung Health CSV
Samsung Health має квіркову структуру: row 0 = метадані, row 1 = заголовки,
trailing коми → треба index_col=False, інакше колонки зсуваються.
Назви колонок міняються між версіями застосунку — тому шукаємо їх гнучко.
"""

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)


def load_csv(path: str | Path) -> pd.DataFrame:
    """
    Завантажує Samsung Health CSV у DataFrame з нормалізованими колонками.
    Прибирає префікс 'com.samsung.health.<type>.' з імен колонок.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Samsung Health файл не знайдено: {path}")

    df = pd.read_csv(path, skiprows=1, index_col=False, low_memory=False)
    df.columns = [_strip_prefix(c) for c in df.columns]
    return df


def _strip_prefix(col: str) -> str:
    """Прибирає 'com.samsung.health.<type>.' префікс з імені колонки."""
    if col.startswith("com.samsung.health."):
        parts = col.split(".")
        return parts[-1]  # com.samsung.health.exercise.duration -> duration
    return col


def _find_col(df: pd.DataFrame, *names: str) -> str | None:
    """
    Гнучкий пошук колонки. Спочатку точний збіг по будь-якому з names,
    потім частковий (endswith) — щоб ловити варіації між версіями Samsung Health.
    Повертає назву колонки або None.
    """
    cols = list(df.columns)
    # 1. Точний збіг
    for name in names:
        if name in cols:
            return name
    # 2. endswith (для випадків недообрізаного префіксу типу 'exercise.end_time')
    for name in names:
        for c in cols:
            if c.endswith("." + name) or c.endswith("_" + name):
                return c
    return None


def _series(df: pd.DataFrame, *names: str):
    """Повертає Series по гнучко знайденій колонці, або колонку з NaN якщо нема."""
    col = _find_col(df, *names)
    if col is None:
        return pd.Series([pd.NA] * len(df), index=df.index)
    return df[col]


# ---------------------------------------------------------------------------
# Спеціалізовані лоадери для кожного типу даних
# ---------------------------------------------------------------------------


def load_sleep(path: str | Path) -> pd.DataFrame:
    """
    Сесії сну -> DataFrame з колонками:
      start, end, duration_h, efficiency, sleep_score, date
    """
    df = load_csv(path)
    df["start"] = pd.to_datetime(_series(df, "start_time"), errors="coerce")
    df["end"]   = pd.to_datetime(_series(df, "end_time"),   errors="coerce")
    df["duration_h"] = (df["end"] - df["start"]).dt.total_seconds() / 3600
    if "efficiency" not in df.columns:
        df["efficiency"] = pd.to_numeric(_series(df, "efficiency", "sleep_efficiency"), errors="coerce")
    if "sleep_score" not in df.columns:
        df["sleep_score"] = pd.to_numeric(_series(df, "sleep_score", "score"), errors="coerce")
    df = df.dropna(subset=["start", "end"]).copy()
    df["date"] = df["start"].dt.date
    return df.sort_values("start").reset_index(drop=True)


def load_sleep_stages(path: str | Path) -> pd.DataFrame:
    """
    Етапи сну (REM/Deep/Light/Awake) -> DataFrame з:
      start, end, duration_min, stage, stage_name, sleep_id
    """
    from .constants import SLEEP_STAGES
    df = load_csv(path)
    df["start"] = pd.to_datetime(_series(df, "start_time"), errors="coerce")
    df["end"]   = pd.to_datetime(_series(df, "end_time"),   errors="coerce")
    df["duration_min"] = (df["end"] - df["start"]).dt.total_seconds() / 60
    df["stage"] = pd.to_numeric(_series(df, "stage"), errors="coerce")
    df["stage_name"] = df["stage"].map(SLEEP_STAGES).fillna("UNKNOWN")
    if "sleep_id" not in df.columns:
        df["sleep_id"] = _series(df, "sleep_id")
    return df.dropna(subset=["start"]).sort_values("start").reset_index(drop=True)


def load_steps_daily(path: str | Path) -> pd.DataFrame:
    """
    Денні кроки (pedometer_day_summary) -> DataFrame з:
      date, step_count, distance_km, calorie, active_minutes
    Агрегує множинні записи за день.
    """
    df = load_csv(path)
    df["timestamp"] = pd.to_datetime(_series(df, "day_time"), unit="ms", errors="coerce")
    df["step_count"] = pd.to_numeric(_series(df, "step_count"), errors="coerce")
    df["distance_km"] = pd.to_numeric(_series(df, "distance"), errors="coerce") / 1000.0
    df["calorie"] = pd.to_numeric(_series(df, "calorie"), errors="coerce")
    df["active_minutes"] = pd.to_numeric(_series(df, "active_time"), errors="coerce") / 60000.0
    df = df.dropna(subset=["timestamp"]).copy()
    df["date"] = df["timestamp"].dt.date

    # Samsung Health має кілька записів на день (різні пристрої: phone + watch + інші).
    # SUM подвоює/потроює значення. Беремо MAX — це консолідоване значення з найточнішого
    # джерела (на May 26 в тестових даних дає 4648 vs sum=13383).
    daily = df.groupby("date").agg(
        step_count=("step_count", "max"),
        distance_km=("distance_km", "max"),
        calorie=("calorie", "max"),
        active_minutes=("active_minutes", "max"),
    ).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)


def load_heart_rate(path: str | Path) -> pd.DataFrame:
    """
    Серцебиття -> DataFrame з:
      timestamp, hr, hr_min, hr_max
    """
    df = load_csv(path)
    df["timestamp"] = pd.to_datetime(_series(df, "start_time"), errors="coerce")
    df["hr"]     = pd.to_numeric(_series(df, "heart_rate"), errors="coerce")
    df["hr_min"] = pd.to_numeric(_series(df, "min"), errors="coerce")
    df["hr_max"] = pd.to_numeric(_series(df, "max"), errors="coerce")
    df = df.dropna(subset=["timestamp", "hr"]).copy()
    df = df[df["hr"] > 0]  # 0 = невалідний замір
    return df[["timestamp", "hr", "hr_min", "hr_max"]].sort_values("timestamp").reset_index(drop=True)


def load_exercise(path: str | Path) -> pd.DataFrame:
    """
    Тренування -> DataFrame з:
      start, end, date, duration_min, type_code, type_name, distance_km,
      calorie, mean_hr, max_hr
    Стійкий до різних версій Samsung Health (гнучкий пошук колонок).
    """
    from .constants import EXERCISE_TYPES
    df = load_csv(path)
    df["start"] = pd.to_datetime(_series(df, "start_time"), errors="coerce")
    df["end"]   = pd.to_datetime(_series(df, "end_time"),   errors="coerce")
    df["duration_min"] = pd.to_numeric(_series(df, "duration"), errors="coerce") / 60000
    df["type_code"] = pd.to_numeric(_series(df, "exercise_type"), errors="coerce")
    df["type_name"] = df["type_code"].map(EXERCISE_TYPES).fillna("Unknown")
    df["distance_km"] = pd.to_numeric(_series(df, "distance"), errors="coerce") / 1000.0
    df["calorie"]  = pd.to_numeric(_series(df, "calorie"), errors="coerce")
    df["mean_hr"]  = pd.to_numeric(_series(df, "mean_heart_rate"), errors="coerce")
    df["max_hr"]   = pd.to_numeric(_series(df, "max_heart_rate"),  errors="coerce")
    df = df.dropna(subset=["start"]).copy()
    df["date"] = df["start"].dt.date
    return df[["start", "end", "date", "duration_min", "type_code",
               "type_name", "distance_km", "calorie", "mean_hr", "max_hr"]] \
        .sort_values("start").reset_index(drop=True)


def load_activity_daily(path: str | Path) -> pd.DataFrame:
    """
    Денна активність -> DataFrame з:
      date, step_count, distance_km, calorie, exercise_min, active_min,
      floor_count, score
    """
    df = load_csv(path)
    df["timestamp"] = pd.to_datetime(_series(df, "day_time"), errors="coerce")
    df["step_count"] = pd.to_numeric(_series(df, "step_count"), errors="coerce")
    df["distance_km"]  = pd.to_numeric(_series(df, "distance"), errors="coerce") / 1000.0
    df["calorie"]      = pd.to_numeric(_series(df, "calorie"), errors="coerce")
    df["exercise_min"] = pd.to_numeric(_series(df, "exercise_time"), errors="coerce") / 60000
    df["active_min"]   = pd.to_numeric(_series(df, "active_time"), errors="coerce") / 60000
    df["floor_count"]  = pd.to_numeric(_series(df, "floor_count"), errors="coerce")
    df["score"]        = pd.to_numeric(_series(df, "score"), errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df["date"] = pd.to_datetime(df["timestamp"].dt.date)
    return df[["date", "step_count", "distance_km", "calorie",
               "exercise_min", "active_min", "floor_count", "score"]] \
        .sort_values("date").reset_index(drop=True)