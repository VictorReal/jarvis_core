"""
jarvis_integration.py — інтеграція cros-correlation з JARVIS.
Тул cross_correlation_report + HUD-функції + Telegram-доставка.
"""
import time as _time
import logging
import pandas as pd

from . import data_merge as dm
from . import analysis as an
from . import visualizer as viz
from . import report as rep

logger = logging.getLogger(__name__)

# Telegram доставка реєструється ззовні (main.py), як у mood.
_notify_text = None
_notify_photo = None

_cache = {"df": None, "loaded_at": 0}
_CACHE_TTL = 300


def register_telegram(notify_text=None, notify_photo=None):
    global _notify_text, _notify_photo
    _notify_text = notify_text
    _notify_photo = notify_photo
    print("[CORR] Telegram доставку підключено")


def _cached_matrix() -> pd.DataFrame:
    now = _time.time()
    if _cache["df"] is not None and (now - _cache["loaded_at"]) < _CACHE_TTL:
        return _cache["df"]
    _cache["df"] = dm.build_daily_matrix()
    _cache["loaded_at"] = now
    return _cache["df"]


def invalidate_cache():
    _cache["df"] = None
    _cache["loaded_at"] = 0


# ---------------------------------------------------------------- LLM tool
def cross_correlation_report_tool(send_telegram: bool = False) -> str:
    """Аналізує зв'язки між сном, активністю, настроєм і витратами."""
    df = _cached_matrix()
    text = rep.build_report(df)
    if send_telegram:
        try:
            img = viz.plot_dashboard(df)
            if _notify_photo:
                _notify_photo_bytes(img, text)
            elif _notify_text:
                _notify_text(text)
            else:
                return text + " (Telegram delivery not configured, Sir.)"
            return "Cross-correlation report sent to your Telegram, Sir."
        except Exception as e:
            return f"Sir, report built but Telegram delivery failed: {e}"
    return text


def _notify_photo_bytes(img_bytes: bytes, caption: str):
    """Зберігає PNG тимчасово і шле через notify_photo(path, caption)."""
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), "corr_dashboard.png")
    with open(path, "wb") as f:
        f.write(img_bytes)
    _notify_photo(path, caption[:1024])


# ---------------------------------------------------------------- HUD
def get_summary() -> dict:
    df = _cached_matrix()
    s = an.summary(df)
    s["insights"] = an.insights(df) if s.get("available") else []
    return s


def render_chart(panel: str) -> bytes:
    df = _cached_matrix()
    if panel == "matrix":
        return viz.plot_matrix(df)
    if panel == "timeline":
        return viz.plot_timeline(df)
    if panel == "dashboard":
        return viz.plot_dashboard(df)
    if panel.startswith("scatter:"):
        # формат scatter:a,b
        try:
            _, pairs = panel.split(":")
            a, b = pairs.split(",")
            return viz.plot_scatter(df, a, b)
        except Exception:
            pass
    # дефолт — найсильніша пара
    pairs = an.strongest_pairs(df, top=1)
    if pairs:
        return viz.plot_scatter(df, pairs[0]["a"], pairs[0]["b"])
    return viz.plot_matrix(df)
