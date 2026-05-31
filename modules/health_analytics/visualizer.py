"""
visualizer.py — графіки в JARVIS-стилі (dark theme, cyan accents).
Виводить PNG у файл або BytesIO для Telegram/HUD.
"""

import io
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from .constants import SLEEP_STAGE_COLORS, GOAL_DAILY_STEPS


# Кольорова палітра в стилі HUD
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
}


def _setup_style():
    """Глобальні стилі для всіх графіків."""
    plt.rcParams.update({
        "figure.facecolor":  COLORS["bg"],
        "axes.facecolor":    COLORS["panel"],
        "axes.edgecolor":    COLORS["grid"],
        "axes.labelcolor":   COLORS["text"],
        "axes.titlecolor":   COLORS["title"],
        "xtick.color":       COLORS["text"],
        "ytick.color":       COLORS["text"],
        "grid.color":        COLORS["grid"],
        "grid.linestyle":    "--",
        "grid.alpha":        0.4,
        "axes.grid":         True,
        "font.size":         10,
        "axes.titlesize":    12,
        "axes.titleweight":  "bold",
        "axes.spines.top":   False,
        "axes.spines.right": False,
    })


def _save(fig, path: str | Path | None) -> bytes:
    """Зберігає в файл (якщо path) і завжди повертає bytes для Telegram."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor=COLORS["bg"])
    plt.close(fig)
    buf.seek(0)
    data = buf.getvalue()
    if path:
        Path(path).write_bytes(data)
    return data


# ---------------------------------------------------------------------------
# STEPS
# ---------------------------------------------------------------------------

def plot_steps_daily(steps_series: pd.DataFrame,
                     title: str = "Daily Steps",
                     path: str | Path | None = None) -> bytes:
    """
    Графік щоденних кроків + 7-day rolling avg + ціль 10K.
    steps_series має мати колонки: date, step_count, rolling_7d.
    """
    _setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5))

    ax.bar(steps_series["date"], steps_series["step_count"],
           color=COLORS["blue"], alpha=0.6, width=0.9, label="Daily")
    ax.plot(steps_series["date"], steps_series["rolling_7d"],
            color=COLORS["cyan"], linewidth=2.2, label="7-day avg")
    ax.axhline(GOAL_DAILY_STEPS, color=COLORS["orange"],
               linestyle="--", linewidth=1, alpha=0.7, label=f"Goal {GOAL_DAILY_STEPS}")

    ax.set_title(title)
    ax.set_ylabel("Steps")
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"], loc="upper left")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.autofmt_xdate()
    return _save(fig, path)


def plot_steps_weekday(weekday_df: pd.DataFrame,
                       title: str = "Steps by Weekday",
                       path: str | Path | None = None) -> bytes:
    """Бар-чарт по днях тижня."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(weekday_df["weekday"], weekday_df["avg_steps"], color=COLORS["cyan"])
    # Підсвічуємо weekends
    for i, day in enumerate(weekday_df["weekday"]):
        if day in ["Saturday", "Sunday"]:
            bars[i].set_color(COLORS["orange"])
    ax.axhline(GOAL_DAILY_STEPS, color=COLORS["text"],
               linestyle="--", linewidth=1, alpha=0.5)
    ax.set_title(title)
    ax.set_ylabel("Avg Steps")
    return _save(fig, path)


def plot_steps_monthly_trend(monthly_df: pd.DataFrame,
                             title: str = "Monthly Steps Trend",
                             path: str | Path | None = None) -> bytes:
    """Довгостроковий тренд по місяцях."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(monthly_df["month"], monthly_df["avg_steps"],
            color=COLORS["cyan"], linewidth=2, marker="o", markersize=4)
    ax.fill_between(monthly_df["month"], monthly_df["avg_steps"],
                    color=COLORS["cyan"], alpha=0.15)
    ax.axhline(GOAL_DAILY_STEPS, color=COLORS["orange"],
               linestyle="--", linewidth=1, alpha=0.6, label=f"Goal {GOAL_DAILY_STEPS}")
    ax.set_title(title)
    ax.set_ylabel("Avg Daily Steps")
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"])
    fig.autofmt_xdate()
    return _save(fig, path)


# ---------------------------------------------------------------------------
# SLEEP
# ---------------------------------------------------------------------------

def plot_sleep_duration(sleep_series: pd.DataFrame,
                        title: str = "Sleep Duration",
                        path: str | Path | None = None) -> bytes:
    """Тривалість сну по ночах."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(10, 4.5))

    colors = [COLORS["red"] if h < 6 else COLORS["orange"] if h < 7
              else COLORS["green"] for h in sleep_series["duration_h"]]
    ax.bar(sleep_series["night_date"], sleep_series["duration_h"],
           color=colors, alpha=0.85, width=0.9)
    ax.axhline(7.5, color=COLORS["cyan"], linestyle="--",
               linewidth=1, alpha=0.7, label="Goal 7.5h")
    ax.set_title(title)
    ax.set_ylabel("Hours")
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"])
    fig.autofmt_xdate()
    return _save(fig, path)


