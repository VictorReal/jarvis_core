"""
analysis.py — крос-кореляційний аналіз зведеної денної таблиці.
Матриця Пірсона, лагові ефекти, генерація людських висновків/рекомендацій.
"""
import pandas as pd
import numpy as np

from .constants import (
    METRICS, CORR_NOTABLE, CORR_STRONG, MIN_OVERLAP_DAYS, PAIR_INSIGHTS,
)


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Матриця кореляцій Пірсона по доступних метриках (pairwise, NaN відкидаються попарно)."""
    if df.empty or df.shape[1] < 2:
        return pd.DataFrame()
    return df.corr(method="pearson", min_periods=MIN_OVERLAP_DAYS)


def pair_overlaps(df: pd.DataFrame) -> dict:
    """Скільки спільних (не-NaN) днів має кожна пара — для довіри до кореляції."""
    out = {}
    cols = list(df.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            n = int(df[[a, b]].dropna().shape[0])
            out[(a, b)] = n
    return out


def strongest_pairs(df: pd.DataFrame, top: int = 5) -> list[dict]:
    """
    Найсильніші зв'язки (за |r|), лише пари з достатнім overlap.
    Повертає список dict: {a, b, r, n, strength}.
    """
    corr = correlation_matrix(df)
    if corr.empty:
        return []
    overlaps = pair_overlaps(df)
    pairs = []
    cols = list(corr.columns)
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            a, b = cols[i], cols[j]
            r = corr.loc[a, b]
            n = overlaps.get((a, b), 0)
            if pd.isna(r) or n < MIN_OVERLAP_DAYS:
                continue
            strength = ("strong" if abs(r) >= CORR_STRONG
                        else "notable" if abs(r) >= CORR_NOTABLE
                        else "weak")
            pairs.append({"a": a, "b": b, "r": round(float(r), 2),
                          "n": n, "strength": strength})
    pairs.sort(key=lambda p: abs(p["r"]), reverse=True)
    return pairs[:top]


def lagged_correlation(df: pd.DataFrame, driver: str, outcome: str,
                       max_lag: int = 2) -> dict:
    """
    Чи корелює driver сьогодні з outcome через 0..max_lag днів.
    Напр. driver='sleep_h', outcome='mood' → чи впливає сон на настрій наступного дня.
    Повертає {lag: r} для лагів з достатнім overlap.
    """
    if driver not in df.columns or outcome not in df.columns:
        return {}
    out = {}
    for lag in range(0, max_lag + 1):
        shifted = df[outcome].shift(-lag)
        pair = pd.concat([df[driver], shifted], axis=1).dropna()
        if len(pair) >= MIN_OVERLAP_DAYS:
            r = pair.iloc[:, 0].corr(pair.iloc[:, 1])
            if not pd.isna(r):
                out[lag] = round(float(r), 2)
    return out


def summary(df: pd.DataFrame) -> dict:
    """Зведення для HUD-модалу: які метрики є, скільки днів, найсильніші зв'язки."""
    if df.empty:
        return {"available": False, "metrics": [], "days": 0, "pairs": []}
    return {
        "available": True,
        "metrics": [METRICS.get(c, c) for c in df.columns],
        "metric_keys": list(df.columns),
        "days": int(df.dropna(how="all").shape[0]),
        "full_overlap_days": int(df.dropna().shape[0]),
        "pairs": strongest_pairs(df, top=6),
    }


def _label(key: str) -> str:
    return METRICS.get(key, key)


def insights(df: pd.DataFrame) -> list[str]:
    """
    Генерує людські висновки/рекомендації на основі знайдених зв'язків.
    Використовує PAIR_INSIGHTS для напрямкової інтерпретації + кілька загальних правил.
    """
    if df.empty:
        return ["Not enough data yet to find cross-metric patterns, Sir."]

    pairs = strongest_pairs(df, top=8)
    out = []

    for p in pairs:
        if p["strength"] == "weak":
            continue
        a, b, r = p["a"], p["b"], p["r"]
        key = (a, b) if (a, b) in PAIR_INSIGHTS else (b, a) if (b, a) in PAIR_INSIGHTS else None
        if key:
            pos, neg = PAIR_INSIGHTS[key]
            text = pos if r > 0 else neg
        else:
            direction = "rises with" if r > 0 else "falls as"
            text = f"{_label(a)} {direction} {_label(b)}."
        strength_word = "Strong" if p["strength"] == "strong" else "Notable"
        out.append(f"{strength_word} link (r={r}, n={p['n']}d): {text}")

    # Лаговий ефект сну на настрій — окремо, якщо є обидві метрики
    if "sleep_h" in df.columns and "mood" in df.columns:
        lags = lagged_correlation(df, "sleep_h", "mood", max_lag=2)
        if lags:
            same = lags.get(0)
            nxt = lags.get(1)
            if same is not None and nxt is not None and abs(nxt) > abs(same) + 0.05:
                out.append(
                    f"Sleep affects next-day mood more than same-day "
                    f"(r={nxt} vs {same}) — protect your sleep for tomorrow."
                )

    # Лаговий ефект тренування на сон тієї ж ночі та настрій наступного дня
    if "workout" in df.columns:
        if "sleep_h" in df.columns:
            wl = lagged_correlation(df, "workout", "sleep_h", max_lag=1)
            r0 = wl.get(0)
            if r0 is not None and abs(r0) >= CORR_NOTABLE:
                if r0 > 0:
                    out.append(f"Training days lead to more sleep that night (r={r0}).")
                else:
                    out.append(f"Training days lead to less sleep that night (r={r0}) — mind recovery.")
        if "mood" in df.columns:
            wm = lagged_correlation(df, "workout", "mood", max_lag=1)
            nxt = wm.get(1)
            if nxt is not None and abs(nxt) >= CORR_NOTABLE:
                if nxt > 0:
                    out.append(f"Mood is higher the day after training (r={nxt}).")
                else:
                    out.append(f"Mood dips the day after training (r={nxt}) — possible fatigue.")

    if not out:
        out.append("No strong cross-metric patterns yet — keep logging for clearer signals, Sir.")
    return out
