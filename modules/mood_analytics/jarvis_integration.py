"""
Інтеграція настрою з агентом JARVIS.
Тули, які викликає LLM: log_mood (запис) і mood_report (аналітика).
Telegram-доставка — через callback, який реєструє main.py (як у health/money).
"""
from . import parser, analysis, report, visualizer

# Telegram callbacks реєструються ззовні (main.py), щоб уникнути циклічних імпортів.
_notify_text = None   # fn(text)
_notify_photo = None  # fn(photo_path, caption)


def register_telegram(notify_text=None, notify_photo=None):
    """main.py викликає це після ініціалізації Telegram."""
    global _notify_text, _notify_photo
    _notify_text = notify_text
    _notify_photo = notify_photo
    print("[MOOD] Telegram доставку підключено")


def log_mood_tool(score: int, tags: str = "", note: str = "", source: str = "voice") -> str:
    """
    Записує настрій. Викликається agent-тулом log_mood та Telegram callback'ом.
    Повертає короткий статус для голосу/тексту.
    """
    try:
        parser.add_entry(score=score, tags=tags, note=note, source=source)
    except Exception as e:
        return f"Sir, I couldn't log your mood: {e}"
    df = parser.filter_period(parser.load_df(), "week")
    return report.short_status(df)


def mood_report_tool(period: str = "week", send_telegram: bool = False) -> str:
    """
    Будує текстовий звіт настрою. Опційно шле дашборд у Telegram.
    """
    df_all = parser.load_df()
    df = parser.filter_period(df_all, period)
    text = report.build_report(df, period)

    if send_telegram:
        try:
            img = visualizer.dashboard(df)
            if _notify_photo:
                _notify_photo(img, text)
            elif _notify_text:
                _notify_text(text)
            else:
                return text + " (Telegram delivery not configured, Sir.)"
            return f"Mood report for {period} sent to your Telegram, Sir."
        except Exception as e:
            return f"Sir, report built but Telegram delivery failed: {e}"

    return text


def get_summary(period: str = "week") -> dict:
    """Для HUD-ендпоінтів — сирі цифри без форматування."""
    df = parser.filter_period(parser.load_df(), period)
    return analysis.summary_stats(df)
