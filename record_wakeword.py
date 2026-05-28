"""
record_wakeword.py — запис зразків wake word для тренування OpenWakeWord
Використання: python record_wakeword.py --word ultron --count 150
"""

import argparse
import os
import time
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write

SAMPLERATE = 16000
DURATION   = 1.5   # секунд на кожен запис
OUTPUT_DIR = "wake_words/training"


def record_sample(index: int, word: str) -> bool:
    print(f"\n[{index}] Скажи '{word}' (Enter щоб почати, 'q' щоб вийти): ", end="")
    inp = input().strip().lower()
    if inp == "q":
        return False

    print("  🔴 Запис...", end="", flush=True)
    audio = sd.rec(
        int(DURATION * SAMPLERATE),
        samplerate=SAMPLERATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    print(" ✓")

    out_dir = os.path.join(OUTPUT_DIR, word)
    os.makedirs(out_dir, exist_ok=True)
    filename = os.path.join(out_dir, f"{word}_{index:04d}.wav")
    write(filename, SAMPLERATE, audio)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--word",  default="ultron", help="Слово для запису")
    parser.add_argument("--count", type=int, default=150, help="Кількість зразків")
    parser.add_argument("--start", type=int, default=1, help="Починати з номера")
    args = parser.parse_args()

    print(f"=== Запис wake word: '{args.word}' ===")
    print(f"Буде записано {args.count} зразків по {DURATION}с кожен.")
    print("Поради:")
    print("  - Говори в різних тонах (тихіше, голосніше, швидше, повільніше)")
    print("  - Змінюй відстань від мікрофона")
    print("  - Роби паузи між записами")
    print("  - 'q' + Enter щоб зупинитись і продовжити пізніше\n")

    recorded = 0
    for i in range(args.start, args.start + args.count):
        if not record_sample(i, args.word):
            break
        recorded += 1

        if recorded % 25 == 0:
            print(f"\n  ✅ Записано {recorded}/{args.count} — можеш зробити паузу!\n")

    out_dir = os.path.join(OUTPUT_DIR, args.word)
    files = len([f for f in os.listdir(out_dir) if f.endswith(".wav")]) if os.path.exists(out_dir) else 0
    print(f"\n=== Готово! Записано: {recorded} зразків ===")
    print(f"Всього у папці: {files} файлів")
    print(f"Шлях: {os.path.abspath(out_dir)}")
    print("\nНаступний крок: python train_wakeword.py --word ultron")


if __name__ == "__main__":
    main()