def plot_sleep_stages_pie(breakdown: dict,
                          title: str = "Sleep Stages",
                          path: str | Path | None = None) -> bytes:
    """Donut-чарт фаз сну."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(6, 5))
    labels = list(breakdown.keys())
    sizes  = list(breakdown.values())
    colors = [SLEEP_STAGE_COLORS.get(label, COLORS["text"]) for label in labels]

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.1f%%",
        colors=colors, wedgeprops={"width": 0.4, "edgecolor": COLORS["bg"]},
        textprops={"color": COLORS["text"]},
    )
    for t in autotexts:
        t.set_color(COLORS["title"])
        t.set_weight("bold")
    ax.set_title(title)
    return _save(fig, path)


# ---------------------------------------------------------------------------
# HEART RATE
# ---------------------------------------------------------------------------

def plot_resting_hr(daily_df: pd.DataFrame,
                    title: str = "Resting Heart Rate",
                    path: str | Path | None = None) -> bytes:
    """Денний resting HR — індикатор фітнес-форми."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(daily_df["date"], daily_df["resting_hr"],
            color=COLORS["red"], linewidth=1.8, marker="o", markersize=3)
    if len(daily_df) >= 7:
        ax.plot(daily_df["date"], daily_df["resting_hr"].rolling(7, min_periods=1).mean(),
                color=COLORS["cyan"], linewidth=2, alpha=0.85, label="7-day avg")
        ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
                  labelcolor=COLORS["text"])
    ax.set_title(title)
    ax.set_ylabel("bpm")
    fig.autofmt_xdate()
    return _save(fig, path)


# ---------------------------------------------------------------------------
# DASHBOARD (composite — все на одному PNG для HUD/Telegram)
# ---------------------------------------------------------------------------

def plot_dashboard(steps_series: pd.DataFrame,
                   weekday_df: pd.DataFrame,
                   sleep_series: pd.DataFrame,
                   stages_breakdown: dict,
                   path: str | Path | None = None) -> bytes:
    """Композитна панель: 2x2 grid з основними метриками."""
    _setup_style()
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    # Top-left: daily steps з rolling avg
    ax = axes[0, 0]
    ax.bar(steps_series["date"], steps_series["step_count"],
           color=COLORS["blue"], alpha=0.6, width=0.9)
    ax.plot(steps_series["date"], steps_series["rolling_7d"],
            color=COLORS["cyan"], linewidth=2)
    ax.axhline(GOAL_DAILY_STEPS, color=COLORS["orange"],
               linestyle="--", linewidth=1, alpha=0.6)
    ax.set_title("Daily Steps")
    ax.set_ylabel("Steps")
    ax.tick_params(axis="x", rotation=30)

    # Top-right: weekday pattern
    ax = axes[0, 1]
    bars = ax.bar(weekday_df["weekday"], weekday_df["avg_steps"], color=COLORS["cyan"])
    for i, day in enumerate(weekday_df["weekday"]):
        if day in ["Saturday", "Sunday"]:
            bars[i].set_color(COLORS["orange"])
    ax.set_title("Avg Steps by Weekday")
    ax.set_ylabel("Steps")
    ax.tick_params(axis="x", rotation=30)

    # Bottom-left: sleep duration
    ax = axes[1, 0]
    if not sleep_series.empty:
        colors = [COLORS["red"] if h < 6 else COLORS["orange"] if h < 7
                  else COLORS["green"] for h in sleep_series["duration_h"]]
        ax.bar(sleep_series["night_date"], sleep_series["duration_h"],
               color=colors, alpha=0.85, width=0.9)
        ax.axhline(7.5, color=COLORS["cyan"], linestyle="--",
                   linewidth=1, alpha=0.7)
    ax.set_title("Sleep Duration (hours)")
    ax.set_ylabel("Hours")
    ax.tick_params(axis="x", rotation=30)

    # Bottom-right: sleep stages
    ax = axes[1, 1]
    if stages_breakdown:
        labels = list(stages_breakdown.keys())
        sizes  = list(stages_breakdown.values())
        colors = [SLEEP_STAGE_COLORS.get(l, COLORS["text"]) for l in labels]
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, autopct="%1.0f%%",
            colors=colors, wedgeprops={"width": 0.4, "edgecolor": COLORS["bg"]},
            textprops={"color": COLORS["text"], "fontsize": 9},
        )
        for t in autotexts:
            t.set_color(COLORS["title"])
            t.set_weight("bold")
    ax.set_title("Sleep Stages")

    fig.suptitle("Health Dashboard", color=COLORS["title"],
                 fontsize=15, weight="bold", y=1.00)
    fig.tight_layout()
    return _save(fig, path)
