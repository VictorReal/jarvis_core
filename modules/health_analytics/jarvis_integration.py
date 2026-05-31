"""
jarvis_integration.py — точка інтеграції health_analytics з JARVIS.

Підключення в brain/agent.py:

    from modules.health_analytics.jarvis_integration import (
        health_report_tool, send_health_dashboard_to_telegram
    )

Підключення в HUD:
    GET /health/dashboard → повертає latest PNG
"""

import logging
from pathlib import Path
import pandas as pd

from .parser import (
    load_sleep, load_sleep_stages, load_steps_daily,
    load_heart_rate, load_exercise, load_activity_daily,
)
from . import sleep_analysis as sa
from . import steps_analysis as st
from . import heart_rate_analysis as hra
from . import exercise_analysis as ea
from . import visualizer as viz
from . import report as rep

logger = logging.getLogger(__name__)

# Шлях за замовчуванням — куди класти експорт Samsung Health
DEFAULT_EXPORT_DIR = Path("data/samsung_health")
DASHBOARD_PATH     = Path("data/samsung_health/dashboard_latest.png")


def find_latest_export(export_dir: Path | str = DEFAULT_EXPORT_DIR) -> dict[str, Path]:
    """
    Шукає найсвіжіші Samsung Health CSV у каталозі.
    Якщо одне ім'я має кілька версій (різні timestamp) — бере найновішу.
    """
    export_dir = Path(export_dir)
    if not export_dir.exists():
        raise FileNotFoundError(
            f"Папка з експортом не знайдена: {export_dir}. "
            f"Розпакуй Samsung Health ZIP сюди."
        )

    patterns = {
        "sleep":         "com.samsung.shealth.sleep.*.csv",
        "sleep_stage":   "com.samsung.health.sleep_stage.*.csv",
        "steps_daily":   "com.samsung.shealth.tracker.pedometer_day_summary.*.csv",
        "heart_rate":    "com.samsung.shealth.tracker.heart_rate.*.csv",
        "exercise":      "com.samsung.shealth.exercise.*.csv",
        "activity_day":  "com.samsung.shealth.activity.day_summary.*.csv",
    }

    found = {}
    for key, pattern in patterns.items():
        candidates = sorted(export_dir.glob(pattern))
        if candidates:
            found[key] = candidates[-1]  # найновіша по timestamp у назві
    return found


def load_all(export_dir: Path | str = DEFAULT_EXPORT_DIR) -> dict[str, pd.DataFrame]:
    """Завантажує всі датасети одним викликом."""
    files = find_latest_export(Path(export_dir))
    loaders = {
        "sleep":        load_sleep,
        "sleep_stage":  load_sleep_stages,
        "steps_daily":  load_steps_daily,
        "heart_rate":   load_heart_rate,
        "exercise":     load_exercise,
        "activity_day": load_activity_daily,
    }
    out = {}
    for key, path in files.items():
        try:
            out[key] = loaders[key](path)
            logger.info(f"[HEALTH] Завантажено {key}: {len(out[key])} рядків")
        except Exception as e:
            logger.error(f"[HEALTH] Не вдалось завантажити {key}: {e}")
    return out


# ---------------------------------------------------------------------------
# LLM TOOL
# ---------------------------------------------------------------------------

def health_report_tool(period: str = "week",
                       send_telegram: bool = False,
                       export_dir: Path | str = DEFAULT_EXPORT_DIR) -> str:
    """
    LLM-tool. Аналізує дані Samsung Health за період.

    Args:
        period: today / week / month / year / all
        send_telegram: якщо True — шле PNG-dashboard і повний звіт у Telegram
        export_dir: де лежать CSV-експорти

    Returns:
        Текстовий звіт (повертає в LLM, який потім озвучить/відповість).
    """
    try:
        data = load_all(Path(export_dir))
    except FileNotFoundError as e:
        return f"Sir, {e}"

    if not data:
        return "Sir, Samsung Health export not found. Place CSV files in data/samsung_health/."

    parts = []

    # Steps
    if "steps_daily" in data:
        s = st.steps_summary(data["steps_daily"], period)
        parts.append(rep.steps_report(s))

    # Sleep + stages
    if "sleep" in data:
        sl_sum = sa.sleep_summary(data["sleep"], period)
        stages = sa.sleep_stages_breakdown(data["sleep_stage"]) if "sleep_stage" in data else None
        parts.append(rep.sleep_report(sl_sum, stages))

    # Heart rate
    if "heart_rate" in data:
        parts.append(rep.hr_report(hra.hr_summary(data["heart_rate"], period)))

    # Exercise
    if "exercise" in data:
        parts.append(rep.exercise_report(ea.exercise_summary(data["exercise"], period)))

    text_report = "\n\n".join(parts)

    if send_telegram:
        try:
            png_path = generate_dashboard(data, period=period)
            _send_to_telegram(text_report, png_path)
        except Exception as e:
            logger.error(f"[HEALTH] Telegram send failed: {e}")

    return text_report


