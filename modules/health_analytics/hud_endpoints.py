"""
hud_endpoints.py — Flask Blueprint з health-routes для HUD.

Реєстрація в hud_module.py (один рядок):

    from modules.health_analytics.hud_endpoints import register_health_routes
    register_health_routes(app)
"""

import logging
from flask import Blueprint, jsonify, request, Response

from .jarvis_integration import (
    today_summary,
    get_summary_dict,
    render_panel_png,
    health_report_tool,
    invalidate_cache,
)

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.route("/today")
def health_today():
    """Мінімальне зведення для HUD-мініпанелі (швидке)."""
    return jsonify(today_summary())


@health_bp.route("/summary")
def health_summary():
    """Повне зведення за період → JSON для модалу."""
    period = request.args.get("period", "week")
    return jsonify(get_summary_dict(period=period))


@health_bp.route("/chart")
def health_chart():
    """
    Рендер одного графіка → PNG.
    Query: panel=<name>, period=<today|week|month|year|all>
    """
    panel = request.args.get("panel", "dashboard")
    period = request.args.get("period", "month")
    try:
        png = render_panel_png(panel, period)
        return Response(png, mimetype="image/png")
    except FileNotFoundError:
        return ("Samsung Health export not found.", 404)
    except ValueError as e:
        return (str(e), 400)
    except Exception as e:
        logger.exception("[HEALTH HUD] chart render failed")
        return (f"Render error: {e}", 500)


@health_bp.route("/insights")
def health_insights():
    """Рекомендації для HUD-блоку висновків health-модала."""
    period = request.args.get("period", "week")
    try:
        d = get_summary_dict(period=period)   # уже імпортовано у файлі
    except Exception as e:
        return jsonify({"insights": [f"Health data unavailable: {e}"]})

    if not d.get("available"):
        return jsonify({"insights": ["No health data yet, Sir."]})

    ins = []

    # Сон
    sl = d.get("sleep") or {}
    if sl.get("nights"):
        avg = sl.get("avg_duration_h")
        if avg is not None:
            if avg < 7:
                ins.append(f"Average sleep {avg:.1f}h is below the 7h target — prioritize earlier nights, Sir.")
            else:
                ins.append(f"Average sleep {avg:.1f}h meets the target.")

    # Кроки
    st = d.get("steps") or {}
    if st.get("days"):
        avg = st.get("avg_steps")
        goal = st.get("goal_met_pct")
        if avg is not None:
            if avg < 8000:
                ins.append(f"Daily steps average {avg:,} — aim to move more.")
            else:
                ins.append(f"Daily steps average {avg:,} — solid activity.")
        if goal is not None and goal < 40:
            ins.append(f"10K goal met only {goal:.0f}% of days — short walks add up.")

    # Resting HR
    hr = d.get("heart_rate") or {}
    if hr.get("resting_avg"):
        ins.append(f"Resting HR around {hr['resting_avg']:.0f} bpm — track the trend over weeks.")

    return jsonify({"insights": ins or ["Health metrics look stable, Sir."]})


@health_bp.route("/telegram", methods=["POST"])
def health_send_telegram():
    """Шле повний звіт + dashboard у Telegram."""
    period = request.json.get("period", "week") if request.is_json else "week"
    try:
        text = health_report_tool(period=period, send_telegram=True)
        return jsonify({"ok": True, "preview": text[:300]})
    except Exception as e:
        logger.exception("[HEALTH HUD] telegram send failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@health_bp.route("/refresh", methods=["POST"])
def health_refresh():
    """Скидає кеш (викликати після нового експорту)."""
    invalidate_cache()
    return jsonify({"ok": True})


def register_health_routes(app):
    """Реєструє Blueprint у Flask app. Викликати один раз з hud_module.py."""
    app.register_blueprint(health_bp)
    logger.info("[HEALTH HUD] Routes registered: /health/today, /summary, /chart, /telegram, /refresh")
