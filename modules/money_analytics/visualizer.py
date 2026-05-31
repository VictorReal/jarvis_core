"""
visualizer.py — графіки витрат у JARVIS HUD-стилі.
"""

import io
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

from .constants import CATEGORY_COLORS

# Палітра в стилі HUD
COLORS = {
    "bg":     "#0a0e1a",
    "panel":  "#0f1626",
    "grid":   "#1c2942",
    "text":   "#a8c5e8",
    "title":  "#e8f0ff",
    "cyan":   "#00d4ff",
    "blue":   "#3a6df0",
    "green":  "#00ff88",
    "orange": "#ff9500",
    "red":    "#ff3b30",
}


def _setup_style():
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
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor=COLORS["bg"])
    plt.close(fig)
    buf.seek(0)
    data = buf.getvalue()
    if path:
        Path(path).write_bytes(data)
    return data


def plot_categories_pie(cat_df: pd.DataFrame, title: str = "Spending by Category",
                        top_n: int = 8, path=None) -> bytes:
    """Donut-чарт топ-N категорій + Other."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(7, 6))

    if cat_df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                color=COLORS["text"], fontsize=14, transform=ax.transAxes)
        ax.axis("off")
        return _save(fig, path)

    top = cat_df.head(top_n).copy()
    rest = cat_df.iloc[top_n:]
    if not rest.empty:
        other_row = pd.DataFrame([{
            "category": "Other",
            "amount": rest["amount"].sum(),
            "count": rest["count"].sum(),
            "pct": rest["pct"].sum(),
        }])
        top = pd.concat([top, other_row], ignore_index=True)

    colors = CATEGORY_COLORS[:len(top)]
    wedges, texts, autotexts = ax.pie(
        top["amount"], labels=top["category"],
        autopct="%1.0f%%",
        colors=colors,
        wedgeprops={"width": 0.42, "edgecolor": COLORS["bg"], "linewidth": 1.5},
        textprops={"color": COLORS["text"], "fontsize": 10},
        pctdistance=0.8,
    )
    for t in autotexts:
        t.set_color(COLORS["title"])
        t.set_weight("bold")
        t.set_fontsize(9)

    ax.set_title(title)
    return _save(fig, path)


def plot_monthly_trend(monthly: pd.DataFrame, title: str = "Monthly: Income vs Expenses",
                       show_budget_target: bool = True, path=None) -> bytes:
    """Bar chart: income vs expenses + net line + 80%-of-income target."""
    _setup_style()
    if monthly.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                color=COLORS["text"], transform=ax.transAxes)
        return _save(fig, path)

    fig, ax = plt.subplots(figsize=(11, 4.5))

    x = list(range(len(monthly)))
    width = 0.4

    ax.bar([i - width/2 for i in x], monthly["income"], width=width,
           color=COLORS["green"], alpha=0.85, label="Income")
    ax.bar([i + width/2 for i in x], monthly["expenses"], width=width,
           color=COLORS["orange"], alpha=0.85, label="Expenses")

    # 80%-of-income line (per-month target for total spending under 50/30/20)
    if show_budget_target:
        targets = (monthly["income"] * 0.8).tolist()
        # рисуємо як короткі сегменти над кожним expense-баром
        for i, t in enumerate(targets):
            if t > 0:
                ax.hlines(t, i - width, i + width,
                          colors=COLORS["red"], linestyles="--",
                          linewidth=1.4, alpha=0.85,
                          label="80% target" if i == 0 else None)

    ax.plot(x, monthly["net"], color=COLORS["cyan"], linewidth=2.2,
            marker="o", markersize=5, label="Net")
    ax.axhline(0, color=COLORS["text"], linestyle="-", linewidth=0.5, alpha=0.4)

    ax.set_xticks(x)
    ax.set_xticklabels([m.strftime("%b %y") for m in monthly["month"]], rotation=30)
    ax.set_title(title)
    ax.set_ylabel("UAH")
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"])
    return _save(fig, path)


def plot_budget_503020(budget: dict, title: str = "Budget: 50/30/20 Rule",
                       path=None) -> bytes:
    """Side-by-side: actual vs target для Needs / Wants / Savings."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(10, 5))

    if not budget.get("available"):
        ax.text(0.5, 0.5, "No income in period — can't compute budget",
                ha="center", va="center", color=COLORS["text"],
                transform=ax.transAxes)
        ax.axis("off")
        return _save(fig, path)

    labels = ["Needs (≤50%)", "Wants (≤30%)", "Savings (≥20%)"]
    targets = [budget["target_needs"], budget["target_wants"], budget["target_savings"]]
    actuals = [budget["actual_needs"], budget["actual_wants"], budget["actual_savings"]]

    x = list(range(len(labels)))
    w = 0.38

    # Target bars (background, dim)
    ax.bar([i - w/2 for i in x], targets, w,
           color=COLORS["text"], alpha=0.3, label="Target")
    # Actual bars (color-coded by status)
    colors = []
    statuses = [budget["needs_ok"], budget["wants_ok"], budget["savings_ok"]]
    for ok in statuses:
        colors.append(COLORS["green"] if ok else COLORS["red"])
    ax.bar([i + w/2 for i in x], actuals, w, color=colors,
           alpha=0.9, label="Actual")

    # Підписи (% від таргету). >100% = перевитрата (для needs/wants) → позначаємо.
    pcts = [budget["needs_used_pct"], budget["wants_used_pct"], budget["savings_done_pct"]]
    statuses_lbl = [budget["needs_ok"], budget["wants_ok"], budget["savings_ok"]]
    for i, (a, p, ok) in enumerate(zip(actuals, pcts, statuses_lbl)):
        # для savings >=100% це добре; для needs/wants >100% це over budget
        is_savings = (i == 2)
        if not ok and not is_savings and p > 100:
            label = f"{p:.0f}%  over"
        elif not ok and is_savings:
            label = f"{p:.0f}%  under"
        else:
            label = f"{p:.0f}%"
        ax.text(i + w/2, a, label, ha="center", va="bottom",
                color=COLORS["title"], fontweight="bold", fontsize=10)

    # Пояснювальна лінія таргету (100% орієнтир для кожної категорії — на рівні target бару)
    ax.text(0.99, 0.97,
            ">100% on Needs/Wants = over budget",
            transform=ax.transAxes, ha="right", va="top",
            color=COLORS["text"], fontsize=8, alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title(title + f"  ·  Income: {budget['income']:,.0f} {budget['currency']}")
    ax.set_ylabel(budget["currency"])
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"])
    return _save(fig, path)


def plot_daily_spend(daily: pd.DataFrame, title: str = "Daily Spending",
                     daily_budget: float | None = None, path=None) -> bytes:
    """Денні витрати + 7-day rolling avg + (опційно) budget ceiling line."""
    _setup_style()
    if daily.empty:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                color=COLORS["text"], transform=ax.transAxes)
        return _save(fig, path)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(daily["date"], daily["amount"],
           color=COLORS["orange"], alpha=0.55, width=0.9, label="Daily")
    ax.plot(daily["date"], daily["rolling_7d"],
            color=COLORS["cyan"], linewidth=2, label="7-day avg")
    if daily_budget and daily_budget > 0:
        ax.axhline(daily_budget, color=COLORS["red"], linestyle="--",
                   linewidth=1.4, alpha=0.85,
                   label=f"50/30/20 daily budget ({daily_budget:,.0f})")
    ax.set_title(title)
    ax.set_ylabel("UAH")
    ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
              labelcolor=COLORS["text"])
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.autofmt_xdate()
    return _save(fig, path)