# ---------------------------------------------------------------------------
# DASHBOARD PNG (для HUD і Telegram)
# ---------------------------------------------------------------------------

def generate_dashboard(data: dict[str, pd.DataFrame] | None = None,
                       period: str = "month",
                       out_path: Path | str = DASHBOARD_PATH) -> Path:
    """
    Генерує composite-dashboard PNG. Повертає шлях.
    Якщо data не передано — завантажує сам.
    """
    if data is None:
        data = load_all()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    steps_series = st.daily_series(data["steps_daily"], period) if "steps_daily" in data else pd.DataFrame()
    weekday_df   = st.weekday_pattern(data["steps_daily"]) if "steps_daily" in data else pd.DataFrame()
    sleep_series = sa.daily_series(data["sleep"], period) if "sleep" in data else pd.DataFrame()
    stages = sa.sleep_stages_breakdown(data["sleep_stage"]) if "sleep_stage" in data else {}

    viz.plot_dashboard(
        steps_series=steps_series,
        weekday_df=weekday_df,
        sleep_series=sleep_series,
        stages_breakdown=stages,
        path=out_path,
    )
    return out_path


# ---------------------------------------------------------------------------
# Telegram (опціональна інтеграція)
# ---------------------------------------------------------------------------

def _send_to_telegram(text: str, png_path: Path):
    """
    Шле PNG-dashboard + текстовий звіт у Telegram.
    Не залежить від інстансу TelegramModule — створює Bot напряму
    (як TelegramModule.notify_owner), щоб працювати з будь-якого потоку.
    """
    import os
    import asyncio
    import threading

    token = os.getenv("TELEGRAM_TOKEN")
    try:
        user_id = int(os.getenv("TELEGRAM_USER_ID", "0"))
    except ValueError:
        user_id = 0

    if not token or not user_id:
        logger.warning("[HEALTH] TELEGRAM_TOKEN або USER_ID не задано в .env")
        return

    png_path = Path(png_path) if png_path else None

    async def _send():
        try:
            from telegram import Bot
            bot = Bot(token=token)

            # 1) Фото з коротким caption
            if png_path and png_path.exists():
                with open(png_path, "rb") as photo:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=photo,
                        caption="📊 Health Dashboard",
                    )

            # 2) Повний текст звіту (розбиваємо якщо > 4000 символів)
            if text:
                for i in range(0, len(text), 4000):
                    await bot.send_message(chat_id=user_id, text=text[i:i + 4000])

            logger.info(f"[HEALTH] Telegram надіслано: dashboard + {len(text)} chars")
        except Exception as e:
            logger.error(f"[HEALTH] Telegram send error: {e}")

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_send())
        loop.close()

    threading.Thread(target=_run, daemon=True).start()


# ===========================================================================
# HUD-специфічні функції (для мініпанелі + модалу)
# ===========================================================================

import time as _time
from datetime import datetime

# Простий in-memory кеш — щоб HUD не парсив CSV кожні 2 секунди
_cache = {"data": None, "loaded_at": 0}
_CACHE_TTL = 300  # 5 хв


def _cached_data(export_dir: Path | str = DEFAULT_EXPORT_DIR) -> dict[str, pd.DataFrame]:
    """Кешований load_all — повертає дані з пам'яті якщо TTL не вийшов."""
    now = _time.time()
    if _cache["data"] is not None and (now - _cache["loaded_at"]) < _CACHE_TTL:
        return _cache["data"]
    _cache["data"] = load_all(export_dir)
    _cache["loaded_at"] = now
    return _cache["data"]


def invalidate_cache():
    """Скидає кеш (викликати після нового експорту)."""
    _cache["data"] = None
    _cache["loaded_at"] = 0


