"""
report.py — текстові звіти для Telegram у форматі без markdown
(пам'ять каже: Jarvis spoken/written responses concise, non-markdown).
"""

from .constants import GOAL_DAILY_STEPS, GOAL_SLEEP_HOURS


def _trim_num(x, decimals=0):
    if x is None or x == "—":
        return "—"
    try:
        if decimals == 0:
            return f"{int(x)}"
        return f"{float(x):.{decimals}f}"
    except Exception:
        return str(x)


def steps_report(summary: dict) -> str:
    """Звіт по кроках для Telegram."""
    if summary.get("days", 0) == 0:
        return "📊 Steps: no data for this period."

    p = summary["period"]
    goal_emoji = "✅" if summary.get("goal_met_pct", 0) >= 50 else "⚠️"

    lines = [
        f"👟 STEPS — {p.upper()}",
        f"Days tracked: {summary['days']}",
        f"Total steps: {summary['total_steps']:,}",
        f"Daily avg: {summary['avg_steps']:,} (median {summary['median_steps']:,})",
        f"Best day: {summary['max_steps']:,} ({summary['max_date']})",
        f"Distance: {_trim_num(summary['total_km'], 1)} km",
        f"Calories burned: {summary['total_calories']:,}",
        f"Active minutes: {summary['active_minutes']}",
        f"{goal_emoji} Goal 10K met: {summary['goal_met_days']}/{summary['days']} days ({_trim_num(summary['goal_met_pct'], 1)}%)",
    ]
    return "\n".join(lines)


def sleep_report(summary: dict, stages_breakdown: dict | None = None) -> str:
    """Звіт по сну."""
    if summary.get("nights", 0) == 0:
        return "🛌 Sleep: no data for this period."

    p = summary["period"]
    avg_h = summary["avg_duration_h"]
    goal_emoji = "✅" if avg_h >= GOAL_SLEEP_HOURS else "⚠️"

    lines = [
        f"🛌 SLEEP — {p.upper()}",
        f"Nights tracked: {summary['nights']}",
        f"{goal_emoji} Avg duration: {_trim_num(avg_h, 2)}h (goal {GOAL_SLEEP_HOURS}h)",
        f"Efficiency: {_trim_num(summary['avg_efficiency'], 1)}%",
        f"Shortest: {_trim_num(summary['shortest_h'], 1)}h | Longest: {_trim_num(summary['longest_h'], 1)}h",
    ]
    if summary.get("avg_sleep_score") is not None:
        lines.append(f"Sleep score: {_trim_num(summary['avg_sleep_score'], 1)}/100")

    if stages_breakdown:
        stages = " | ".join(f"{k} {v:.0f}%" for k, v in stages_breakdown.items())
        lines.append(f"Stages: {stages}")

    return "\n".join(lines)


def hr_report(summary: dict) -> str:
    """Звіт по пульсу."""
    if summary.get("samples", 0) == 0:
        return "❤️ Heart rate: no data for this period."

    lines = [
        f"❤️ HEART RATE — {summary['period'].upper()}",
        f"Samples: {summary['samples']:,}",
        f"Average: {_trim_num(summary['avg_hr'], 1)} bpm",
        f"Range: {summary['min_hr']}–{summary['max_hr']} bpm",
    ]
    if summary.get("resting_avg") is not None:
        lines.append(f"Resting avg: {_trim_num(summary['resting_avg'], 1)} bpm")
    lines.append(f"Active samples (>120): {summary['active_count']}")
    return "\n".join(lines)


def exercise_report(summary: dict) -> str:
    """Звіт по тренуваннях."""
    if summary.get("sessions", 0) == 0:
        return "🏋️ Exercise: no workouts in this period."

    lines = [
        f"🏋️ EXERCISE — {summary['period'].upper()}",
        f"Sessions: {summary['sessions']}",
        f"Total time: {summary['total_minutes']} min",
        f"Avg session: {_trim_num(summary['avg_duration'], 1)} min",
        f"Distance: {_trim_num(summary['total_km'], 2)} km",
        f"Calories: {summary['total_calories']:,}",
        f"Most frequent: {summary['top_type']}",
    ]
    if summary.get("avg_mean_hr") is not None:
        lines.append(f"Avg HR during workout: {_trim_num(summary['avg_mean_hr'], 0)} bpm")
    return "\n".join(lines)


def full_report(steps_sum: dict, sleep_sum: dict, hr_sum: dict, ex_sum: dict,
                stages: dict | None = None) -> str:
    """Повний health-звіт для Telegram (комбінований)."""
    parts = [
        steps_report(steps_sum),
        "",
        sleep_report(sleep_sum, stages),
        "",
        hr_report(hr_sum),
        "",
        exercise_report(ex_sum),
    ]
    return "\n".join(parts)
