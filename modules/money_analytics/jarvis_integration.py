"""
jarvis_integration.py — точка інтеграції money_analytics з JARVIS.

Tool у brain/agent.py:
    @tool
    def money_report(period: str = "month") -> str:
        from modules.money_analytics.jarvis_integration import money_report_tool
        return money_report_tool(period=period)

    @tool
    def money_report_to_telegram(period: str = "month") -> str:
        from modules.money_analytics.jarvis_integration import money_report_tool
        return money_report_tool(period=period, send_telegram=True)
"""

import os
import time as _time
import logging
import asyncio
import threading
from pathlib import Path
import pandas as pd

from .parser import load_all_files
from . import analysis as ma
from . import visualizer as viz
from . import report as rep
from .constants import DEFAULT_EXPORT_DIR

logger = logging.getLogger(__name__)

DASHBOARD_PATH = Path("data/money_manager/dashboard_latest.png")

# Кеш — щоб HUD не парсив XLSX кожні 2 секунди
_cache = {"df": None, "loaded_at": 0}
_CACHE_TTL = 300  # 5 хв


def _cached_df(export_dir: str | Path = DEFAULT_EXPORT_DIR) -> pd.DataFrame:
    now = _time.time()
    if _cache["df"] is not None and (now - _cache["loaded_at"]) < _CACHE_TTL:
        return _cache["df"]
    _cache["df"] = load_all_files(Path(export_dir))
    _cache["loaded_at"] = now
    return _cache["df"]


def invalidate_cache():
    _cache["df"] = None
    _cache["loaded_at"] = 0


# ---------------------------------------------------------------------------
# LLM TOOL
# ---------------------------------------------------------------------------

def money_report_tool(period: str = "month",
                      send_telegram: bool = False,
                      export_dir: str | Path = DEFAULT_EXPORT_DIR) -> str:
    """
    Аналіз витрат за період. Повертає текстовий звіт (для LLM/голосу).
    """
    try:
        df = _cached_df(export_dir)
    except FileNotFoundError as e:
        return f"Sir, {e}"

    if df.empty:
        return "Sir, Money Manager export not found. Place .xlsx in data/money_manager/."

    summary = ma.summary(df, period)
    needs_wants = ma.needs_vs_wants(df, period)
    budget = ma.budget_503020(df, period)
    text = rep.money_report(summary, needs_wants, budget)

    if send_telegram:
        try:
            png_path = generate_dashboard(df, period=period)
            _send_to_telegram(text, png_path)
        except Exception as e:
            logger.error(f"[MONEY] telegram failed: {e}")

    return text


# ---------------------------------------------------------------------------
# Dashboard (PNG)
# ---------------------------------------------------------------------------

def generate_dashboard(df: pd.DataFrame | None = None,
                       period: str = "month",
                       out_path: Path | str = DASHBOARD_PATH) -> Path:
    if df is None:
        df = _cached_df()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cat_df = ma.by_category(df, period)
    monthly = ma.monthly_trend(df)
    daily = ma.daily_series(df, period)
    budget = ma.budget_503020(df, period)

    viz.plot_dashboard(cat_df, monthly, daily, budget, path=out_path)
    return out_path


# ---------------------------------------------------------------------------
# HUD-специфічні функції
# ---------------------------------------------------------------------------

def today_summary(export_dir: str | Path = DEFAULT_EXPORT_DIR) -> dict:
    """Мінімальне зведення для HUD-мініпанелі."""
    try:
        df = _cached_df(export_dir)
    except FileNotFoundError:
        return {"available": False, "error": "no data folder"}

    if df.empty:
        return {"available": False}

    out = {"available": True}
    today = pd.Timestamp.now().normalize()

    # Today's spending
    today_ex = df[(df["kind"] == "expense") &
                  (df["date"] >= today) &
                  (df["date"] < today + pd.Timedelta(days=1))]
    out["today_spent"] = round(float(today_ex["amount"].sum()), 0) if not today_ex.empty else 0

    # This month
    month_start = today.replace(day=1)
    month_ex = df[(df["kind"] == "expense") & (df["date"] >= month_start)]
    out["month_spent"] = round(float(month_ex["amount"].sum()), 0)

    month_inc = df[(df["kind"] == "income") & (df["date"] >= month_start)]
    out["month_earned"] = round(float(month_inc["amount"].sum()), 0)
    out["month_net"] = round(out["month_earned"] - out["month_spent"], 0)

    # Currency
    out["currency"] = df["currency"].mode().iloc[0] if not df["currency"].mode().empty else "UAH"

    return out