def plot_weekday(weekday_df: pd.DataFrame, title: str = "Spending by Weekday",
                 path=None) -> bytes:
    """Бар-чарт по днях тижня (виходні підсвічуємо)."""
    _setup_style()
    if weekday_df.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                color=COLORS["text"], transform=ax.transAxes)
        return _save(fig, path)

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(weekday_df["weekday"], weekday_df["avg_amount"],
                  color=COLORS["cyan"])
    for i, day in enumerate(weekday_df["weekday"]):
        if day in ["Saturday", "Sunday"]:
            bars[i].set_color(COLORS["orange"])
    ax.set_title(title)
    ax.set_ylabel("Avg UAH/day")
    return _save(fig, path)


def plot_needs_vs_wants(needs_wants: dict, title: str = "Needs vs Wants",
                        path=None) -> bytes:
    """Donut: needs / wants / other."""
    _setup_style()
    fig, ax = plt.subplots(figsize=(6, 5))
    labels = ["Needs", "Wants", "Other"]
    sizes = [needs_wants.get("needs", 0),
             needs_wants.get("wants", 0),
             needs_wants.get("other", 0)]
    colors = [COLORS["green"], COLORS["orange"], COLORS["text"]]
    if sum(sizes) == 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                color=COLORS["text"], transform=ax.transAxes)
        ax.axis("off")
        return _save(fig, path)

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.0f%%",
        colors=colors,
        wedgeprops={"width": 0.42, "edgecolor": COLORS["bg"], "linewidth": 1.5},
        textprops={"color": COLORS["text"]},
    )
    for t in autotexts:
        t.set_color(COLORS["title"])
        t.set_weight("bold")
    ax.set_title(title)
    return _save(fig, path)


