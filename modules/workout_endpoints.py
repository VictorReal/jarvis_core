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
        # Надсилає детальний підсумок + PNG мапи у Telegram (money-патерн).
        try:
            from modules.workout_module import get_workout
            w = get_workout()
            text = w.get_telegram_report()
            # рендеримо PNG мапи (front+back з кольорами станів)
            png_bytes = None
            try:
                from modules.workout_visualizer import render_map_png
                png_bytes = render_map_png(w.get_muscle_map())
                logger.info(f"[WORKOUT] PNG згенеровано ({len(png_bytes)} байт)")
            except Exception as e:
                import traceback
                logger.warning(f"[WORKOUT] PNG render error: {e}\n{traceback.format_exc()}")
            sent = _send_telegram(text, png_bytes)
            return jsonify({"ok": sent, "summary": text})
        except Exception as e:
            logger.warning(f"[WORKOUT] telegram endpoint error: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500

    logger.info("[WORKOUT] HUD-роути зареєстровані")


def _send_telegram(text: str, png_bytes: bytes = None) -> bool:
    """Надсилає текст (+опційно PNG) власнику в Telegram.
    Патерн money: TELEGRAM_TOKEN + TELEGRAM_USER_ID, async через Bot."""
    import os
    token = os.getenv("TELEGRAM_TOKEN")
    try:
        user_id = int(os.getenv("TELEGRAM_USER_ID", "0"))
    except ValueError:
        user_id = 0
    if not token or not user_id:
        logger.warning("[WORKOUT] TELEGRAM_TOKEN/USER_ID не задано")
        return False

    import asyncio
    import threading

    async def _send():
        try:
            from telegram import Bot
            bot = Bot(token=token)
            if png_bytes:
                import tempfile, os as _os
                tmp = _os.path.join(tempfile.gettempdir(), "workout_map.png")
                with open(tmp, "wb") as f:
                    f.write(png_bytes)
                with open(tmp, "rb") as photo:
                    await bot.send_photo(chat_id=user_id, photo=photo,
                                         caption="🏋️ Workout Map")
            # текст окремо (Telegram caption має ліміт 1024)
            for i in range(0, len(text), 4000):
                await bot.send_message(chat_id=user_id, text=text[i:i + 4000])
            logger.info("[WORKOUT] Telegram надіслано")
        except Exception as e:
            logger.error(f"[WORKOUT] Telegram error: {e}")

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send())
        loop.close()

    threading.Thread(target=_run, daemon=True).start()
    return True