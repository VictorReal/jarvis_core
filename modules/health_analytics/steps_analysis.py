"""
steps_analysis.py — аналітика кроків з Samsung Health.
"""

import pandas as pd
import numpy as np
from .constants import GOAL_DAILY_STEPS


def filter_period(df: pd.DataFrame, period: str = "week", date_col: str = "date") -> pd.DataFrame:
    """Фільтр за період: today / week / month / year / all."""
    if period == "all":
        return df
    now = pd.Timestamp.now()
    deltas = {"today": 1, "week": 7, "month": 30, "year": 365}
    cutoff = now - pd.Timedelta(days=deltas.get(period, 7))
    return df[df[date_col] >= cutoff].copy()


def steps_summary(steps_df: pd.DataFrame, period: str = "week") -> dict:
    """Підсумок по кроках за період."""
    df = filter_period(steps_df, period)
    if df.empty:
        return {"period": period, "days": 0, "message": "No data for this period."}

    return {
        "period":         period,
        "days":           len(df),
        "total_steps":    int(df["step_count"].sum()),
        "avg_steps":      int(df["step_count"].mean()),
        "median_steps":   int(df["step_count"].median()),
        "max_steps":      int(df["step_count"].max()),
        "max_date":       str(df.loc[df["step_count"].idxmax(), "date"].date()),
        "total_km":       round(df["distance_km"].sum(), 2),
        "total_calories": int(df["calorie"].sum()),
        "active_minutes": int(df["active_minutes"].sum()),
        "goal_met_days":  int((df["step_count"] >= GOAL_DAILY_STEPS).sum()),
        "goal_met_pct":   round((df["step_count"] >= GOAL_DAILY_STEPS).mean() * 100, 1),
    }


def weekday_pattern(steps_df: pd.DataFrame) -> pd.DataFrame:
    """Середні кроки по днях тижня."""
    df = steps_df.copy()
    df["weekday"] = df["date"].dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    grouped = df.groupby("weekday")["step_count"].mean().reindex(order)
    return grouped.reset_index().rename(columns={"step_count": "avg_steps"})


def monthly_trend(steps_df: pd.DataFrame) -> pd.DataFrame:
    """Середні кроки по місяцях за весь період (для довгострокового тренду)."""
    df = steps_df.copy()
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df.groupby("month").agg(
        avg_steps=("step_count", "mean"),
        total_km=("distance_km", "sum"),
        days=("step_count", "count"),
    ).reset_index()


def daily_series(steps_df: pd.DataFrame, period: str = "month") -> pd.DataFrame:
    """Часова серія для графіків + 7-day rolling average."""
    df = filter_period(steps_df, period).copy()
    df = df.sort_values("date").reset_index(drop=True)
    df["rolling_7d"] = df["step_count"].rolling(window=7, min_periods=1).mean()
    return df[["date", "step_count", "rolling_7d", "distance_km", "calorie"]]


def consistency_score(steps_df: pd.DataFrame, period: str = "month") -> float:
    """
    Скор постійності (0-100): як часто за період досягав цілі в 10K кроків.
    Базовий, для добавлення в HUD/zвіт.
    """
    df = filter_period(steps_df, period)
    if df.empty:
        return 0.0
    return round((df["step_count"] >= GOAL_DAILY_STEPS).mean() * 100, 1)
