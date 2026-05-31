"""
Аналітика настрою.
Агрегації, тренди, streak, розподіл тегів, порівняння ранок/вечір.
Усі функції приймають уже відфільтрований DataFrame з parser.load_df()/filter_period().
"""
from datetime import date, timedelta

import pandas as pd

from .constants import NEGATIVE_TAGS, SCORE_MAX


def summary_stats(df: pd.DataFrame) -> dict:
    """Базові показники для HUD-міні-панелі і модалу."""
    if df.empty:
        return {
            "count": 0, "avg": None, "latest": None, "latest_tags": [],
            "min": None, "max": None, "trend": "flat",
            "morning_avg": None, "evening_avg": None,
            "positive_pct": None, "days_logged": 0, "best_day": None,
        }

    scores = df["score"]
    latest_row = df.iloc[-1]

    # AM/PM рахуємо за годиною timestamp (надійно, не залежить від time_of_day,
    # який часто 'adhoc' для логувань протягом дня)
    hours = df["timestamp"].dt.hour
    morning = df[hours < 12]["score"]
    evening = df[hours >= 12]["score"]

    return {
        "count":       int(len(df)),
        "avg":         round(float(scores.mean()), 1),
        "latest":      int(latest_row["score"]),
        "latest_tags": latest_row.get("tag_list", []),
        "min":         int(scores.min()),
        "max":         int(scores.max()),
        "trend":       _trend(df),
        "morning_avg": round(float(morning.mean()), 1) if not morning.empty else None,
        "evening_avg": round(float(evening.mean()), 1) if not evening.empty else None,
        "positive_pct": _positive_pct(df),
        "days_logged": int(df["timestamp"].dt.normalize().nunique()),
        "best_day":    _best_weekday(df),
    }


def _trend(df: pd.DataFrame) -> str:
    """Напрямок настрою: up/down/flat. Порівнює середнє першої і другої половини."""
    if len(df) < 4:
        return "flat"
    half = len(df) // 2
    first = df.iloc[:half]["score"].mean()
    second = df.iloc[half:]["score"].mean()
    diff = second - first
    if diff >= 0.5:
        return "up"
    if diff <= -0.5:
        return "down"
    return "flat"


def _positive_pct(df: pd.DataFrame) -> int:
    """% записів, де настрій радше позитивний (score >= 6 і без негативних тегів-домінант)."""
    if df.empty:
        return 0
    positive = 0
    for _, row in df.iterrows():
        neg = sum(1 for t in row.get("tag_list", []) if t in NEGATIVE_TAGS)
        pos = len(row.get("tag_list", [])) - neg
        if row["score"] >= 6 and neg <= pos:
            positive += 1
    return round(100 * positive / len(df))


def logging_streak(df: pd.DataFrame) -> int:
    """Скільки днів поспіль (рахуючи від сьогодні/останнього дня) є хоча б один запис."""
    if df.empty:
        return 0
    days = set(pd.to_datetime(df["date"]).dt.date)
    streak = 0
    cursor = date.today()
    # Якщо сьогодні запису ще нема — стартуємо від останнього дня з записом
    if cursor not in days:
        cursor = max(days)
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def daily_series(df: pd.DataFrame) -> pd.DataFrame:
    """Середній настрій по днях — для лінійного тренду."""
    if df.empty:
        return pd.DataFrame(columns=["date", "score"])
    d = df.copy()
    # надійна денна дата з timestamp (date-колонка могла бути object/None)
    d["_day"] = d["timestamp"].dt.normalize()
    g = (d.groupby("_day")["score"].mean().round(2)
           .reset_index().sort_values("_day").reset_index(drop=True))
    g.columns = ["date", "score"]
    return g


def tag_distribution(df: pd.DataFrame) -> pd.Series:
    """Частота кожного тега (відсортовано). Для bar-чарту тегів."""
    if df.empty:
        return pd.Series(dtype=int)
    flat = [t for tags in df["tag_list"] for t in tags]
    if not flat:
        return pd.Series(dtype=int)
    return pd.Series(flat).value_counts()


def hour_distribution(df: pd.DataFrame) -> pd.Series:
    """Середній настрій за годиною доби — коли тобі найкраще/найгірше."""
    if df.empty:
        return pd.Series(dtype=float)
    return df.groupby(df["timestamp"].dt.hour)["score"].mean().round(2)


def morning_vs_evening(df: pd.DataFrame) -> dict:
    """Порівняння ранок/вечір за годиною запису (до 12:00 = AM, після = PM)."""
    if df.empty:
        return {"morning": None, "evening": None, "morning_n": 0, "evening_n": 0}
    hours = df["timestamp"].dt.hour
    m = df[hours < 12]["score"]
    e = df[hours >= 12]["score"]
    return {
        "morning": round(float(m.mean()), 1) if not m.empty else None,
        "evening": round(float(e.mean()), 1) if not e.empty else None,
        "morning_n": int(len(m)),
        "evening_n": int(len(e)),
    }


def correlation_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Денний ряд для cross-correlation з health/money (пункт 5 роадмапу).
    Повертає DataFrame index=date з колонкою mood (середній за день).
    Health/Money модулі зможуть зробити join по індексу-даті.
    """
    if df.empty:
        return pd.DataFrame(columns=["mood"])
    g = daily_series(df).set_index("date")
    g.columns = ["mood"]
    g.index = pd.to_datetime(g.index)
    return g


WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def weekday_distribution(df: pd.DataFrame) -> pd.Series:
    """Середній настрій по днях тижня (Mon..Sun). Для графіка 'Mood by Day'."""
    if df.empty:
        return pd.Series(dtype=float)
    d = df.copy()
    d["weekday"] = d["timestamp"].dt.day_name()
    grouped = d.groupby("weekday")["score"].mean().reindex(WEEKDAY_ORDER)
    return grouped.round(2)


def _best_weekday(df: pd.DataFrame):
    """День тижня з найвищим середнім настроєм (коротка назва) або None."""
    wd = weekday_distribution(df)
    wd = wd.dropna()
    if wd.empty:
        return None
    return wd.idxmax()[:3]  # 'Mon', 'Sat'...
