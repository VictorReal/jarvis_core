"""
workout_endpoints.py — Flask-роути HUD для мʼязової мапи.

Патерн такий самий, як у health_analytics/money_analytics:
  • register_workout_routes(app) вішає роути на наявний Flask-app HUD;
  • дані бере з WorkoutModule (singleton get_workout) — окремий інстанс
    не створюється, main.py чіпати не треба;
  • HUD-фронт (hud_script.js) фетчить /api/workout/map і малює мапу.

Роути:
  GET  /api/workout/map      → {ok, map:{group:{hours,state}}, summary}
  POST /api/workout/log      → залогувати тренування (body: {"exercise": "..."} )
  POST /api/workout/telegram → надіслати підсумок у Telegram (опційно)
"""

import logging
from flask import jsonify, request

logger = logging.getLogger(__name__)


def register_workout_routes(app):
    """Реєструє роути мʼязової мапи на переданому Flask-app."""

    @app.route("/api/workout/map")
    def _workout_map():
        # Повертає поточний стан усіх груп (колір рахується в модулі за 24/48/72).
        try:
            from modules.workout_module import get_workout
            w = get_workout()
            return jsonify({
                "ok": True,
                "map": w.get_muscle_map(),
                "summary": w.get_summary(),
            })
        except Exception as e:
            logger.warning(f"[WORKOUT] map endpoint error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/workout/log", methods=["POST"])
    def _workout_log():
        # Лог тренування з HUD (натуральна мова: "груди і трицепс").
        try:
            from modules.workout_module import get_workout
            data = request.get_json(force=True, silent=True) or {}
            exercise = (data.get("exercise") or "").strip()
            if not exercise:
                return jsonify({"ok": False, "error": "empty exercise"}), 400
            w = get_workout()
            msg = w.log_workout(exercise)
            return jsonify({"ok": True, "message": msg, "map": w.get_muscle_map()})
        except Exception as e:
            logger.warning(f"[WORKOUT] log endpoint error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/workout/telegram", methods=["POST"])
    def _workout_telegram():
        # Надсилає короткий підсумок у Telegram (тим самим Bot-патерном, що health/money).
        try:
            from modules.workout_module import get_workout
            w = get_workout()
            summary = w.get_summary()
            sent = _send_telegram(summary)
            return jsonify({"ok": sent, "summary": summary})
        except Exception as e:
            logger.warning(f"[WORKOUT] telegram endpoint error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    logger.info("[WORKOUT] HUD-роути зареєстровані")


def _send_telegram(text: str) -> bool:
    """Надсилає текст власнику в Telegram. Бере токен/chat_id з .env
    (як money/health notify_owner). Якщо не налаштовано — тихо False."""
    try:
        import os
        token = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_OWNER_ID") or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.warning("[WORKOUT] Telegram не налаштований (.env)")
            return False
        from telegram import Bot
        Bot(token).send_message(chat_id=chat_id, text=f"🏋️ {text}")
        return True
    except Exception as e:
        logger.warning(f"[WORKOUT] Telegram send error: {e}")
        return False
