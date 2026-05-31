"""
sleep_analysis.py — аналітика сну з даних Samsung Health.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def filter_period(df: pd.DataFrame, period: str = "week", date_col: str = "start") -> pd.DataFrame:
    """Фільтрує DataFrame за період: today / week / month / year / all."""
    if period == "all":
        return df
    now = pd.Timestamp.now()
    deltas = {"today": 1, "week": 7, "month": 30, "year": 365}
    cutoff = now - pd.Timedelta(days=deltas.get(period, 7))
    return df[df[date_col] >= cutoff].copy()


def main_session_per_night(sleep_df: pd.DataFrame) -> pd.DataFrame:
    """
    Залишає тільки найдовшу сесію за календарну ніч.
    Samsung Health часто записує короткі денні сни — для метрик основного сну
    нам потрібна найдовша сесія, прив'язана до календарної дати засинання.
    """
    df = sleep_df.copy()
    # "Ніч" прив'язуємо до дати засинання, але якщо засинаєш після 00:00 —
    # це вважається ніччю попереднього дня
    df["night_date"] = df["start"].apply(
        lambda d: (d - pd.Timedelta(hours=18)).date()
    )
    return df.loc[df.groupby("night_date")["duration_h"].idxmax()].reset_index(drop=True)


def sleep_summary(sleep_df: pd.DataFrame, period: str = "week") -> dict:
    """
    Підсумок по сну за період.
    Повертає dict зі статистикою.
    """
    df = filter_period(sleep_df, period)
    if df.empty:
        return {"period": period, "nights": 0, "message": "No sleep data for this period."}

    main = main_session_per_night(df)
    return {
        "period":         period,
        "nights":         len(main),
        "avg_duration_h": round(main["duration_h"].mean(), 2),
        "avg_efficiency": round(main["efficiency"].mean(), 1),
        "avg_sleep_score": (round(main["sleep_score"].mean(), 1)
                            if main["sleep_score"].notna().any() else None),
        "shortest_h":     round(main["duration_h"].min(), 2),
        "longest_h":      round(main["duration_h"].max(), 2),
        "total_sessions": len(df),  # включаючи денні сни
    }


def sleep_stages_breakdown(stages_df: pd.DataFrame, sleep_id: str | None = None) -> dict:
    """
    Розподіл фаз сну (% REM, % Deep, % Light, % Awake).
    Якщо sleep_id вказано — рахує для конкретної сесії, інакше для всіх.
    """
    df = stages_df.copy()
    if sleep_id:
        df = df[df["sleep_id"] == sleep_id]
    if df.empty:
        return {}
    total = df["duration_min"].sum()
    if total == 0:
        return {}
    breakdown = df.groupby("stage_name")["duration_min"].sum()
    return {stage: round(mins / total * 100, 1) for stage, mins in breakdown.items()}


def weekday_pattern(sleep_df: pd.DataFrame) -> pd.DataFrame:
    """Середня тривалість сну по днях тижня (Mon-Sun)."""
    main = main_session_per_night(sleep_df)
    main["weekday"] = pd.to_datetime(main["night_date"]).dt.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    grouped = main.groupby("weekday")["duration_h"].mean().reindex(order)
    return grouped.reset_index().rename(columns={"duration_h": "avg_hours"})


def daily_series(sleep_df: pd.DataFrame, period: str = "month") -> pd.DataFrame:
    """
    Часова серія тривалості сну по днях (для графіків).
    Повертає DataFrame з колонками: night_date, duration_h.
    """
    df = filter_period(sleep_df, period)
    main = main_session_per_night(df)
    return main[["night_date", "duration_h", "sleep_score", "efficiency"]] \
        .sort_values("night_date") \
        .reset_index(drop=True)
