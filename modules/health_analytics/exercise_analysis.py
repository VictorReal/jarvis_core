"""
exercise_analysis.py — аналітика тренувань з Samsung Health.
"""

import pandas as pd


def filter_period(df: pd.DataFrame, period: str = "week", date_col: str = "start") -> pd.DataFrame:
    if period == "all":
        return df
    now = pd.Timestamp.now()
    deltas = {"today": 1, "week": 7, "month": 30, "year": 365}
    cutoff = now - pd.Timedelta(days=deltas.get(period, 7))
    return df[df[date_col] >= cutoff].copy()


def exercise_summary(ex_df: pd.DataFrame, period: str = "week") -> dict:
    """Підсумок по тренуваннях за період."""
    df = filter_period(ex_df, period)
    if df.empty:
        return {"period": period, "sessions": 0, "message": "No workouts in this period."}

    return {
        "period":          period,
        "sessions":        len(df),
        "total_minutes":   int(df["duration_min"].sum()),
        "avg_duration":    round(df["duration_min"].mean(), 1),
        "total_km":        round(df["distance_km"].sum(), 2),
        "total_calories":  int(df["calorie"].sum()),
        "top_type":        df["type_name"].mode().iloc[0] if not df["type_name"].mode().empty else "—",
        "type_breakdown":  df["type_name"].value_counts().to_dict(),
        "avg_mean_hr":     round(df["mean_hr"].mean(), 1) if df["mean_hr"].notna().any() else None,
        "avg_max_hr":      round(df["max_hr"].mean(), 1) if df["max_hr"].notna().any() else None,
    }


def weekly_volume(ex_df: pd.DataFrame, period: str = "year") -> pd.DataFrame:
    """Хвилин тренувань на тиждень — для відстеження обсягу."""
    df = filter_period(ex_df, period).copy()
    df["week"] = df["start"].dt.to_period("W").dt.start_time
    return df.groupby("week").agg(
        total_min=("duration_min", "sum"),
        sessions=("duration_min", "count"),
        total_km=("distance_km", "sum"),
    ).reset_index()
