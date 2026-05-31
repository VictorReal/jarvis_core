"""
heart_rate_analysis.py — аналітика пульсу з Samsung Health.
"""

import pandas as pd
from .constants import HR_RESTING_MAX, HR_ACTIVE_MIN


def filter_period(df: pd.DataFrame, period: str = "week", date_col: str = "timestamp") -> pd.DataFrame:
    if period == "all":
        return df
    now = pd.Timestamp.now()
    deltas = {"today": 1, "week": 7, "month": 30, "year": 365}
    cutoff = now - pd.Timedelta(days=deltas.get(period, 7))
    return df[df[date_col] >= cutoff].copy()


def hr_summary(hr_df: pd.DataFrame, period: str = "week") -> dict:
    """Підсумок по пульсу за період."""
    df = filter_period(hr_df, period)
    if df.empty:
        return {"period": period, "samples": 0, "message": "No data."}

    resting = df[df["hr"] < HR_RESTING_MAX]["hr"]
    active  = df[df["hr"] > HR_ACTIVE_MIN]["hr"]

    return {
        "period":         period,
        "samples":        len(df),
        "avg_hr":         round(df["hr"].mean(), 1),
        "median_hr":      round(df["hr"].median(), 1),
        "min_hr":         int(df["hr"].min()),
        "max_hr":         int(df["hr"].max()),
        "resting_avg":    round(resting.mean(), 1) if not resting.empty else None,
        "resting_count":  len(resting),
        "active_count":   len(active),
    }


def daily_resting_hr(hr_df: pd.DataFrame, period: str = "month") -> pd.DataFrame:
    """
    Денний resting HR (мін значення за день — наближення до true resting HR).
    Resting HR — важливий індикатор фітнес-форми. Знижується = форма зростає.
    """
    df = filter_period(hr_df, period)
    df["date"] = df["timestamp"].dt.date
    daily = df.groupby("date").agg(
        resting_hr=("hr", "min"),
        mean_hr=("hr", "mean"),
        max_hr=("hr", "max"),
        samples=("hr", "count"),
    ).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)
