"""
voice_id_module.py — Розпізнавання людини за голосом

Принцип:
  1. enroll(name, audio_np)  — записати зразок голосу (5-10 сек) → ембедінг → data/voice_profiles/
  2. identify(audio_np)      — порівняти з усіма профілями → ім'я або None
  3. identify_from_mic()     — записати з мікрофона і ідентифікувати

Ембедінг: MFCC (40 коефіцієнтів) + delta + delta-delta → mean вектор.
Схожість: cosine similarity. Поріг: 0.82 (налаштовується).
Не потребує інтернету, працює локально.
"""

import json
import logging
import os
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

VOICE_DIR    = Path("data/voice_profiles")
SAMPLE_RATE  = 16000
THRESHOLD    = 0.82   # мінімальна cosine similarity для впевненого розпізнавання
ENROLL_SECS  = 7      # скільки секунд записуємо при реєстрації


# ─────────────────────────────────────────────────────────────────────────────
#  Утиліти
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_dir():
    VOICE_DIR.mkdir(parents=True, exist_ok=True)


def _profile_path(name: str) -> Path:
    return VOICE_DIR / f"{name.lower().replace(' ', '_')}.json"


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ─────────────────────────────────────────────────────────────────────────────
#  MFCC ембедінг
# ─────────────────────────────────────────────────────────────────────────────

def _compute_embedding(audio_np: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray | None:
    """
    Обчислює MFCC ембедінг аудіо.
    audio_np: float32 або int16, mono.
    """
    try:
        import librosa
    except ImportError:
        logger.error("[VOICE_ID] librosa не встановлено. pip install librosa")
        return None

    # Нормалізуємо до float32 [-1, 1]
    audio = audio_np.astype(np.float32)
    if audio.dtype != np.float32 or audio.max() > 1.0:
        audio = audio / 32768.0

    # Flatten якщо stereo
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    # MFCC (40) + delta + delta-delta → вектор 120 значень
    mfcc       = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=40)
    mfcc_delta = librosa.feature.delta(mfcc)
    mfcc_d2    = librosa.feature.delta(mfcc, order=2)

    features = np.concatenate([
        mfcc.mean(axis=1),
        mfcc_delta.mean(axis=1),
        mfcc_d2.mean(axis=1),
    ])
    return features


# ─────────────────────────────────────────────────────────────────────────────
#  Запис з мікрофона
# ─────────────────────────────────────────────────────────────────────────────

def record_audio(duration: float = ENROLL_SECS, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Записує аудіо з мікрофона. Повертає int16 numpy array."""
    import sounddevice as sd
    print(f"[VOICE_ID] Запис {duration} сек... говоріть зараз")
    audio = sd.rec(
        int(duration * sr),
        samplerate=sr,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    print("[VOICE_ID] Запис завершено")
    return audio.flatten()


# ─────────────────────────────────────────────────────────────────────────────
#  Реєстрація голосу (enroll)
# ─────────────────────────────────────────────────────────────────────────────

def enroll(name: str, audio_np: np.ndarray | None = None, sr: int = SAMPLE_RATE) -> bool:
    """
    Реєструє голос людини.
    Якщо audio_np не передано — записує з мікрофона.
    Якщо профіль вже існує — усереднює з попереднім (для надійності).
    """
    _ensure_dir()

    if audio_np is None:
        print(f"[VOICE_ID] Реєстрація голосу: {name}")
        audio_np = record_audio(ENROLL_SECS, sr)

    embedding = _compute_embedding(audio_np, sr)
    if embedding is None:
        return False

    path = _profile_path(name)
    if path.exists():
        # Усереднюємо з існуючим ембедінгом → більш стабільний профіль
        try:
            existing = json.loads(path.read_text())
            old_emb = np.array(existing["embedding"])
            embedding = (embedding + old_emb) / 2.0
            logger.info(f"[VOICE_ID] Оновлено профіль {name} (усереднення)")
        except Exception:
            pass

    data = {
        "name": name,
        "embedding": embedding.tolist(),
        "enrolled_at": time.strftime("%Y-%m-%d %H:%M"),
        "sample_rate": sr,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"[VOICE_ID] Профіль збережено: {name}")
    return True


def enroll_from_mic(name: str) -> bool:
    """Зручна обгортка: записати і зареєструвати."""
    return enroll(name, audio_np=None)


# ─────────────────────────────────────────────────────────────────────────────
#  Розпізнавання (identify)
# ─────────────────────────────────────────────────────────────────────────────

def identify(audio_np: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[str | None, float]:
    """
    Ідентифікує людину за голосом.
    Повертає (name, score) або (None, 0.0) якщо не впізнано.
    """
    _ensure_dir()

    embedding = _compute_embedding(audio_np, sr)
    if embedding is None:
        return None, 0.0

    profiles = list(VOICE_DIR.glob("*.json"))
    if not profiles:
        logger.info("[VOICE_ID] Немає зареєстрованих голосів")
        return None, 0.0

    best_name  = None
    best_score = 0.0

    for path in profiles:
        try:
            data = json.loads(path.read_text())
            ref_emb = np.array(data["embedding"])
            score   = _cosine_sim(embedding, ref_emb)
            logger.debug(f"[VOICE_ID] {data['name']}: {score:.3f}")
            if score > best_score:
                best_score = score
                best_name  = data["name"]
        except Exception as e:
            logger.warning(f"[VOICE_ID] Помилка читання {path}: {e}")

    if best_score >= THRESHOLD:
        print(f"[VOICE_ID] Впізнано: {best_name} (score={best_score:.3f})")
        return best_name, best_score
    else:
        print(f"[VOICE_ID] Не впізнано (найкраще: {best_name}, score={best_score:.3f})")
        return None, best_score


def identify_from_mic(duration: float = 4.0) -> tuple[str | None, float]:
    """Записує з мікрофона і ідентифікує."""
    audio = record_audio(duration)
    return identify(audio)


# ─────────────────────────────────────────────────────────────────────────────
#  Утиліти управління профілями
# ─────────────────────────────────────────────────────────────────────────────

def list_enrolled() -> list[str]:
    """Список всіх зареєстрованих голосів."""
    _ensure_dir()
    names = []
    for path in VOICE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            names.append(data["name"])
        except Exception:
            pass
    return names


def delete_voice_profile(name: str) -> bool:
    """Видаляє голосовий профіль."""
    path = _profile_path(name)
    if path.exists():
        path.unlink()
        print(f"[VOICE_ID] Профіль видалено: {name}")
        return True
    return False


def set_threshold(value: float):
    """Змінює поріг розпізнавання (0.0–1.0). За замовчуванням 0.82."""
    global THRESHOLD
    THRESHOLD = max(0.0, min(1.0, value))
    print(f"[VOICE_ID] Поріг встановлено: {THRESHOLD}")