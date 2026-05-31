"""
hud_endpoints.py — Flask-роути крос-кореляції для HUD.
register_correlation_routes(app) — викликати з hud_module.py.
"""
import logging
from flask import jsonify, request, Response

from . import jarvis_integration as ji

logger = logging.getLogger(__name__)


def register_correlation_routes(app):

    @app.route("/correlation/summary")
    def correlation_summary():
        return jsonify(ji.get_summary())

    @app.route("/correlation/chart")
    def correlation_chart():
        panel = request.args.get("panel", "matrix")
        try:
            png = ji.render_chart(panel)
            return Response(png, mimetype="image/png")
        except Exception as e:
            logger.exception("[CORR HUD] chart failed")
            return (f"Render error: {e}", 500)

    @app.route("/correlation/refresh", methods=["POST"])
    def correlation_refresh():
        ji.invalidate_cache()
        return jsonify({"ok": True})

    @app.route("/correlation/telegram", methods=["POST"])
    def correlation_telegram():
        msg = ji.cross_correlation_report_tool(send_telegram=True)
        return jsonify({"ok": True, "status": msg})

    print("[HUD] Correlation routes зареєстровано")
