"""
day_logger.py — Логування дня для JARVIS
Зберігає команди і відповіді в logs/YYYY-MM-DD.md
Джарвіс може прочитати і підсумувати через get_today_log()
"""

import os
import threading
from datetime import datetime
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs"
_lock = threading.Lock()


def _log_path(date: datetime = None) -> Path:
    d = date or datetime.now()
    return LOGS_DIR / f"{d.strftime('%Y-%m-%d')}.md"


def log_exchange(user_text: str, jarvis_text: str):
    """Записує одну пару запит/відповідь у файл поточного дня."""
    LOGS_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    entry = (
        f"\n### {now.strftime('%H:%M:%S')}\n"
        f"**SIR:** {user_text.strip()}\n"
        f"**JARVIS:** {jarvis_text.strip()}\n"
    )
    with _lock:
        with open(_log_path(now), "a", encoding="utf-8") as f:
            # Заголовок якщо файл новий
            if f.tell() == 0:
                f.write(f"# JARVIS Log — {now.strftime('%A, %d %B %Y')}\n")
            f.write(entry)


def get_today_log() -> str:
    """Повертає весь лог поточного дня як текст (для підсумку через LLM)."""
    path = _log_path()
    if not path.exists():
        return ""
    with _lock:
        return path.read_text(encoding="utf-8")


def get_log_summary_prompt() -> str:
    """Готовий промпт для LLM — підсумувати день."""
    log = get_today_log()
    if not log:
        return ""
    return (
        "Here is today's activity log between Sir and JARVIS.\n"
        "Summarize: what was asked, what was done, any notable patterns. "
        "Be concise, 3-5 sentences, slightly witty.\n\n"
        f"{log}"
    )