def today_summary(export_dir: Path | str = DEFAULT_EXPORT_DIR) -> dict:
    """
    Мінімальне зведення для HUD-мініпанелі.
    Повертає: steps_today, sleep_last_h, hr_latest, hr_resting_avg
    """
    try:
        data = _cached_data(export_dir)
    except FileNotFoundError:
        return {"available": False, "error": "no data folder"}

    if not data:
        return {"available": False, "error": "empty export"}

    today = pd.Timestamp.now().normalize()
    out = {"available": True}

    # Кроки сьогодні (або останній день з даними)
    if "steps_daily" in data and not data["steps_daily"].empty:
        df = data["steps_daily"]
        today_row = df[df["date"] == today]
        if not today_row.empty:
            out["steps_today"] = int(today_row["step_count"].iloc[0])
            out["steps_today_label"] = "today"
        else:
            last = df.iloc[-1]
            out["steps_today"] = int(last["step_count"])
            days_ago = (today - last["date"]).days
            out["steps_today_label"] = f"{days_ago}d ago" if days_ago > 0 else "today"

    # Останній сон
    if "sleep" in data and not data["sleep"].empty:
        df = data["sleep"].sort_values("start")
        last = df.iloc[-1]
        out["sleep_last_h"] = round(float(last["duration_h"]), 1)
        out["sleep_last_date"] = str(last["start"].date())

    # Останній пульс (та середній resting за тиждень)
    if "heart_rate" in data and not data["heart_rate"].empty:
        df = data["heart_rate"].sort_values("timestamp")
        out["hr_latest"] = int(df["hr"].iloc[-1])
        week_ago = today - pd.Timedelta(days=7)
        recent = df[df["timestamp"] >= week_ago]
        if not recent.empty:
            resting = recent[recent["hr"] < 60]["hr"]
            if not resting.empty:
                out["hr_resting_week"] = round(float(resting.mean()), 1)

    return out


def get_summary_dict(period: str = "week",
                     export_dir: Path | str = DEFAULT_EXPORT_DIR) -> dict:
    """Повний summary як dict (для JSON-endpoint у HUD)."""
    try:
        data = _cached_data(export_dir)
    except FileNotFoundError:
        return {"available": False}

    if not data:
        return {"available": False}

    out = {"available": True, "period": period}

    if "steps_daily" in data:
        out["steps"] = st.steps_summary(data["steps_daily"], period)
    if "sleep" in data:
        out["sleep"] = sa.sleep_summary(data["sleep"], period)
        if "sleep_stage" in data:
            out["sleep_stages"] = sa.sleep_stages_breakdown(data["sleep_stage"])
    if "heart_rate" in data:
        out["heart_rate"] = hra.hr_summary(data["heart_rate"], period)
    if "exercise" in data:
        out["exercise"] = ea.exercise_summary(data["exercise"], period)

    # JSON-сумісні типи (numpy → native python)
    return _to_native(out)


def _to_native(obj):
    """Рекурсивна конверсія numpy/pandas типів у Python-native (для JSON)."""
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
                     export_dir: Path | str = DEFAULT_EXPORT_DIR) -> bytes:
    """
    Рендерить один графік за назвою (для HUD-модалу).
    panel: steps_daily | steps_weekday | steps_monthly | sleep_duration |
           sleep_stages | resting_hr | dashboard
    """
    data = _cached_data(export_dir)

    if panel == "steps_daily" and "steps_daily" in data:
        series = st.daily_series(data["steps_daily"], period)
        return viz.plot_steps_daily(series, title=f"Daily Steps — {period}")

    if panel == "steps_weekday" and "steps_daily" in data:
        wd = st.weekday_pattern(data["steps_daily"])
        return viz.plot_steps_weekday(wd, title="Avg Steps by Weekday")

    if panel == "steps_monthly" and "steps_daily" in data:
        mn = st.monthly_trend(data["steps_daily"])
        return viz.plot_steps_monthly_trend(mn, title="Monthly Steps Trend")

    if panel == "sleep_duration" and "sleep" in data:
        series = sa.daily_series(data["sleep"], period)
        return viz.plot_sleep_duration(series, title=f"Sleep Duration — {period}")

    if panel == "sleep_stages" and "sleep_stage" in data:
        breakdown = sa.sleep_stages_breakdown(data["sleep_stage"])
        return viz.plot_sleep_stages_pie(breakdown, title="Sleep Stages")

    if panel == "resting_hr" and "heart_rate" in data:
        daily = hra.daily_resting_hr(data["heart_rate"], period)
        return viz.plot_resting_hr(daily, title=f"Resting HR — {period}")

    if panel == "dashboard":
        steps_series = st.daily_series(data["steps_daily"], period) if "steps_daily" in data else pd.DataFrame()
        wd = st.weekday_pattern(data["steps_daily"]) if "steps_daily" in data else pd.DataFrame()
        sleep_series = sa.daily_series(data["sleep"], period) if "sleep" in data else pd.DataFrame()
        stages = sa.sleep_stages_breakdown(data["sleep_stage"]) if "sleep_stage" in data else {}
        return viz.plot_dashboard(steps_series, wd, sleep_series, stages)

    raise ValueError(f"Unknown panel: {panel}")