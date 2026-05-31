"""
correlation_analytics — крос-кореляційний аналіз JARVIS.
Зводить sleep × steps × resting HR × mood × spending у єдину денну таблицю,
рахує кореляції, лагові ефекти і генерує висновки/рекомендації.

Патерн ідентичний health/money/mood:
  data_merge        — зведення денних рядів з усіх модулів
  analysis          — кореляційна матриця, лаги, insights
  visualizer        — heatmap, scatter, timeline, dashboard PNG
  report            — текстовий звіт (non-markdown)
  jarvis_integration— тул + HUD-функції + Telegram
  hud_endpoints     — Flask-роути /correlation/*
"""
from .jarvis_integration import (
    cross_correlation_report_tool,
    register_telegram,
    get_summary,
    invalidate_cache,
)

__all__ = [
    "cross_correlation_report_tool",
    "register_telegram",
    "get_summary",
    "invalidate_cache",
]
