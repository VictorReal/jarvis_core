"""
analysis.py — Аналітика витрат і надходжень з Money Manager.
"""

import pandas as pd
from .constants import NEEDS_CATEGORIES, WANTS_CATEGORIES


def filter_period(df: pd.DataFrame, period: str = "month") -> pd.DataFrame:
    """
    Календарні періоди:
      today — з 00:00 сьогодні
      week  — з понеділка цього тижня
      month — з 1 числа цього місяця
      year  — з 1 січня цього року
      all   — весь датасет
    """
    if period == "all":
        return df
    now = pd.Timestamp.now()
    if period == "today":
        cutoff = now.normalize()
    elif period == "week":
        cutoff = (now - pd.Timedelta(days=now.weekday())).normalize()
    elif period == "month":
        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        cutoff = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        cutoff = now - pd.Timedelta(days=30)
    return df[df["date"] >= cutoff].copy()


def summary(df: pd.DataFrame, period: str = "month") -> dict:
    """
    Підсумок: витрати, надходження, баланс, savings rate, top categories.
    df — об'єднаний DataFrame (expenses + income).
    """
    sub = filter_period(df, period)
    if sub.empty:
        return {"period": period, "transactions": 0, "message": "No data."}

    ex = sub[sub["kind"] == "expense"]
    inc = sub[sub["kind"] == "income"]

    total_spent = float(ex["amount"].sum())
    total_earned = float(inc["amount"].sum())
    net = total_earned - total_spent
    savings_rate = (net / total_earned * 100) if total_earned > 0 else None

    days = max((sub["date"].max() - sub["date"].min()).days, 1)

    top_cats = (ex.groupby("category")["amount"].sum()
                .sort_values(ascending=False).head(5))

    return {
        "period":           period,
        "from":             str(sub["date"].min().date()),
        "to":               str(sub["date"].max().date()),
        "days":             days,
        "transactions":     len(sub),
        "expenses_count":   len(ex),
        "income_count":     len(inc),
        "total_spent":      round(total_spent, 0),
        "total_earned":     round(total_earned, 0),
        "net":              round(net, 0),
        "savings_rate":     round(savings_rate, 1) if savings_rate is not None else None,
        "daily_avg_spend":  round(total_spent / days, 0),
        "biggest_expense":  round(float(ex["amount"].max()), 0) if not ex.empty else 0,
        "biggest_expense_category": (ex.loc[ex["amount"].idxmax(), "category"]
                                     if not ex.empty else "—"),
        "currency":         (sub["currency"].mode().iloc[0]
                             if not sub["currency"].mode().empty else "UAH"),
        "top_categories":   {k: round(float(v), 0) for k, v in top_cats.items()},
    }


