"""
mood_analytics — модуль трекера настрою для JARVIS.

Патерн ідентичний health_analytics / money_analytics:
  parser            — читання/запис data/mood/moods.csv
  analysis          — агрегації, тренди, streak, теги
  visualizer        — matplotlib PNG-чарти + дашборд
  report            — текстові звіти (non-markdown, для Telegram/TTS)
  jarvis_integration— тули log_mood / mood_report для agent.py
  hud_endpoints     — Flask-роути /mood/* для HUD
  constants         — шкала, теги, шляхи, кольори
"""
from .jarvis_integration import (
    log_mood_tool,
    mood_report_tool,
    register_telegram,
    get_summary,
)
from .constants import MOOD_TAGS, SCORE_MIN, SCORE_MAX

__all__ = [
    "log_mood_tool", "mood_report_tool", "register_telegram", "get_summary",
    "MOOD_TAGS", "SCORE_MIN", "SCORE_MAX",
]