def plot_dashboard(cat_df, monthly, daily, budget, path=None) -> bytes:
    """Композитна панель 2x2: categories, monthly, daily (з budget line), 50/30/20."""
    _setup_style()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    # TL: categories pie
    ax = axes[0, 0]
    if not cat_df.empty:
        top = cat_df.head(7).copy()
        rest = cat_df.iloc[7:]
        if not rest.empty:
            other = pd.DataFrame([{"category": "Other", "amount": rest["amount"].sum(),
                                   "count": 0, "pct": rest["pct"].sum()}])
            top = pd.concat([top, other], ignore_index=True)
        colors = CATEGORY_COLORS[:len(top)]
        w, t, at = ax.pie(top["amount"], labels=top["category"], autopct="%1.0f%%",
                          colors=colors,
                          wedgeprops={"width": 0.4, "edgecolor": COLORS["bg"]},
                          textprops={"color": COLORS["text"], "fontsize": 9},
                          pctdistance=0.8)
        for a in at:
            a.set_color(COLORS["title"])
            a.set_weight("bold")
            a.set_fontsize(8)
    ax.set_title("By Category")

    # TR: monthly bars + 80% target line
    ax = axes[0, 1]
    if not monthly.empty:
        x = list(range(len(monthly)))
        w = 0.4
        ax.bar([i - w/2 for i in x], monthly["income"], w,
               color=COLORS["green"], alpha=0.85, label="Income")
        ax.bar([i + w/2 for i in x], monthly["expenses"], w,
               color=COLORS["orange"], alpha=0.85, label="Expenses")
        # 80% target per month
        targets = (monthly["income"] * 0.8).tolist()
        for i, t in enumerate(targets):
            if t > 0:
                ax.hlines(t, i - w, i + w, colors=COLORS["red"],
                          linestyles="--", linewidth=1.2, alpha=0.85,
                          label="80% target" if i == 0 else None)
        ax.plot(x, monthly["net"], color=COLORS["cyan"], linewidth=2,
                marker="o", markersize=4, label="Net")
        ax.set_xticks(x)
        ax.set_xticklabels([m.strftime("%b") for m in monthly["month"]], rotation=30)
        ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
                  labelcolor=COLORS["text"], fontsize=8)
    ax.set_title("Income vs Expenses (with 80% target)")
    ax.set_ylabel("UAH")

    # BL: daily spending з budget ceiling
    ax = axes[1, 0]
    if not daily.empty:
        ax.bar(daily["date"], daily["amount"], color=COLORS["orange"], alpha=0.55, width=0.9)
        ax.plot(daily["date"], daily["rolling_7d"], color=COLORS["cyan"], linewidth=2)
        if budget and budget.get("available") and budget.get("daily_budget", 0) > 0:
            ax.axhline(budget["daily_budget"], color=COLORS["red"],
                       linestyle="--", linewidth=1.4, alpha=0.85,
                       label=f"Budget {budget['daily_budget']:,.0f}/day")
            ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
                      labelcolor=COLORS["text"], fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.tick_params(axis="x", rotation=30)
    ax.set_title("Daily Spending vs Budget")
    ax.set_ylabel("UAH")

    # BR: 50/30/20 actual vs target
    ax = axes[1, 1]
    if budget and budget.get("available"):
        labels = ["Needs\n(≤50%)", "Wants\n(≤30%)", "Savings\n(≥20%)"]
        targets = [budget["target_needs"], budget["target_wants"], budget["target_savings"]]
        actuals = [budget["actual_needs"], budget["actual_wants"], budget["actual_savings"]]
        statuses = [budget["needs_ok"], budget["wants_ok"], budget["savings_ok"]]
        colors = [COLORS["green"] if ok else COLORS["red"] for ok in statuses]

        x = list(range(len(labels)))
        w = 0.38
        ax.bar([i - w/2 for i in x], targets, w, color=COLORS["text"], alpha=0.3, label="Target")
        ax.bar([i + w/2 for i in x], actuals, w, color=colors, alpha=0.9, label="Actual")

        pcts = [budget["needs_used_pct"], budget["wants_used_pct"], budget["savings_done_pct"]]
        for i, (a, p) in enumerate(zip(actuals, pcts)):
            ax.text(i + w/2, a, f"{p:.0f}%", ha="center", va="bottom",
                    color=COLORS["title"], fontweight="bold", fontsize=9)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.legend(facecolor=COLORS["panel"], edgecolor=COLORS["grid"],
                  labelcolor=COLORS["text"], fontsize=8)
    else:
        ax.text(0.5, 0.5, "No income — no budget", ha="center", va="center",
                color=COLORS["text"], transform=ax.transAxes)
        ax.axis("off")
    ax.set_title("50/30/20 Rule (actual vs target)")

    fig.suptitle("Finance Dashboard", color=COLORS["title"],
                 fontsize=15, weight="bold", y=1.00)
    fig.tight_layout()
    return _save(fig, path)
