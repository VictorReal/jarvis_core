"""
HUD-ендпоінти настрою.
register_mood_routes(app) — реєструється з hud_module.py (як health/money).
Роути: /mood/today, /mood/summary, /mood/log, /mood/chart/<name>,
       /mood/refresh, /mood/telegram, /mood/tags
"""
import os

from flask import jsonify, request, send_file

from . import parser, analysis, visualizer, report, jarvis_integration
from .constants import MOOD_TAGS, CACHE_DIR


def register_mood_routes(app):

    @app.route("/mood/today")
    def mood_today():
        """Дані для міні-панелі: останній запис + сьогоднішнє середнє."""
        df = parser.load_df()
        today = parser.filter_period(df, "today")
        stats = analysis.summary_stats(df if today.empty else today)
        return jsonify({
            "latest":      stats["latest"],
            "latest_tags": stats["latest_tags"],
            "avg":         stats["avg"],
            "count":       stats["count"],
            "trend":       stats["trend"],
            "days_logged": stats["days_logged"],
        })

    @app.route("/mood/summary")
    def mood_summary():
        """Повна статистика за період — для модалу."""
        period = request.args.get("period", "week")
        df = parser.filter_period(parser.load_df(), period)
        stats = analysis.summary_stats(df)
        mve = analysis.morning_vs_evening(df)
        return jsonify({
            "stats": stats,
            "morning_vs_evening": mve,
            "text": report.build_report(df, period),
        })

    @app.route("/mood/insights")
    def mood_insights():
        """Рекомендації для HUD-блоку висновків."""
        period = request.args.get("period", "month")
        df = parser.filter_period(parser.load_df(), period)
        return jsonify({"insights": report.insights(df)})

    @app.route("/mood/tags")
    def mood_tags():
        """Канонічний список тегів — щоб HUD будував кнопки динамічно."""
        return jsonify({"tags": MOOD_TAGS})

    @app.route("/mood/log", methods=["POST"])
    def mood_log():
        """Запис настрою з HUD-кнопки/форми."""
        data = request.get_json(silent=True) or {}
        score = data.get("score")
        if score is None:
            return jsonify({"ok": False, "error": "score required"}), 400
        tags = data.get("tags", "")
        note = data.get("note", "")
        status = jarvis_integration.log_mood_tool(
            score=score, tags=tags, note=note, source="hud"
        )
        return jsonify({"ok": True, "status": status})

    @app.route("/mood/chart/<name>")
    def mood_chart(name):
        """Віддає PNG-чарт. Генерує свіжий за поточний період (week)."""
        period = request.args.get("period", "week")
        df = parser.filter_period(parser.load_df(), period)
        builders = {
            "trend":        visualizer.chart_trend,
            "tags":         visualizer.chart_tags,
            "distribution": visualizer.chart_distribution,
            "hourly":       visualizer.chart_hourly,
            "dashboard":    visualizer.dashboard,
        }
        if name not in builders:
            return jsonify({"error": "unknown chart"}), 404
        path = builders[name](df, f"mood_{name}.png")
        return send_file(os.path.abspath(path), mimetype="image/png")

    @app.route("/mood/refresh", methods=["POST"])
    def mood_refresh():
        """Чистить кеш чартів — наступний запит згенерує свіжі."""
        try:
            if os.path.isdir(CACHE_DIR):
                for f in os.listdir(CACHE_DIR):
                    if f.endswith(".png"):
                        os.remove(os.path.join(CACHE_DIR, f))
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/mood/telegram", methods=["POST"])
    def mood_telegram():
        """Шле звіт+дашборд у Telegram."""
        period = (request.get_json(silent=True) or {}).get("period", "week")
        msg = jarvis_integration.mood_report_tool(period=period, send_telegram=True)
        return jsonify({"ok": True, "status": msg})

    print("[HUD] Mood routes зареєстровано")
