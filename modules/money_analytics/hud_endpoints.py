"""
hud_endpoints.py — Flask Blueprint з money-routes для HUD.

Реєстрація в hud_module.py:
    from modules.money_analytics.hud_endpoints import register_money_routes
    register_money_routes(app)
"""

import logging
from flask import Blueprint, jsonify, request, Response

from .jarvis_integration import (
    today_summary,
    get_summary_dict,
    get_insights,
    render_panel_png,
    money_report_tool,
    invalidate_cache,
)

logger = logging.getLogger(__name__)

money_bp = Blueprint("money", __name__, url_prefix="/money")


@money_bp.route("/today")
def money_today():
    """Мінізведення для HUD-мініпанелі."""
    return jsonify(today_summary())


@money_bp.route("/insights")
def money_insights():
    period = request.args.get("period", "month")
    return jsonify(get_insights(period=period))


@money_bp.route("/summary")
def money_summary():
    period = request.args.get("period", "month")
    return jsonify(get_summary_dict(period=period))


@money_bp.route("/chart")
def money_chart():
    panel = request.args.get("panel", "dashboard")
    period = request.args.get("period", "month")
    try:
        png = render_panel_png(panel, period)
        return Response(png, mimetype="image/png")
    except FileNotFoundError:
        return ("Money Manager export not found.", 404)
    except ValueError as e:
        return (str(e), 400)
    except Exception as e:
        logger.exception("[MONEY HUD] chart fail")
        return (f"Render error: {e}", 500)


@money_bp.route("/telegram", methods=["POST"])
def money_send_telegram():
    period = request.json.get("period", "month") if request.is_json else "month"
    try:
        text = money_report_tool(period=period, send_telegram=True)
        return jsonify({"ok": True, "preview": text[:300]})
    except Exception as e:
        logger.exception("[MONEY HUD] telegram fail")
        return jsonify({"ok": False, "error": str(e)}), 500


@money_bp.route("/refresh", methods=["POST"])
def money_refresh():
    invalidate_cache()
    return jsonify({"ok": True})


def register_money_routes(app):
    app.register_blueprint(money_bp)
    logger.info("[MONEY HUD] Routes registered: /money/today, /summary, /chart, /telegram, /refresh")
