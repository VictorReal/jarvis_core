"""
parser.py — Завантаження експорту Money Manager (.xlsx).

Структура файлу:
  - Лист 'Expenses': витрати з категоріями
  - Лист 'Income':   надходження
  - Лист 'Transfers': перекидки між акаунтами (не враховуємо в P&L)

Перший рядок у кожному листі — title ("expenses list for the period..."),
тому skiprows=1.
"""

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)


def _normalize(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Нормалізує колонки експорту Money Manager у наш формат."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["Date and time"], errors="coerce")
    df["category"] = df["Category"].astype(str).str.strip()
    df["account"] = df["Account"].astype(str).str.strip()
    df["amount"] = pd.to_numeric(df["Amount in default currency"], errors="coerce")
    df["currency"] = df["Default currency"].astype(str).str.strip()
    df["comment"] = df["Comment"].fillna("").astype(str).str.strip()
    df["tags"] = df["Tags"].fillna("").astype(str).str.strip()
    df["kind"] = kind  # 'expense' або 'income'
    df = df.dropna(subset=["date", "amount"]).copy()
    return df[["date", "kind", "category", "account",
               "amount", "currency", "comment", "tags"]] \
        .sort_values("date").reset_index(drop=True)


def load_expenses(path: str | Path) -> pd.DataFrame:
    """Витрати → DataFrame з нормалізованими колонками."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Money Manager файл не знайдено: {path}")
    df = pd.read_excel(path, sheet_name="Expenses", skiprows=1)
    return _normalize(df, kind="expense")


def load_income(path: str | Path) -> pd.DataFrame:
    """Надходження → DataFrame з нормалізованими колонками."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Money Manager файл не знайдено: {path}")
    df = pd.read_excel(path, sheet_name="Income", skiprows=1)
    return _normalize(df, kind="income")


def load_all_files(export_dir: str | Path) -> pd.DataFrame:
    """
    Завантажує ВСІ .xlsx з каталогу і об'єднує в один DataFrame.
    Дозволяє накопичувати експорти за кілька років.
    Дублі (та сама date+category+amount+comment) — видаляються.
    """
    export_dir = Path(export_dir)
    if not export_dir.exists():
        raise FileNotFoundError(
            f"Папка з експортом не знайдена: {export_dir}. "
            f"Поклади .xlsx з Money Manager сюди."
        )

    files = sorted(export_dir.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError(f"У {export_dir} немає .xlsx файлів")

    all_dfs = []
    for f in files:
        try:
            ex = load_expenses(f)
            all_dfs.append(ex)
            logger.info(f"[MONEY] {f.name}: {len(ex)} expenses")
        except Exception as e:
            logger.warning(f"[MONEY] не вдалось експорт {f.name} (expenses): {e}")
        try:
            inc = load_income(f)
            all_dfs.append(inc)
            logger.info(f"[MONEY] {f.name}: {len(inc)} incomes")
        except Exception as e:
            logger.warning(f"[MONEY] не вдалось експорт {f.name} (income): {e}")

    if not all_dfs:
        raise ValueError(f"Жоден файл у {export_dir} не парсився")

    combined = pd.concat(all_dfs, ignore_index=True)
    # Видаляємо дублі (можуть бути коли експорти перекриваються)
    combined = combined.drop_duplicates(
        subset=["date", "kind", "category", "amount", "comment"]
    )
    return combined.sort_values("date").reset_index(drop=True)
