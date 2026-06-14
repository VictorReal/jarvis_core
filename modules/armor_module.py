"""
armor_module.py — трекер збірки Iron Man броні для JARVIS HUD.

Кожна деталь броні друкується на 3D-принтері. Статус деталі:
  • not_printed — ще не надруковано (на HUD лише контур, без заливки)
  • printing    — друкується (напівпрозорий колір + пульсація)
  • done        — готово (повний канонічний колір)

Дані статусів зберігаються в data/armor_status.json (переживають перезапуск).
Геометрія деталей (paths/transform/колір) — у modules/hud_assets/armor_map.svg
та armor_parts.json (id, color, electro).

Electro-деталі (arc_reactor, eyes) — завжди світні, не мають статусу
і не рахуються у % готовності (це електроніка, не друк).

Канонічна палітра (приглушена, Mark): bordo / dark gold / dark silver.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATUS_FILE = Path("data/armor_status.json")
PARTS_FILE = Path(__file__).resolve().parent / "hud_assets" / "armor_parts.json"

# канонічні кольори (приглушені)
CANON_COLORS = {
    "gold":   "#b8923a",
    "red":    "#8b1a1a",
    "silver": "#8a9099",
    "arc":    "#7fdfff",
}

STATUSES = ["not_printed", "printing", "done"]

# Англ-назви деталей → id (для голосу/тексту: "armor chest done").
# Ключі — слова, які може сказати користувач; значення — точний id або префікс.
NAME_ALIASES = {
    "helmet": ["helmet_top", "helmet_faceplate", "helmet_chin"],
    "faceplate": ["helmet_faceplate"],
    "chin": ["helmet_chin"],
    "neck": ["neck"],
    "chest": ["chest"],
    "abs": ["abs"],
    "cod": ["cod"],
    "pelvis": ["cod", "upperthigh"],
    "upper thigh": ["upperthigh"],
    "shoulders": ["left_shoulder", "right_shoulder"],
    "left shoulder": ["left_shoulder"],
    "right shoulder": ["right_shoulder"],
    "arms": ["left_arm", "right_arm"],
    "hands": ["left_arm", "right_arm", "left_biceps", "right_biceps",
              "left_triceps", "right_triceps", "left_forearm", "right_forearm"],
    "left arm": ["left_arm"],
    "right arm": ["right_arm"],
    "biceps": ["left_biceps", "right_biceps"],
    "triceps": ["left_triceps", "right_triceps"],
    "forearms": ["left_forearm", "right_forearm"],
    "left forearm": ["left_forearm"],
    "right forearm": ["right_forearm"],
    "thighs": ["left_thigh", "right_thigh"],
    "left thigh": ["left_thigh"],
    "right thigh": ["right_thigh"],
    "knees": ["left_knee", "right_knee"],
    "shins": ["left_shin", "right_shin"],
    "feet": ["left_foot", "right_foot"],
    "left foot": ["left_foot"],
    "right foot": ["right_foot"],
    "upperback": ["left_upperback", "right_upperback"],
    "elbows": ["left_elbow", "right_elbow"],
    "left elbow": ["left_elbow"],
    "right elbow": ["right_elbow"],
    "back": ["back"],
    "upper back": ["back", "left_upperback", "right_upperback"],
    "mid back": ["midback"],
    "midback": ["midback"],
    "lower back": ["lowback"],
    "lowback": ["lowback"],
    "лікті": ["left_elbow", "right_elbow"],
    "спина": ["back", "midback", "lowback"],
    "лопатки": ["midback"],
    "поперек": ["lowback"],
    "legs": ["left_thigh", "right_thigh", "left_knee", "right_knee",
             "left_shin", "right_shin", "left_foot", "right_foot"],
    # українські назви (для зручності — команди можуть бути й укр)
    "шолом": ["helmet_top", "helmet_faceplate", "helmet_chin"],
    "шия": ["neck"],
    "груди": ["chest"],
    "прес": ["abs"],
    "плечі": ["left_shoulder", "right_shoulder"],
    "руки": ["left_arm", "right_arm"],
    "біцепс": ["left_biceps", "right_biceps"],
    "біцепси": ["left_biceps", "right_biceps"],
    "трицепс": ["left_triceps", "right_triceps"],
    "трицепси": ["left_triceps", "right_triceps"],
    "передпліччя": ["left_forearm", "right_forearm"],
    "стегна": ["left_thigh", "right_thigh"],
    "коліна": ["left_knee", "right_knee"],
    "гомілки": ["left_shin", "right_shin"],
    "ступні": ["left_foot", "right_foot"],
    "ноги": ["left_thigh", "right_thigh", "left_knee", "right_knee",
             "left_shin", "right_shin", "left_foot", "right_foot"],
}


class ArmorModule:
    def __init__(self):
        self._parts = None  # кеш списку деталей

    # ----------------------------------------------------------------- #
    #  Деталі (геометрія + метадані)
    # ----------------------------------------------------------------- #
    def _load_parts(self) -> list:
        if self._parts is not None:
            return self._parts
        try:
            self._parts = json.loads(PARTS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[ARMOR] parts load error: {e}")
            self._parts = []
        return self._parts

    def _printable_ids(self) -> list:
        """id деталей, що друкуються (без electro)."""
        return [p["id"] for p in self._load_parts() if not p.get("electro")]

    # ----------------------------------------------------------------- #
    #  Статуси (persistence)
    # ----------------------------------------------------------------- #
    def _load_status(self) -> dict:
        try:
            if STATUS_FILE.exists():
                return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[ARMOR] status load error: {e}")
        return {}

    def _save_status(self, status: dict):
        try:
            STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        except Exception as e:
            logger.warning(f"[ARMOR] status save error: {e}")

    def get_status(self, part_id: str) -> str:
        return self._load_status().get(part_id, "not_printed")

    def set_status(self, part_id: str, status: str) -> bool:
        if status not in STATUSES:
            return False
        st = self._load_status()
        st[part_id] = status
        self._save_status(st)
        return True

    def cycle_status(self, part_id: str) -> str:
        """Циклічно: not_printed → printing → done → not_printed. Повертає новий."""
        cur = self.get_status(part_id)
        nxt = STATUSES[(STATUSES.index(cur) + 1) % len(STATUSES)]
        self.set_status(part_id, nxt)
        return nxt

    # ----------------------------------------------------------------- #
    #  Команди голосом/текстом
    # ----------------------------------------------------------------- #
    def resolve_parts(self, name: str) -> list:
        """Англ-назва → список id деталей. 'helmet'→3 деталі, 'chest'→1 тощо."""
        n = name.lower().strip()
        if n in NAME_ALIASES:
            return NAME_ALIASES[n]
        # частковий збіг по id
        ids = self._printable_ids()
        hits = [i for i in ids if n.replace(" ", "_") in i]
        return hits

    def command(self, part_name: str, status: str) -> str:
        """Встановити статус групі деталей. Напр. command('chest','done')."""
        status = status.lower().strip().replace(" ", "_")
        # синоніми статусів
        smap = {
            "done": "done", "ready": "done", "finished": "done", "complete": "done",
            "printing": "printing", "in_progress": "printing", "printing_now": "printing",
            "not_printed": "not_printed", "todo": "not_printed", "pending": "not_printed",
            "reset": "not_printed", "not_done": "not_printed",
        }
        status = smap.get(status, status)
        if status not in STATUSES:
            return f"Unknown status '{status}', Sir. Use: not_printed, printing, done."

        ids = self.resolve_parts(part_name)
        if not ids:
            return f"Sir, I don't recognize armor part '{part_name}'."
        for pid in ids:
            self.set_status(pid, status)
        nice = status.replace("_", " ")
        return f"Armor: {part_name} set to {nice}, Sir. ({len(ids)} part(s))"

    # ----------------------------------------------------------------- #
    #  Дані для HUD + прогрес
    # ----------------------------------------------------------------- #
    def get_armor_map(self) -> dict:
        """{part_id: status} для всіх деталей (electro → 'electro')."""
        out = {}
        st = self._load_status()
        for p in self._load_parts():
            if p.get("electro"):
                out[p["id"]] = "electro"
            else:
                out[p["id"]] = st.get(p["id"], "not_printed")
        return out

    def progress(self) -> dict:
        """% готовності: done / усі друковані × 100."""
        ids = self._printable_ids()
        if not ids:
            return {"percent": 0, "done": 0, "printing": 0, "total": 0}
        st = self._load_status()
        done = sum(1 for i in ids if st.get(i) == "done")
        printing = sum(1 for i in ids if st.get(i) == "printing")
        return {
            "percent": round(done / len(ids) * 100),
            "done": done,
            "printing": printing,
            "total": len(ids),
        }

    def get_summary(self) -> str:
        """Короткий підсумок для голосу/Telegram/розмов JARVIS."""
        p = self.progress()
        if p["total"] == 0:
            return "Armor build data is not loaded yet, Sir."
        msg = (f"Mark suit build is {p['percent']}% complete, Sir — "
               f"{p['done']} of {p['total']} parts printed")
        if p["printing"]:
            msg += f", {p['printing']} currently printing"
        return msg + "."


_armor_instance = None

def get_armor() -> "ArmorModule":
    global _armor_instance
    if _armor_instance is None:
        _armor_instance = ArmorModule()
    return _armor_instance