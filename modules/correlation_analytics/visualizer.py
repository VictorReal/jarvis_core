"""
visualizer.py — графіки крос-кореляції в JARVIS-темі. PNG у файл / BytesIO.
"""
import io
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .constants import COLORS, METRICS
from . import analysis as an


def _style():
    plt.rcParams.update({
        "figure.facecolor": COLORS["bg"], "axes.facecolor": COLORS["panel"],
        "axes.edgecolor": COLORS["grid"], "axes.labelcolor": COLORS["text"],
        "axes.titlecolor": COLORS["title"], "xtick.color": COLORS["text"],
        "ytick.color": COLORS["text"], "grid.color": COLORS["grid"],
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
        "text.color": COLORS["text"],
    })


def _save(fig, path=None) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor=COLORS["bg"])
    plt.close(fig)
    buf.seek(0)
    data = buf.getvalue()
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)
    return data


def plot_matrix(df: pd.DataFrame, title="Correlation Matrix", path=None) -> bytes:
    """Теплова карта кореляцій."""
    _style()
    corr = an.correlation_matrix(df)
    fig, ax = plt.subplots(figsize=(6.5, 5.5))
    if corr.empty:
        ax.text(0.5, 0.5, "Not enough data", color=COLORS["text"],
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return _save(fig, path)
    labels = [METRICS.get(c, c) for c in corr.columns]
    im = ax.imshow(corr.values, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels)
    for i in range(len(corr)):
        for j in range(len(corr)):
            v = corr.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                        color="black", fontweight="bold", fontsize=9)
    ax.set_title(title)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return _save(fig, path)


def plot_scatter(df: pd.DataFrame, x: str, y: str, path=None) -> bytes:
    """Scatter двох метрик + лінія тренду."""
    _style()
    fig, ax = plt.subplots(figsize=(6, 4.5))
    pair = df[[x, y]].dropna()
    if len(pair) < 3:
        ax.text(0.5, 0.5, "Not enough overlap", color=COLORS["text"],
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off"); return _save(fig, path)
    ax.scatter(pair[x], pair[y], color=COLORS["cyan"], alpha=0.6, s=22)
    # лінія тренду
    z = np.polyfit(pair[x], pair[y], 1)
    xs = np.linspace(pair[x].min(), pair[x].max(), 50)
    ax.plot(xs, np.polyval(z, xs), color=COLORS["orange"], lw=2)
    r = pair[x].corr(pair[y])
    ax.set_xlabel(METRICS.get(x, x)); ax.set_ylabel(METRICS.get(y, y))
    ax.set_title(f"{METRICS.get(y, y)} vs {METRICS.get(x, x)}  (r={r:.2f})")
    ax.grid(True, color=COLORS["grid"], alpha=0.3)
    return _save(fig, path)


def plot_timeline(df: pd.DataFrame, path=None) -> bytes:
    """Нормалізовані ряди всіх метрик в одному часовому вікні (z-score) — побачити синхронність."""
    _style()
    fig, ax = plt.subplots(figsize=(11, 4.5))
    if df.empty:
        ax.text(0.5, 0.5, "No data", color=COLORS["text"],
                ha="center", va="center", transform=ax.transAxes)
        ax.axis("off"); return _save(fig, path)
    palette = [COLORS["cyan"], COLORS["purple"], COLORS["green"], COLORS["orange"], COLORS["red"]]
    for i, col in enumerate(df.columns):
        s = df[col].dropna()
        if s.std() and len(s) > 2:
            z = (s - s.mean()) / s.std()
            ax.plot(z.index, z.values, label=METRICS.get(col, col),
                    color=palette[i % len(palette)], lw=1.3, alpha=0.85)
    ax.set_title("Normalized metrics over time (z-score)")
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"], fontsize=8, ncol=len(df.columns))
    ax.grid(True, color=COLORS["grid"], alpha=0.3)
    fig.autofmt_xdate()
    return _save(fig, path)


def plot_dashboard(df: pd.DataFrame, path=None) -> bytes:
    """Композит 2x2: матриця + timeline + 2 найсильніші scatter-пари."""
    _style()
    fig = plt.figure(figsize=(13, 9))
    pairs = an.strongest_pairs(df, top=2)

    # матриця (верх-ліво)
    ax1 = fig.add_subplot(2, 2, 1)
    corr = an.correlation_matrix(df)
    if not corr.empty:
        labels = [METRICS.get(c, c) for c in corr.columns]
        im = ax1.imshow(corr.values, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
        ax1.set_xticks(range(len(labels))); ax1.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax1.set_yticks(range(len(labels))); ax1.set_yticklabels(labels, fontsize=8)
        for i in range(len(corr)):
            for j in range(len(corr)):
                v = corr.values[i, j]
                if not np.isnan(v):
                    ax1.text(j, i, f"{v:.2f}", ha="center", va="center",
                             color="black", fontweight="bold", fontsize=7)
    ax1.set_title("Correlation Matrix")

    # timeline (верх-право)
    ax2 = fig.add_subplot(2, 2, 2)
    palette = [COLORS["cyan"], COLORS["purple"], COLORS["green"], COLORS["orange"], COLORS["red"]]
    for i, col in enumerate(df.columns):
        s = df[col].dropna()
        if s.std() and len(s) > 2:
            z = (s - s.mean()) / s.std()
            ax2.plot(z.index, z.values, label=METRICS.get(col, col),
                     color=palette[i % len(palette)], lw=1, alpha=0.8)
    ax2.set_title("Normalized over time")
    ax2.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
               labelcolor=COLORS["text"], fontsize=7)
    ax2.tick_params(axis="x", rotation=30)

    # 2 scatter (низ)
    for idx, p in enumerate(pairs):
        ax = fig.add_subplot(2, 2, 3 + idx)
        pair = df[[p["a"], p["b"]]].dropna()
        if len(pair) >= 3:
            ax.scatter(pair[p["a"]], pair[p["b"]], color=COLORS["cyan"], alpha=0.6, s=18)
            z = np.polyfit(pair[p["a"]], pair[p["b"]], 1)
            xs = np.linspace(pair[p["a"]].min(), pair[p["a"]].max(), 50)
            ax.plot(xs, np.polyval(z, xs), color=COLORS["orange"], lw=2)
            ax.set_xlabel(METRICS.get(p["a"], p["a"]), fontsize=8)
            ax.set_ylabel(METRICS.get(p["b"], p["b"]), fontsize=8)
            ax.set_title(f"r={p['r']}", fontsize=10)
        ax.grid(True, color=COLORS["grid"], alpha=0.3)

    fig.suptitle("JARVIS · Cross-Correlation Dashboard", color=COLORS["title"],
                 fontsize=15, weight="bold", y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return _save(fig, path)
