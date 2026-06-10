"""
workout_visualizer.py — рендер мʼязової мапи у PNG для Telegram-звіту.

БЕЗ cairosvg (на Windows немає libcairo). Використовує matplotlib + svgpath2mpl
+ Pillow — усе pure-python / вже є в проєкті (money/health на matplotlib).

Дані беруться з mapdata.json (path + transform кожної зони, фон-контур base64),
згенерованого з muscle_map.svg. Рендерить FRONT і BACK поруч у PNG.
"""

import io
import re
import json
import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# дані мапи (path/transform/фон) — лежать поряд із SVG в hud_assets
MAPDATA_PATH = Path(__file__).resolve().parent / "hud_assets" / "mapdata.json"

STATE_COLORS = {
    "fresh": "#00e676",
    "mid":   "#ffd400",
    "old":   "#ff3d3d",
}
BASE_FILL = "#1a2730"
BG = "#050b14"


def _apply_transform(verts, transform: str):
    """Застосовує potrace-трансформацію translate(tx,ty) scale(sx,sy) до вершин."""
    m = re.search(r'translate\(([\d.-]+),([\d.-]+)\)\s*scale\(([\d.-]+),([\d.-]+)\)',
                  transform)
    if not m:
        return verts
    tx, ty, sx, sy = map(float, m.groups())
    out = verts.copy()
    out[:, 0] = verts[:, 0] * sx + tx
    out[:, 1] = verts[:, 1] * sy + ty
    return out


def _render_layer(ax, layer: dict, muscle_map: dict):
    """Малює один шар (front/back) на осі ax: фон-контур + кольорові зони."""
    import numpy as np
    from matplotlib.path import Path as MplPath
    from matplotlib.patches import PathPatch
    from svgpath2mpl import parse_path

    vb = layer["viewBox"].split()
    vbw, vbh = float(vb[2]), float(vb[3])

    # фон-контур (base64 PNG)
    if layer.get("bg"):
        b64 = layer["bg"].split(",", 1)[1]
        from PIL import Image
        im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        ax.imshow(np.asarray(im), extent=[0, vbw, vbh, 0], aspect="auto", zorder=0)

    # кольорові зони
    for gid, g in layer["groups"].items():
        info = muscle_map.get(gid, {})
        state = info.get("state", "none")
        if state not in STATE_COLORS:
            continue  # незамальовані пропускаємо
        color = STATE_COLORS[state]
        for d in g["paths"]:
            mp = parse_path(d)
            verts = _apply_transform(mp.vertices, g["transform"])
            ax.add_patch(PathPatch(MplPath(verts, mp.codes), facecolor=color,
                                   edgecolor="none", alpha=0.85, zorder=2))

    ax.set_xlim(0, vbw)
    ax.set_ylim(vbh, 0)
    ax.axis("off")


def render_map_png(muscle_map: dict, mapdata_path=None) -> bytes:
    """Рендерить FRONT+BACK мапу у PNG (поруч), зони за станом. matplotlib, без cairo."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mp_path = Path(mapdata_path) if mapdata_path else MAPDATA_PATH
    if not mp_path.exists():
        raise FileNotFoundError(f"mapdata.json не знайдено: {mp_path}")

    data = json.loads(mp_path.read_text(encoding="utf-8"))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 7))
    fig.patch.set_facecolor(BG)
    _render_layer(ax1, data["front"], muscle_map)
    _render_layer(ax2, data["back"], muscle_map)
    ax1.set_title("FRONT", color="#00d4ff", fontsize=14, fontweight="bold")
    ax2.set_title("BACK", color="#00d4ff", fontsize=14, fontweight="bold")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()