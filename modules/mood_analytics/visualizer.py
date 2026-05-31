"""
Візуалізація настрою → PNG.
Стиль узгоджено з HUD (тёмний фон, --hud-accent).
Кожна функція повертає шлях до збереженого PNG у cache/.
Дашборд (combined) — для Telegram одним зображенням.
"""
import os

import matplotlib
matplotlib.use("Agg")  # без GUI — рендер у файл
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from .constants import (
    CACHE_DIR, COLOR_ACCENT, COLOR_ACCENT2, COLOR_BAD,
    COLOR_BG, COLOR_GRID, COLOR_TEXT, SCORE_MAX, score_color,
)
from . import analysis


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _style_ax(ax, title=""):
    """Спільний тёмний стиль осей під HUD."""
    ax.set_facecolor(COLOR_BG)
    ax.tick_params(colors=COLOR_TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(COLOR_GRID)
    ax.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.5)
    if title:
        ax.set_title(title, color=COLOR_ACCENT, fontsize=11, pad=10)


def _save(fig, name: str) -> str:
    _ensure_cache()
    path = os.path.join(CACHE_DIR, name)
    fig.patch.set_facecolor(COLOR_BG)
    fig.savefig(path, dpi=110, bbox_inches="tight", facecolor=COLOR_BG)
    plt.close(fig)
    return path


def chart_trend(df, name="mood_trend.png") -> str:
    """Лінія середнього настрою по днях."""
    series = analysis.daily_series(df)
    fig, ax = plt.subplots(figsize=(6, 3))
    _style_ax(ax, "MOOD TREND")
    if not series.empty:
        ax.plot(series["date"], series["score"],
                color=COLOR_ACCENT, linewidth=2, marker="o", markersize=4)
        ax.fill_between(series["date"], series["score"], 0,
                        color=COLOR_ACCENT, alpha=0.12)
        ax.set_ylim(0, SCORE_MAX)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        fig.autofmt_xdate(rotation=45)
    else:
        ax.text(0.5, 0.5, "NO DATA", color=COLOR_TEXT,
                ha="center", va="center", transform=ax.transAxes)
    return _save(fig, name)


def chart_tags(df, name="mood_tags.png") -> str:
    """Горизонтальний бар частоти тегів."""
    dist = analysis.tag_distribution(df)
    fig, ax = plt.subplots(figsize=(6, 3))
    _style_ax(ax, "TAG FREQUENCY")
    if not dist.empty:
        dist = dist.head(10)[::-1]
        ax.barh(dist.index, dist.values, color=COLOR_ACCENT2, alpha=0.8)
    else:
        ax.text(0.5, 0.5, "NO TAGS", color=COLOR_TEXT,
                ha="center", va="center", transform=ax.transAxes)
    return _save(fig, name)


def chart_distribution(df, name="mood_dist.png") -> str:
    """Гістограма розподілу оцінок 1-10."""
    fig, ax = plt.subplots(figsize=(6, 3))
    _style_ax(ax, "SCORE DISTRIBUTION")
    if not df.empty:
        counts = df["score"].value_counts().sort_index()
        colors = [score_color(s) for s in counts.index]
        ax.bar(counts.index, counts.values, color=colors, alpha=0.85)
        ax.set_xticks(range(1, SCORE_MAX + 1))
        ax.set_xlim(0.5, SCORE_MAX + 0.5)
    else:
        ax.text(0.5, 0.5, "NO DATA", color=COLOR_TEXT,
                ha="center", va="center", transform=ax.transAxes)
    return _save(fig, name)


def chart_hourly(df, name="mood_hourly.png") -> str:
    """Середній настрій по днях тижня (Mon..Sun). (маршрут лишається 'hourly')."""
    series = analysis.weekday_distribution(df)
    fig, ax = plt.subplots(figsize=(6, 3))
    _style_ax(ax, "MOOD BY DAY")
    if series is not None and not series.dropna().empty:
        labels = [d[:3] for d in series.index]
        vals = series.values
        colors = [score_color(v) if v == v else COLOR_TEXT for v in vals]
        xs = range(len(labels))
        ax.bar(xs, [0 if v != v else v for v in vals], color=colors, alpha=0.85)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(labels)
        ax.set_ylim(0, SCORE_MAX)
    else:
        ax.text(0.5, 0.5, "NO DATA", color=COLOR_TEXT,
                ha="center", va="center", transform=ax.transAxes)
    return _save(fig, name)


def dashboard(df, name="mood_dashboard.png") -> str:
    """Комбінований дашборд 2x2 — для Telegram одним зображенням."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    fig.suptitle("JARVIS · MOOD ANALYTICS", color=COLOR_ACCENT,
                 fontsize=15, fontweight="bold", y=0.98)

    # 1. Тренд
    ax = axes[0, 0]; _style_ax(ax, "MOOD TREND")
    series = analysis.daily_series(df)
    if not series.empty:
        ax.plot(series["date"], series["score"], color=COLOR_ACCENT,
                linewidth=2, marker="o", markersize=3)
        ax.fill_between(series["date"], series["score"], 0, color=COLOR_ACCENT, alpha=0.12)
        ax.set_ylim(0, SCORE_MAX)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        for lbl in ax.get_xticklabels():
            lbl.set_rotation(45); lbl.set_ha("right")
    else:
        ax.text(0.5, 0.5, "NO DATA", color=COLOR_TEXT, ha="center", va="center", transform=ax.transAxes)

    # 2. Теги
    ax = axes[0, 1]; _style_ax(ax, "TOP TAGS")
    dist = analysis.tag_distribution(df)
    if not dist.empty:
        dist = dist.head(8)[::-1]
        ax.barh(dist.index, dist.values, color=COLOR_ACCENT2, alpha=0.8)
    else:
        ax.text(0.5, 0.5, "NO TAGS", color=COLOR_TEXT, ha="center", va="center", transform=ax.transAxes)

    # 3. Розподіл оцінок
    ax = axes[1, 0]; _style_ax(ax, "SCORE DISTRIBUTION")
    if not df.empty:
        counts = df["score"].value_counts().sort_index()
        ax.bar(counts.index, counts.values, color=[score_color(s) for s in counts.index], alpha=0.85)
        ax.set_xticks(range(1, SCORE_MAX + 1))
    else:
        ax.text(0.5, 0.5, "NO DATA", color=COLOR_TEXT, ha="center", va="center", transform=ax.transAxes)

    # 4. За годиною
    ax = axes[1, 1]; _style_ax(ax, "MOOD BY HOUR")
    hourly = analysis.hour_distribution(df)
    if not hourly.empty:
        ax.bar(hourly.index, hourly.values, color=[score_color(s) for s in hourly.values], alpha=0.85)
        ax.set_ylim(0, SCORE_MAX)
    else:
        ax.text(0.5, 0.5, "NO DATA", color=COLOR_TEXT, ha="center", va="center", transform=ax.transAxes)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    return _save(fig, name)
