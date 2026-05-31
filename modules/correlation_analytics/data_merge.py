"""
data_merge.py — зведення всіх денних метрик у єдину таблицю (index=date).
Дістає денні ряди з health / money / mood модулів через їхні наявні функції.
Стійкий до відсутніх джерел: якщо модуль/дані недоступні — метрика просто пропускається.
"""
import logging
import pandas as pd

logger = logging.getLogger(__name__)


def _safe(fn, label):
    """Викликає fn(), повертає результат або None з логом."""
    try:
        return fn()
    except Exception as e:
        logger.info(f"[CORR] Джерело '{label}' недоступне: {e}")
        return None


def _health_daily() -> dict[str, pd.Series]:
    """Денні ряди здоров'я: steps, sleep_h, resting_hr. Кожен — Series(index=date)."""
    out = {}
    from modules.health_analytics.jarvis_integration import load_all
    from modules.health_analytics import steps_analysis as st
    from modules.health_analytics import sleep_analysis as sa
    from modules.health_analytics import heart_rate_analysis as hra

    data = load_all()
    if not data:
        return out

    # Steps
    if "steps_daily" in data and not data["steps_daily"].empty:
        s = data["steps_daily"][["date", "step_count"]].copy()
        s["date"] = pd.to_datetime(s["date"])
        out["steps"] = s.set_index("date")["step_count"]

    # Sleep (основна сесія за ніч)
    if "sleep" in data and not data["sleep"].empty:
        ser = sa.daily_series(data["sleep"], period="all")
        if not ser.empty:
            ser = ser.copy()
            ser["night_date"] = pd.to_datetime(ser["night_date"])
            out["sleep_h"] = ser.set_index("night_date")["duration_h"]

    # Resting HR (денний мінімум як наближення)
    if "heart_rate" in data and not data["heart_rate"].empty:
        daily = hra.daily_resting_hr(data["heart_rate"], period="all")
        if not daily.empty:
            daily = daily.copy()
            daily["date"] = pd.to_datetime(daily["date"])
            out["resting_hr"] = daily.set_index("date")["resting_hr"]

    return out


def _mood_daily() -> dict[str, pd.Series]:
    """Денний mood (середній за день)."""
    from modules.mood_analytics import parser as mp
    from modules.mood_analytics import analysis as ma
    df = mp.load_df()
    cf = ma.correlation_frame(df)  # index=date, col 'mood'
    if cf.empty:
        return {}
    return {"mood": cf["mood"]}


def _money_daily() -> dict[str, pd.Series]:
    """Денні витрати (сума expense за день)."""
    from modules.money_analytics.jarvis_integration import _cached_df
    from modules.money_analytics import analysis as moa
    df = _cached_df()  # повний df транзакцій
    series = moa.daily_series(df, period="all")  # date, amount
    if series.empty:
        return {}
    s = series.copy()
    s["date"] = pd.to_datetime(s["date"])
    return {"spending": s.set_index("date")["amount"]}


def build_daily_matrix(min_overlap: int = 0) -> pd.DataFrame:
    """
    Зводить усі доступні метрики в одну денну таблицю (index=date, columns=метрики).
    Пропущені джерела просто відсутні як колонки. NaN там, де в день нема даних.
    """
    series_map: dict[str, pd.Series] = {}

    for label, fn in (("health", _health_daily),
                       ("mood", _mood_daily),
                       ("money", _money_daily)):
        res = _safe(fn, label)
        if res:
            series_map.update(res)

    if not series_map:
        return pd.DataFrame()

    # Нормалізуємо індекси до дати (без часу) і зводимо
    cols = {}
    for name, ser in series_map.items():
        s = ser.copy()
        s.index = pd.to_datetime(s.index).normalize()
        # якщо в індексі дублі дат — агрегуємо
        s = s.groupby(s.index).mean()
        cols[name] = s

    df = pd.DataFrame(cols).sort_index()
    return df
