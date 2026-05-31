"""
Текстовий звіт настрою.
Формує лаконічний non-markdown текст (стиль JARVIS) для Telegram і голосу.
"""
from .constants import SCORE_MAX
from . import analysis

_TREND_LABEL = {"up": "improving", "down": "declining", "flat": "stable"}


def build_report(df, period: str = "week") -> str:
    """Текстовий звіт за період. Без markdown — щоб годилось і для TTS."""
    stats = analysis.summary_stats(df)

    if stats["count"] == 0:
        return f"No mood entries logged for this {period} yet, Sir."

    lines = [f"Mood report ({period}):"]
    lines.append(f"Entries: {stats['count']}. Average: {stats['avg']}/{SCORE_MAX}.")
    lines.append(f"Latest: {stats['latest']}/{SCORE_MAX}"
                 + (f" ({', '.join(stats['latest_tags'])})." if stats['latest_tags'] else "."))
    lines.append(f"Range: {stats['min']} to {stats['max']}. "
                 f"Trend: {_TREND_LABEL.get(stats['trend'], 'stable')}.")

    if stats["positive_pct"] is not None:
        lines.append(f"Positive days: {stats['positive_pct']} percent.")

    mve = analysis.morning_vs_evening(df)
    if mve["morning"] is not None and mve["evening"] is not None:
        delta = round(mve["evening"] - mve["morning"], 1)
        direction = "higher" if delta > 0 else "lower" if delta < 0 else "equal"
        lines.append(f"Mornings {mve['morning']}, evenings {mve['evening']} "
                     f"({direction} by end of day).")

    dist = analysis.tag_distribution(df)
    if not dist.empty:
        top = ", ".join(dist.head(3).index.tolist())
        lines.append(f"Most frequent tags: {top}.")

    if stats.get("days_logged", 0) > 1:
        lines.append(f"Days logged: {stats['days_logged']}.")

    return " ".join(lines)


def short_status(df) -> str:
    """Однорядковий статус — для голосової відповіді після log_mood."""
    stats = analysis.summary_stats(df)
    if stats["count"] == 0:
        return "No mood data yet, Sir."
    return (f"Logged. Your average this week is "
            f"{stats['avg']}/{SCORE_MAX}, trend {_TREND_LABEL.get(stats['trend'], 'stable')}.")


def insights(df) -> list[str]:
    """Короткі рекомендації для HUD-блоку висновків (на основі stats/тегів)."""
    from . import analysis as _an
    stats = _an.summary_stats(df)
    if stats["count"] == 0:
        return ["No mood data yet, Sir."]

    out = []
    avg = stats["avg"]
    if avg is not None:
        if avg < 4:
            out.append(f"Average mood {avg}/10 is low — consider what's draining you and seek support if it persists.")
        elif avg >= 7:
            out.append(f"Average mood {avg}/10 is strong. Keep doing what works.")
        else:
            out.append(f"Average mood {avg}/10 is moderate.")

    if stats["trend"] == "down":
        out.append("Mood is trending down recently — worth a closer look at sleep and workload.")
    elif stats["trend"] == "up":
        out.append("Mood is trending up — good momentum.")

    mve = _an.morning_vs_evening(df)
    if mve["morning"] is not None and mve["evening"] is not None:
        if mve["evening"] < mve["morning"] - 0.5:
            out.append("Mood tends to drop by evening — protect your energy later in the day.")
        elif mve["morning"] < mve["evening"] - 0.5:
            out.append("Mornings are tougher than evenings — a gentler morning routine may help.")

    dist = _an.tag_distribution(df)
    if not dist.empty:
        from .constants import NEGATIVE_TAGS
        top = dist.head(3).index.tolist()
        neg_top = [t for t in top if t in NEGATIVE_TAGS]
        if neg_top:
            out.append(f"Frequent tags include '{neg_top[0]}' — recurring theme worth addressing.")

    if stats.get("days_logged", 0) > 7:
        out.append(f"{stats['days_logged']} days logged — consistent self-tracking.")
    if stats.get("best_day"):
        out.append(f"Your best mood day tends to be {stats['best_day']}.")

    return out or ["Mood is steady, Sir."]
