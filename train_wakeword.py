"""
train_wakeword.py — тренування кастомного wake word через OpenWakeWord embeddings + sklearn → ONNX
Використання: python train_wakeword.py --word ultron
"""

import argparse
import os
import glob
import numpy as np
import onnxruntime as ort
import librosa
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType

# ── параметри OWW ────────────────────────────────────────────────────────────
SAMPLE_RATE     = 16000
MEL_CHUNK       = 1280      # семплів на один виклик mel-моделі
MEL_PER_CHUNK   = 5         # mel-рядків з одного чанку (виміряно: shape (1,1,5,32))
N_MEL_FRAMES    = 76        # embedding очікує (batch, 76, 32, 1)
EMBEDDING_DIM   = 96        # розмір виходу embedding_model: (1,1,1,96)

# чанків потрібно щоб отримати ≥76 mel-рядків
N_CHUNKS_NEEDED = int(np.ceil(N_MEL_FRAMES / MEL_PER_CHUNK))   # 16
MIN_SAMPLES     = MEL_CHUNK * N_CHUNKS_NEEDED                   # 20480 ≈ 1.28с

import openwakeword
OWW_DIR        = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
MEL_MODEL_PATH = os.path.join(OWW_DIR, "melspectrogram.onnx")
EMB_MODEL_PATH = os.path.join(OWW_DIR, "embedding_model.onnx")


def load_sessions():
    print("[*] Завантажую допоміжні моделі OWW...")
    mel_sess = ort.InferenceSession(MEL_MODEL_PATH)
    emb_sess = ort.InferenceSession(EMB_MODEL_PATH)
    return mel_sess, emb_sess


def audio_to_embedding(audio: np.ndarray, mel_sess, emb_sess) -> np.ndarray:
    """
    raw audio float32 16kHz → один 96-dim embedding вектор.
    Подаємо N_CHUNKS_NEEDED чанків в mel-модель одним викликом,
    отримуємо (1, 1, N*5, 32), беремо перші 76 рядків → (1, 76, 32, 1) → embedding.
    """
    # паддинг або обрізка
    if len(audio) < MIN_SAMPLES:
        audio = np.pad(audio, (0, MIN_SAMPLES - len(audio)))
    audio = audio[:MIN_SAMPLES].astype(np.float32)

    # подаємо всі семпли одним батчем в mel
    mel_input = audio.reshape(1, -1)                        # (1, MIN_SAMPLES)
    mel_out = mel_sess.run(None, {"input": mel_input})[0]  # (1, 1, N_rows, 32)
    # N_rows = N_CHUNKS_NEEDED * MEL_PER_CHUNK = 80

    mel_rows = mel_out[0, 0, :, :]                         # (N_rows, 32)
    mel_rows = mel_rows[:N_MEL_FRAMES, :]                  # (76, 32)

    # embedding очікує (batch, 76, 32, 1)
    emb_input = mel_rows[:, :, np.newaxis][np.newaxis, :, :, :]  # (1, 76, 32, 1)

    emb_out = emb_sess.run(None, {"input_1": emb_input})[0]      # (1, 1, 1, 96)
    return emb_out.flatten()                                       # (96,)


def load_wav(path: str) -> np.ndarray:
    audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    return audio.astype(np.float32)


def load_negative_samples(neg_dir: str, mel_sess, emb_sess) -> np.ndarray:
    wav_files = sorted(glob.glob(os.path.join(neg_dir, "*.wav")))
    print(f"[*] Завантажую {len(wav_files)} реальних негативних зразків з {neg_dir}...")
    feats = []
    for path in wav_files:
        try:
            audio = load_wav(path)
            emb = audio_to_embedding(audio, mel_sess, emb_sess)
            feats.append(emb)
        except Exception as e:
            print(f"  [!] {os.path.basename(path)}: {e}")
    return np.array(feats, dtype=np.float32)


def generate_negative_samples(mel_sess, emb_sess, n: int) -> np.ndarray:
    print(f"[*] Генерую {n} синтетичних негативних зразків (шум)...")
    negs = []
    for _ in range(n):
        noise = (np.random.randn(MIN_SAMPLES) * 0.01).astype(np.float32)
        emb = audio_to_embedding(noise, mel_sess, emb_sess)
        negs.append(emb)
    return np.array(negs, dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--word", required=True)
    parser.add_argument("--training-dir", default=None)
    parser.add_argument("--negative-dir", default=None,
                        help="папка з реальними негативними зразками (напр. wake_words/training/ultron_negative/)")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    word        = args.word.lower()
    train_dir   = args.training_dir or os.path.join("wake_words", "training", word)
    output_path = args.output or os.path.join("wake_words", f"hey_{word}.onnx")

    if not os.path.isdir(train_dir):
        print(f"[!] Папка не знайдена: {train_dir}")
        return

    wav_files = sorted(glob.glob(os.path.join(train_dir, "*.wav")))
    if len(wav_files) < 10:
        print(f"[!] Замало зразків: {len(wav_files)}")
        return

    print(f"[*] Знайдено {len(wav_files)} зразків у {train_dir}")
    mel_sess, emb_sess = load_sessions()

    # ── позитивні зразки ─────────────────────────────────────────────────────
    print("[*] Витягую embeddings з позитивних зразків...")
    pos_features = []
    for path in wav_files:
        try:
            audio = load_wav(path)
            emb = audio_to_embedding(audio, mel_sess, emb_sess)
            pos_features.append(emb)
        except Exception as e:
            print(f"  [!] {os.path.basename(path)}: {e}")

    if len(pos_features) == 0:
        print("[!] Жодного успішного зразка.")
        return

    pos_features = np.array(pos_features, dtype=np.float32)
    print(f"    → {len(pos_features)} успішно")

    # ── негативні зразки ─────────────────────────────────────────────────────
    neg_dir = args.negative_dir or os.path.join("wake_words", "training", f"{word}_negative")
    if os.path.isdir(neg_dir) and glob.glob(os.path.join(neg_dir, "*.wav")):
        real_negs = load_negative_samples(neg_dir, mel_sess, emb_sess)
        # додаємо синтетичний шум щоб збалансувати
        n_synth = max(len(pos_features) * 2, 50)
        synth_negs = generate_negative_samples(mel_sess, emb_sess, n_synth)
        neg_features = np.vstack([real_negs, synth_negs])
        print(f"    → реальних: {len(real_negs)}, синтетичних: {len(synth_negs)}")
    else:
        print(f"[!] Папка негативів не знайдена: {neg_dir}")
        print("[!] Використовую тільки синтетичний шум — якість може бути гірша.")
        n_neg = max(len(pos_features) * 3, 100)
        neg_features = generate_negative_samples(mel_sess, emb_sess, n_neg)

    X = np.vstack([pos_features, neg_features])
    y = np.array([1] * len(pos_features) + [0] * len(neg_features))

    # ── тренування ───────────────────────────────────────────────────────────
    print("[*] Тренування LogisticRegression...")
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("clf",    LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced"))
    ])
    clf.fit(X, y)
    print(f"    → accuracy: {clf.score(X, y):.3f}")

    # ── конвертація в ONNX ───────────────────────────────────────────────────
    print("[*] Конвертую в ONNX...")
    initial_type = [("float_input", FloatTensorType([None, EMBEDDING_DIM]))]
    onnx_model = convert_sklearn(clf, initial_types=initial_type, target_opset=12)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(onnx_model.SerializeToString())

    print(f"[+] Збережено: {output_path}")
    print(f"[+] Готово! Скажи '{word}' щоб активувати ULTRON режим.")


if __name__ == "__main__":
    main()