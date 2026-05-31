"""
Парсер даних настрою.
Читає/пише data/mood/moods.csv — один рядок на запис.
Повертає чистий pandas DataFrame з типізованими колонками.
"""
import os
import csv
from datetime import datetime

import pandas as pd

from .constants import (
    CSV_PATH, DATA_DIR, CSV_COLUMNS,
    SCORE_MIN, SCORE_MAX, MOOD_TAGS,
    normalize_time_of_day,
)


def _ensure_file():
    """Створює теку і CSV з заголовком, якщо їх ще нема."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
        print(f"[MOOD] Створено новий файл даних: {CSV_PATH}")


def add_entry(score: int, tags=None, note: str = "",
              time_of_day: str = "", source: str = "manual") -> dict:
    """
    Додає один запис настрою. Окремий рядок — для time-series аналітики.
    score: 1-10
    tags: список тегів або рядок через ';'
    note: вільна нотатка
    time_of_day: morning/evening/adhoc (порожнє → авто за годиною)
    source: voice/hud/telegram/manual
    Повертає dict із записаним рядком.
    """
    _ensure_file()

    # Валідація оцінки
    score = int(round(float(score)))
    score = max(SCORE_MIN, min(SCORE_MAX, score))

    # Нормалізуємо теги
    if tags is None:
        tags = []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(",", ";").split(";") if t.strip()]
    # Лишаємо тільки валідні (невідомі ігноруємо, але не падаємо)
    clean_tags = [t.lower() for t in tags if t.lower() in MOOD_TAGS]

    now = datetime.now()
    tod = normalize_time_of_day(time_of_day, now.hour)

    # Нотатку чистимо від ';' щоб не ламати CSV-теги (теги через ';')
    safe_note = (note or "").replace(";", ",").strip()

    row = {
        "timestamp":   now.strftime("%Y-%m-%d %H:%M:%S"),
        "date":        now.strftime("%Y-%m-%d"),
        "time_of_day": tod,
        "score":       score,
        "tags":        ";".join(clean_tags),
        "note":        safe_note,
        "source":      source,
    }

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(row)

    print(f"[MOOD] Записано: score={score} tags={clean_tags} ({source})")
    return row


def load_df() -> pd.DataFrame:
    """
    Завантажує всі записи у DataFrame з типізацією.
    Порожній DataFrame з правильними колонками — якщо даних нема.
    """
    _ensure_file()
    try:
        df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
    except Exception as e:
        print(f"[MOOD] Помилка читання CSV: {e}")
        return pd.DataFrame(columns=CSV_COLUMNS)

    if df.empty:
        return df

    # Типізація
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["date"]      = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["score"]     = pd.to_numeric(df["score"], errors="coerce")
    # Теги → список
    df["tag_list"]  = df["tags"].apply(
        lambda s: [t for t in str(s).split(";") if t] if s else []
    )

    # Викидаємо биті рядки (без часу або оцінки)
    df = df.dropna(subset=["timestamp", "score"]).reset_index(drop=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def filter_period(df: pd.DataFrame, period: str = "all") -> pd.DataFrame:
    """Фільтрує DataFrame за періодом: today/week/month/year/all."""
    if df.empty or period == "all":
        return df
    now = pd.Timestamp.now()
    if period == "today":
        start = now.normalize()
    elif period == "week":
        start = now - pd.Timedelta(days=7)
    elif period == "month":
        start = now - pd.Timedelta(days=30)
    elif period == "year":
        start = now - pd.Timedelta(days=365)
    else:
        return df
    return df[df["timestamp"] >= start].reset_index(drop=True)
