import re
import speech_recognition as sr
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from langdetect import detect, LangDetectException
import tempfile
import os
import time

recognizer = sr.Recognizer()

class SpeechListener:
    def __init__(self):
        self.fs = 16000
        self.silence_threshold = 0.01  # підібрано по реальному рівню мікрофона
        self.silence_duration = 0.8    # секунд тиші після мовлення
        self.silence_duration_initial = 1.5  # секунд тиші якщо ще не говорив
        self.min_record_duration = 0.8 # мінімум секунд перед перевіркою тиші
        self._recording_data = []

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[SpeechListener WARNING] {status}")
        self._recording_data.append(indata.copy())

    def listen(self) -> tuple[str | None, str]:
        """Повертає (текст, мова) — 'en' або 'uk'."""
        self._recording_data = []
        time.sleep(0.1)
        print("[LISTENING...]")

        try:
            with sd.InputStream(
                samplerate=self.fs,
                channels=1,
                callback=self._audio_callback,
                dtype='int16'
            ):
                silent_chunks = 0
                recorded_duration = 0.0
                has_spoken = False  # чи вже говорив користувач
                while True:
                    if self._recording_data:
                        latest_chunk = self._recording_data[-1]
                        recorded_duration += len(latest_chunk) / self.fs
                        volume_norm = (
                            np.linalg.norm(latest_chunk)
                            / np.sqrt(len(latest_chunk))
                            / 32768.0
                        )
                        if volume_norm >= self.silence_threshold:
                            has_spoken = True
                        # Не перевіряємо тишу поки не пройшов мінімальний час
                        if recorded_duration < self.min_record_duration:
                            time.sleep(0.05)
                            continue
                        # Адаптивний таймаут: якщо вже говорив — менше чекаємо
                        active_duration = self.silence_duration if has_spoken else self.silence_duration_initial
                        if volume_norm < self.silence_threshold:
                            silent_chunks += 1
                        else:
                            silent_chunks = 0
                        if silent_chunks > (self.fs / 1024 * active_duration):
                            print("[Тиша зафіксована]")
                            break
                    time.sleep(0.05)

            if not self._recording_data:
                return None, "en"

            audio_combined = np.concatenate(self._recording_data, axis=0)
            filename = tempfile.mktemp(suffix=".wav")

            try:
                write(filename, self.fs, audio_combined)
                with sr.AudioFile(filename) as source:
                    audio = recognizer.record(source)
                    try:
                        # Один запит en-US + langdetect для мови
                        user_text = recognizer.recognize_google(audio, language="en-US")
                        try:
                            detected = detect(user_text)
                            lang = "uk" if detected == "uk" else "en"
                        except LangDetectException:
                            lang = "en"

                        print(f">>> YOU ({lang.upper()}): {user_text}")
                        try:
                            from modules.hud_module import add_message
                            add_message("user", user_text)
                        except Exception: pass
                        return user_text, lang

                    except sr.UnknownValueError:
                        return None, "en"

            finally:
                if os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except Exception as e:
                        print(f"[SpeechListener] Не вдалось видалити файл: {e}")

        except Exception as e:
            print(f"[SpeechListener ERROR] {e}")
            return None, "en"


def _try_identify_speaker(listener_data: list) -> str | None:
    """Намагається ідентифікувати мовця по аудіо з _recording_data."""
    try:
        from voice_id_module import identify, list_enrolled
        if not list_enrolled():
            return None
        audio_np = np.concatenate(listener_data).flatten()
        name, score = identify(audio_np)
        return name
    except Exception:
        return None