def get_summary_dict(period: str = "month",
                    export_dir: str | Path = DEFAULT_EXPORT_DIR) -> dict:
    """Повний summary для модалу (JSON)."""
    try:
        df = _cached_df(export_dir)
    except FileNotFoundError:
        return {"available": False}
    if df.empty:
        return {"available": False}

    out = {
        "available": True,
        "period": period,
        "summary": ma.summary(df, period),
        "needs_wants": ma.needs_vs_wants(df, period),
        "budget": ma.budget_503020(df, period),
        "top_categories": ma.by_category(df, period).head(10).to_dict("records"),
    }
    return _to_native(out)


def _to_native(obj):
    import numpy as np
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_native(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def render_panel_png(panel: str, period: str = "month",
                     export_dir: str | Path = DEFAULT_EXPORT_DIR) -> bytes:
    """Рендерить один графік за назвою."""
    df = _cached_df(export_dir)

    if panel == "categories":
        cat_df = ma.by_category(df, period)
        return viz.plot_categories_pie(cat_df, title=f"Categories — {period}")

    if panel == "monthly":
        monthly = ma.monthly_trend(df)
        return viz.plot_monthly_trend(monthly)

    if panel == "daily":
        daily = ma.daily_series(df, period)
        budget = ma.budget_503020(df, period)
        daily_budget = budget.get("daily_budget") if budget.get("available") else None
        return viz.plot_daily_spend(daily, title=f"Daily Spending — {period}",
                                    daily_budget=daily_budget)

    if panel == "weekday":
        wd = ma.weekday_pattern(df)
        return viz.plot_weekday(wd)

    if panel == "needs_wants":
        nw = ma.needs_vs_wants(df, period)
        return viz.plot_needs_vs_wants(nw, title=f"Needs vs Wants — {period}")

    if panel == "budget":
        budget = ma.budget_503020(df, period)
        return viz.plot_budget_503020(budget, title=f"50/30/20 — {period}")

    if panel == "dashboard":
        cat_df = ma.by_category(df, period)
        monthly = ma.monthly_trend(df)
        daily = ma.daily_series(df, period)
        budget = ma.budget_503020(df, period)
        return viz.plot_dashboard(cat_df, monthly, daily, budget)

    raise ValueError(f"Unknown panel: {panel}")


# ---------------------------------------------------------------------------
# Telegram (як notify_owner у telegram_module)
# ---------------------------------------------------------------------------

def _send_to_telegram(text: str, png_path: Path):
    """Шле PNG + текст у Telegram через прямий Bot()."""
    token = os.getenv("TELEGRAM_TOKEN")
    try:
        user_id = int(os.getenv("TELEGRAM_USER_ID", "0"))
    except ValueError:
        user_id = 0

    if not token or not user_id:
        logger.warning("[MONEY] TELEGRAM_TOKEN/USER_ID не задано")
        return

    png_path = Path(png_path) if png_path else None

    async def _send():
        try:
            from telegram import Bot
            bot = Bot(token=token)
            if png_path and png_path.exists():
                with open(png_path, "rb") as photo:
                    await bot.send_photo(chat_id=user_id, photo=photo,
                                         caption="💰 Finance Dashboard")
            if text:
                for i in range(0, len(text), 4000):
                    await bot.send_message(chat_id=user_id, text=text[i:i+4000])
            logger.info(f"[MONEY] Telegram надіслано")
        except Exception as e:
            logger.error(f"[MONEY] Telegram error: {e}")

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send())
        loop.close()

    threading.Thread(target=_run, daemon=True).start()


def get_insights(period: str = "month", export_dir=DEFAULT_EXPORT_DIR) -> dict:
    """Список рекомендацій для HUD-блоку висновків."""
    from . import report as rep
    try:
        df = _cached_df(export_dir)
    except FileNotFoundError:
        return {"insights": ["No financial data available, Sir."]}
    if df.empty:
        return {"insights": ["No financial data yet, Sir."]}
    summary = ma.summary(df, period)
    budget = ma.budget_503020(df, period)
    return {"insights": rep.insights(summary, budget)}