def by_category(df: pd.DataFrame, period: str = "month",
                kind: str = "expense") -> pd.DataFrame:
    """Розкладка по категоріях з частками."""
    sub = filter_period(df, period)
    sub = sub[sub["kind"] == kind]
    if sub.empty:
        return pd.DataFrame(columns=["category", "amount", "count", "pct"])

    grouped = sub.groupby("category").agg(
        amount=("amount", "sum"),
        count=("amount", "count"),
    ).reset_index()
    total = grouped["amount"].sum()
    grouped["pct"] = (grouped["amount"] / total * 100).round(1) if total > 0 else 0
    return grouped.sort_values("amount", ascending=False).reset_index(drop=True)


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Помісячно: expenses, income, net."""
    sub = df.copy()
    sub["month"] = sub["date"].dt.to_period("M").dt.to_timestamp()
    ex = (sub[sub["kind"] == "expense"].groupby("month")["amount"].sum()
          .rename("expenses"))
    inc = (sub[sub["kind"] == "income"].groupby("month")["amount"].sum()
           .rename("income"))
    out = pd.concat([ex, inc], axis=1).fillna(0).reset_index()
    out["net"] = out["income"] - out["expenses"]
    return out


def daily_series(df: pd.DataFrame, period: str = "month") -> pd.DataFrame:
    """Денна агрегація трат для timeline-графіка."""
    sub = filter_period(df, period)
    ex = sub[sub["kind"] == "expense"].copy()
    if ex.empty:
        return pd.DataFrame(columns=["date", "amount", "rolling_7d"])
    ex["date_only"] = ex["date"].dt.normalize()
    daily = ex.groupby("date_only")["amount"].sum().reset_index()
    daily.columns = ["date", "amount"]
    daily["rolling_7d"] = daily["amount"].rolling(7, min_periods=1).mean()
    return daily


def weekday_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """Середні витрати по днях тижня (Mon-Sun)."""
    ex = df[df["kind"] == "expense"].copy()
    if ex.empty:
        return pd.DataFrame(columns=["weekday", "avg_amount"])
    ex["weekday"] = ex["date"].dt.day_name()
    ex["date_only"] = ex["date"].dt.date
    # Спершу сумуємо за день, потім беремо average по weekday
    daily = ex.groupby(["date_only", "weekday"])["amount"].sum().reset_index()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    avg = daily.groupby("weekday")["amount"].mean().reindex(order)
    return avg.reset_index().rename(columns={"amount": "avg_amount"})


def needs_vs_wants(df: pd.DataFrame, period: str = "month") -> dict:
    """Поділ витрат на NEEDS / WANTS / OTHER. Корисно для self-reflection."""
    sub = filter_period(df, period)
    ex = sub[sub["kind"] == "expense"]
    if ex.empty:
        return {"needs": 0, "wants": 0, "other": 0}

    def bucket(cat: str) -> str:
        if cat in NEEDS_CATEGORIES:
            return "needs"
        if cat in WANTS_CATEGORIES:
            return "wants"
        return "other"

    ex = ex.copy()
    ex["bucket"] = ex["category"].apply(bucket)
    grouped = ex.groupby("bucket")["amount"].sum().to_dict()
    total = sum(grouped.values()) or 1
    return {
        "needs":     round(float(grouped.get("needs", 0)), 0),
        "wants":     round(float(grouped.get("wants", 0)), 0),
        "other":     round(float(grouped.get("other", 0)), 0),
        "needs_pct": round(grouped.get("needs", 0) / total * 100, 1),
        "wants_pct": round(grouped.get("wants", 0) / total * 100, 1),
        "other_pct": round(grouped.get("other", 0) / total * 100, 1),
    }


def top_comments(df: pd.DataFrame, category: str, period: str = "year",
                 limit: int = 10) -> list:
    """Топ-коментарі для конкретної категорії (де саме гроші пішли)."""
    sub = filter_period(df, period)
    sub = sub[(sub["kind"] == "expense") &
              (sub["category"] == category) &
              (sub["comment"] != "")]
    if sub.empty:
        return []
    grouped = sub.groupby("comment")["amount"].agg(["sum", "count"]).reset_index()
    grouped = grouped.sort_values("sum", ascending=False).head(limit)
    return grouped.to_dict("records")


# ---------------------------------------------------------------------------
# 50/30/20 BUDGET (Elizabeth Warren rule)
# ---------------------------------------------------------------------------

def budget_503020(df: pd.DataFrame, period: str = "month") -> dict:
    """
    Аналіз compliance з правилом 50/30/20:
      - 50% income on Needs
      - 30% income on Wants
      - 20% income to Savings (тобто витрати ≤ 80% income)

    Повертає таргети, факт, % виконання і денний budget ceiling.
    """
    sub = filter_period(df, period)
    ex = sub[sub["kind"] == "expense"]
    inc = sub[sub["kind"] == "income"]

    income = float(inc["amount"].sum())
    if income <= 0:
        return {
            "income": 0,
            "available": False,
            "message": "No income in this period to compute budget.",
        }

    nw = needs_vs_wants(df, period)
    actual_needs = nw["needs"]
    actual_wants = nw["wants"]
    actual_other = nw["other"]
    total_spent = float(ex["amount"].sum())
    actual_savings = income - total_spent

    target_needs = round(income * 0.50, 0)
    target_wants = round(income * 0.30, 0)
    target_savings = round(income * 0.20, 0)
    target_total_spend = round(income * 0.80, 0)

    # Денний budget ceiling — для денного графіка
    days = max((sub["date"].max() - sub["date"].min()).days, 1) if not sub.empty else 1
    daily_budget = round(target_total_spend / days, 0)

    def pct_used(actual, target):
        return round(actual / target * 100, 1) if target > 0 else 0

    return {
        "available": True,
        "period": period,
        "currency": (sub["currency"].mode().iloc[0]
                     if not sub["currency"].mode().empty else "UAH"),
        "income": round(income, 0),
        "days": days,
        "daily_budget": daily_budget,

        # Цілі
        "target_needs":   target_needs,
        "target_wants":   target_wants,
        "target_savings": target_savings,
        "target_total":   target_total_spend,

        # Факт
        "actual_needs":   round(actual_needs, 0),
        "actual_wants":   round(actual_wants, 0),
        "actual_other":   round(actual_other, 0),
        "actual_savings": round(actual_savings, 0),
        "actual_total":   round(total_spent, 0),

        # Compliance %
        "needs_used_pct":   pct_used(actual_needs, target_needs),
        "wants_used_pct":   pct_used(actual_wants, target_wants),
        "savings_done_pct": pct_used(actual_savings, target_savings),
        "total_used_pct":   pct_used(total_spent, target_total_spend),

        # Статус
        "needs_ok":   actual_needs <= target_needs,
        "wants_ok":   actual_wants <= target_wants,
        "savings_ok": actual_savings >= target_savings,
        "overall_ok": (actual_needs <= target_needs and
                       actual_wants <= target_wants and
                       actual_savings >= target_savings),
    }