def start_home_conversation(jarvis_brain, safe_speak_func, mode_callback=None):
    """HOME MODE — постійна сесія, закривається тільки по 'goodbye'."""
    listener = SpeechListener()
    print("[HOME MODE] Сесію активовано.")

    _fade_volume(jarvis_brain, target=20)

    while True:
        user_text, lang = listener.listen()

        # Тиша — НЕ закриваємо, просто слухаємо далі
        if not user_text:
            print("[HOME MODE] Тиша — слухаю далі...")
            continue

        # Ідентифікація мовця — тільки якщо є текст
        speaker = _try_identify_speaker(listener._recording_data)
        if speaker:
            print(f"[VOICE_ID] Мовець: {speaker}")
            try:
                from modules.hud_module import update_hud
                update_hud("speaker", speaker)
            except Exception:
                pass

        lower = user_text.lower()

        # Перемикання режимів
        if mode_callback:
            if any(p in lower for p in ["iron man mode", "switch to iron man", "activate iron man"]):
                mode_callback("iron man")
                _restore_volume(jarvis_brain)
                return
            if any(p in lower for p in ["ultron mode", "activate ultron", "switch to ultron", "режим альтрон"]):
                mode_callback("ultron")
                _restore_volume(jarvis_brain)
                return

        # Sleep mode
        if any(p in lower for p in ["sleep mode", "good night", "на ніч", "спати"]):
            safe_speak_func("Good night, Sir. Systems entering low-power mode.")
            _fade_volume(jarvis_brain, target=10)
            try:
                from modules.hud_module import socketio
                socketio.emit('state_update', {'sleep': True})
            except Exception:
                pass
            return

        # Завершення сесії тільки по "goodbye"
        exit_phrases = ["goodbye", "good bye", "до побачення", "вийди", "досить", "вільно"]
        if any(p in lower for p in exit_phrases):
            msg = "Як бажаєте, сер." if lang == "uk" else "Goodbye, Sir. Standing by."
            safe_speak_func(msg, lang)
            _restore_volume(jarvis_brain)
            return

        try:
            response = jarvis_brain.process(user_text, lang=lang)

            if response:
                clean_to_speak = re.sub(r'\[.*?\]', '', response).replace("/", " ").strip()
                if clean_to_speak:
                    safe_speak_func(clean_to_speak, lang)

        except Exception as e:
            print(f"[HOME MODE ERROR] {e}")
            safe_speak_func("Sir, there is an error.", "en")

        print("[HOME MODE] Слухаю далі...")


def start_ironman_conversation(jarvis_brain, safe_speak_func, mode_callback=None):
    """IRON MAN MODE — разова сесія, закривається по тиші."""
    listener = SpeechListener()
    print("[IRON MAN MODE] Діалог активовано.")

    silent_streak = 0
    max_silent = 2

    while True:
        user_text, lang = listener.listen()

        if not user_text:
            silent_streak += 1
            print(f"[IRON MAN MODE] Тиша {silent_streak}/{max_silent}")
            if silent_streak >= max_silent:
                print("[IRON MAN MODE] Сесія закрита по таймауту.")
                _restore_volume(jarvis_brain)
                break
            continue

        silent_streak = 0
        lower = user_text.lower()

        # Перемикання режимів
        if mode_callback:
            if any(p in lower for p in ["home mode", "switch to home"]):
                mode_callback("home")
                _restore_volume(jarvis_brain)
                return
            if any(p in lower for p in ["ultron mode", "activate ultron", "switch to ultron", "режим альтрон"]):
                mode_callback("ultron")
                _restore_volume(jarvis_brain)
                return

        # Sleep mode
        if any(p in lower for p in ["sleep mode", "good night", "на ніч", "спати"]):
            safe_speak_func("Good night, Sir. Systems entering low-power mode.")
            _fade_volume(jarvis_brain, target=10)
            try:
                from modules.hud_module import socketio
                socketio.emit('state_update', {'sleep': True})
            except Exception:
                pass
            return

        try:
            response = jarvis_brain.process(user_text, lang=lang)

            if response:
                res_upper = response.upper()
                clean = re.sub(r'\[.*?\]', '', response).replace("/", " ").strip()

                if clean:
                    safe_speak_func(clean, lang)

                if "[EXIT]" in res_upper:
                    _restore_volume(jarvis_brain)
                    break

        except Exception as e:
            print(f"[IRON MAN MODE ERROR] {e}")
            safe_speak_func("Sir, there was an error.", "en")
            _restore_volume(jarvis_brain)
            break

        print("[IRON MAN MODE] Слухаю далі...")


def _fade_volume(jarvis_brain, target: int, steps: int = 8, delay: float = 0.06):
    """Плавно змінює гучність до target за steps кроків."""
    try:
        current = jarvis_brain.music_module.sp.current_playback()
        if current and current.get("device"):
            start_vol = current["device"].get("volume_percent", 90)
        else:
            start_vol = 90
        step_size = (target - start_vol) / steps
        for i in range(steps):
            vol = int(start_vol + step_size * (i + 1))
            jarvis_brain.music_module.set_volume(vol)
            time.sleep(delay)
    except Exception:
        try:
            jarvis_brain.music_module.set_volume(target)
        except Exception as e:
            print(f"[DEBUG] Не вдалось змінити гучність: {e}")


def _restore_volume(jarvis_brain):
    _fade_volume(jarvis_brain, target=90)