"""
report.py — текстовий звіт крос-кореляції для Telegram/TTS (non-markdown).
"""
from . import analysis as an
from .constants import METRICS


def build_report(df, period_label: str = "all time") -> str:
    s = an.summary(df)
    if not s["available"]:
        return "No cross-metric data available yet, Sir."

    lines = [f"Cross-correlation report ({period_label}):"]
    lines.append(f"Metrics tracked: {', '.join(s['metrics'])}.")
    lines.append(f"Days with data: {s['days']} (full overlap: {s['full_overlap_days']}).")

    if s["pairs"]:
        lines.append("Strongest links:")
        for p in s["pairs"][:4]:
            a = METRICS.get(p["a"], p["a"])
            b = METRICS.get(p["b"], p["b"])
            sign = "+" if p["r"] > 0 else ""
            lines.append(f"  {a} <-> {b}: r={sign}{p['r']} ({p['strength']}, {p['n']}d)")

    ins = an.insights(df)
    if ins:
        lines.append("Insights:")
        for i in ins[:5]:
            lines.append(f"  - {i}")

    return "\n".join(lines)
