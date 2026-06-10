"""
armor_endpoints.py — Flask-роути HUD для трекера збірки броні.

register_armor_routes(app) — викликати з hud_module.py.
Роути:
  GET  /api/armor/map      — {part_id: status} усіх деталей + прогрес
  POST /api/armor/cycle    — циклічно змінити статус деталі (body: {part_id})
  GET  /api/armor/progress — {percent, done, printing, total}
"""

import logging
from flask import jsonify, request

logger = logging.getLogger(__name__)


def register_armor_routes(app):

    @app.route("/api/armor/map")
    def _armor_map():
        from modules.armor_module import get_armor, CANON_COLORS
        a = get_armor()
        return jsonify({
            "map": a.get_armor_map(),
            "colors": CANON_COLORS,
            "progress": a.progress(),
        })

    @app.route("/api/armor/cycle", methods=["POST"])
    def _armor_cycle():
        from modules.armor_module import get_armor
        data = request.get_json(silent=True) or {}
        part_id = data.get("part_id", "")
        if not part_id:
            return jsonify({"ok": False, "error": "no part_id"}), 400
        a = get_armor()
        new_status = a.cycle_status(part_id)
        return jsonify({"ok": True, "part_id": part_id,
                        "status": new_status, "progress": a.progress()})

    @app.route("/api/armor/progress")
    def _armor_progress():
        from modules.armor_module import get_armor
        return jsonify(get_armor().progress())

    print("[ARMOR] HUD-роути зареєстровані")
