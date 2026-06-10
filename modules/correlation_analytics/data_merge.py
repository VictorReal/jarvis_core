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


def _workout_daily() -> dict[str, pd.Series]:
    """Бінарний денний ряд тренувань: 1 = тренувався того дня, 0 = ні.
    Дні без жодного запису лишаються 0 (а не NaN), бо 'не тренувався' —
    це валідне спостереження, потрібне для кореляцій (тренування×сон тощо)."""
    import json
    from pathlib import Path

    wf = Path("data/workouts.json")
    if not wf.exists():
        return {}
    try:
        data = json.loads(wf.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not data:
        return {}

    # дати, коли було хоч одне тренування
    dates = []
    for entry in data:
        t = entry.get("time")
        if t:
            dates.append(pd.to_datetime(t).normalize())
    if not dates:
        return {}

    trained = pd.Series(1, index=pd.DatetimeIndex(dates))
    trained = trained.groupby(trained.index).max()  # кілька записів/день → 1

    # заповнюємо 0 для всіх днів у діапазоні (щоб 'дні відпочинку' рахувались)
    full = pd.date_range(trained.index.min(), trained.index.max(), freq="D")
    workout = trained.reindex(full, fill_value=0).astype(float)
    return {"workout": workout}


def _alcohol_daily() -> dict[str, pd.Series]:
    """Денні витрати на алкоголь (проксі обсягу) з money-модуля.
    Шукає транзакції з категорією, схожою на алкоголь (alco/alcohol/алкоголь).
    Якщо колонки категорії немає або нічого не знайдено — метрика пропускається."""
    from modules.money_analytics.jarvis_integration import _cached_df
    df = _cached_df()
    if df is None or df.empty:
        return {}

    # знаходимо колонку категорії (назва може різнитись)
    cat_col = None
    for cand in ("category", "Category", "категорія", "Категорія", "type", "Type"):
        if cand in df.columns:
            cat_col = cand
            break
    if cat_col is None:
        return {}

    # знаходимо колонку дати і суми
    date_col = next((c for c in ("date", "Date", "дата", "Дата", "time", "datetime") if c in df.columns), None)
    amt_col = next((c for c in ("amount", "Amount", "сума", "Сума", "value", "expense") if c in df.columns), None)
    if date_col is None or amt_col is None:
        return {}

    # фільтр рядків, де категорія містить алкоголь-ключі
    mask = df[cat_col].astype(str).str.lower().str.contains(
        "alco|alcohol|алког|алко|пиво|beer|wine|вино|горілк|whiskey|віскі", regex=True, na=False
    )
    al = df[mask].copy()
    if al.empty:
        return {}

    al[date_col] = pd.to_datetime(al[date_col], errors="coerce")
    al = al.dropna(subset=[date_col])
    # сума витрат на алкоголь за день (абс — бо expense може бути відʼємним)
    al["_amt"] = pd.to_numeric(al[amt_col], errors="coerce").abs()
    daily = al.groupby(al[date_col].dt.normalize())["_amt"].sum()
    if daily.empty:
        return {}
    return {"alcohol": daily}


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
                       ("money", _money_daily),
                       ("alcohol", _alcohol_daily),
                       ("workout", _workout_daily)):
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
