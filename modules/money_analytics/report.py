"""
report.py — текстові звіти Money Manager для голосу/Telegram.
"""


def money_report(summary: dict, needs_wants: dict | None = None,
                 budget: dict | None = None) -> str:
    """Підсумок витрат — стислий звіт без markdown."""
    if summary.get("transactions", 0) == 0:
        return "💰 Finance: no data for this period."

    cur = summary.get("currency", "UAH")
    net = summary["net"]
    net_sign = "+" if net >= 0 else ""
    savings = summary.get("savings_rate")
    savings_emoji = "✅" if savings and savings > 10 else ("⚠️" if savings and savings < 0 else "•")

    lines = [
        f"💰 FINANCE — {summary['period'].upper()}",
        f"Period: {summary['from']} → {summary['to']} ({summary['days']} days)",
        f"Earned: {summary['total_earned']:,.0f} {cur} ({summary['income_count']} transactions)",
        f"Spent:  {summary['total_spent']:,.0f} {cur} ({summary['expenses_count']} transactions)",
        f"{savings_emoji} Net: {net_sign}{net:,.0f} {cur}" +
            (f" (savings rate {savings:+.1f}%)" if savings is not None else ""),
        f"Daily avg spend: {summary['daily_avg_spend']:,.0f} {cur}",
        f"Biggest expense: {summary['biggest_expense']:,.0f} {cur} ({summary['biggest_expense_category']})",
    ]

    if summary.get("top_categories"):
        lines.append("Top 5 categories:")
        for cat, amt in summary["top_categories"].items():
            lines.append(f"  • {cat}: {amt:,.0f} {cur}")

    if needs_wants and sum([needs_wants.get(k, 0) for k in ["needs", "wants", "other"]]) > 0:
        lines.append(
            f"Needs/Wants split: {needs_wants['needs_pct']}% / "
            f"{needs_wants['wants_pct']}% / {needs_wants['other_pct']}% other"
        )

    # 50/30/20 compliance
    if budget and budget.get("available"):
        n_ok = "✅" if budget["needs_ok"] else "❌"
        w_ok = "✅" if budget["wants_ok"] else "❌"
        s_ok = "✅" if budget["savings_ok"] else "❌"
        lines.append("")
        lines.append("📐 50/30/20 RULE")
        lines.append(f"  Daily budget: {budget['daily_budget']:,.0f} {cur}")
        lines.append(f"  {n_ok} Needs:   {budget['actual_needs']:,.0f}/{budget['target_needs']:,.0f} ({budget['needs_used_pct']:.0f}% of target)")
        lines.append(f"  {w_ok} Wants:   {budget['actual_wants']:,.0f}/{budget['target_wants']:,.0f} ({budget['wants_used_pct']:.0f}% of target)")
        lines.append(f"  {s_ok} Savings: {budget['actual_savings']:,.0f}/{budget['target_savings']:,.0f} ({budget['savings_done_pct']:.0f}% of target)")
        if not budget["overall_ok"]:
            advice = []
            if not budget["wants_ok"]:
                overspend = budget["actual_wants"] - budget["target_wants"]
                advice.append(f"cut wants by {overspend:,.0f} {cur}")
            if not budget["needs_ok"]:
                overspend = budget["actual_needs"] - budget["target_needs"]
                advice.append(f"reduce needs by {overspend:,.0f} {cur}")
            if advice:
                lines.append(f"  💡 To balance: {'; '.join(advice)}")

    return "\n".join(lines)


def insights(summary_dict: dict, budget: dict | None = None) -> list[str]:
    """
    Короткі рекомендації для HUD-блоку висновків.
    summary_dict — результат analysis.summary; budget — analysis.budget_503020 (опційно).
    """
    out = []
    if not summary_dict or summary_dict.get("days", summary_dict.get("expenses_count", 0)) == 0:
        return ["Not enough financial data yet, Sir."]

    net = summary_dict.get("net")
    sr = summary_dict.get("savings_rate")
    cur = summary_dict.get("currency", "")

    if net is not None:
        if net < 0:
            out.append(f"You're spending more than you earn (net {net:,.0f} {cur}). Trim discretionary costs.")
        else:
            out.append(f"Positive balance this period (+{net:,.0f} {cur}). Good.")

    if sr is not None:
        if sr < 20:
            out.append(f"Savings rate {sr:.0f}% is below the 20% target — automate a transfer on payday.")
        else:
            out.append(f"Savings rate {sr:.0f}% meets the 20% goal.")

    if budget and budget.get("available"):
        if not budget["wants_ok"]:
            over = budget["actual_wants"] - budget["target_wants"]
            pct = budget["wants_used_pct"]
            out.append(f"Wants are {pct:.0f}% of the limit (~{over:,.0f} {cur} over) — cut non-essentials.")
        if not budget["needs_ok"]:
            over = budget["actual_needs"] - budget["target_needs"]
            out.append(f"Needs exceed 50% of income by {over:,.0f} {cur} — fixed costs are high.")
        if budget["savings_ok"] and budget["wants_ok"] and budget["needs_ok"]:
            out.append("You're within all 50/30/20 targets. Well managed, Sir.")

    return out or ["Spending looks balanced this period, Sir."]
