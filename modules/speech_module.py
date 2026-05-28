import re
import threading
import speech_recognition as sr
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from langdetect import detect, LangDetectException
import tempfile
import os
import time

# Глушимо HTTP-помилки spotipy (виводяться навіть коли ми ловимо exception)
try:
    import logging
    logging.getLogger('spotipy').setLevel(logging.CRITICAL)
except Exception:
    pass

recognizer = sr.Recognizer()

# Мовний режим STT — "en" за замовчуванням, "uk" тільки по команді
_lang_mode = "en"


def set_lang_mode(lang: str):
    global _lang_mode
    _lang_mode = lang
    print(f"[SPEECH] Мовний режим: {lang.upper()}")


# === Самовідлуння: стан TTS і фільтр ===
_tts_lock = threading.Lock()
_tts_active = False  # True поки JARVIS говорить
_recent_tts: list[tuple[str, float]] = []  # (нормалізований текст, час)


def _normalize_for_echo(text: str) -> str:
    """Нижній регістр + без пунктуації — для порівняння."""
    return re.sub(r'[^\w\s]', '', text.lower()).strip()


def _register_tts(text: str):
    """Реєструє нову фразу TTS і піднімає прапор активності."""
    global _tts_active
    with _tts_lock:
        _tts_active = True
        norm = _normalize_for_echo(text)
        if norm:
            _recent_tts.append((norm, time.time()))
            if len(_recent_tts) > 5:
                _recent_tts.pop(0)


def _mark_tts_done():
    """TTS закінчив — мікрофон знову вільний."""
    global _tts_active
    with _tts_lock:
        _tts_active = False


def _wait_while_tts():
    """Блокує доки JARVIS говорить."""
    while True:
        with _tts_lock:
            if not _tts_active:
                return
        time.sleep(0.05)


def _is_echo(recognized: str) -> bool:
    """Чи це наше власне відлуння (страховка після STT)."""
    if not recognized:
        return False
    norm = _normalize_for_echo(recognized)
    if len(norm) < 8:  # короткі фрази не фільтруємо
        return False
    now = time.time()
    with _tts_lock:
        active = [(t, ts) for t, ts in _recent_tts if now - ts < 5]
    norm_words = set(norm.split())
    for tts_text, _ in active:
        # recognized — шматок нашої TTS
        if norm in tts_text:
            return True
        # або >=70% слів збігаються (для STT-помилок типу retrieved→retreat)
        tts_words = set(tts_text.split())
        if len(norm_words) >= 3 and len(tts_words) >= 3:
            common = norm_words & tts_words
            if len(common) / len(norm_words) >= 0.7:
                return True
    return False


def make_echo_aware(speak_func):
    """Обгортка TTS: піднімає прапор + реєструє фразу + хвіст 0.25с."""
    if getattr(speak_func, '_echo_aware', False):
        return speak_func  # вже обгорнуто — не дубліюємо
    def wrapped(text, lang):
        _register_tts(text)
        try:
            return speak_func(text, lang)
        finally:
            time.sleep(0.25)  # буфер на акустичний хвіст
            _mark_tts_done()
    wrapped._echo_aware = True
    return wrapped


class SpeechListener:
    def __init__(self):
        self.fs = 16000
        self.silence_threshold = 0.004  # знижено: ловить тихий голос
        self.silence_duration = 0.8     # секунд тиші після мовлення
        self.silence_duration_initial = 1.5
        self.min_record_duration = 0.8
        self._recording_data = []

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[SpeechListener WARNING] {status}")
        self._recording_data.append(indata.copy())

    def listen(self) -> tuple[str | None, str]:
        """Повертає (текст, мова) — 'en' або 'uk'."""
        _wait_while_tts()  # не пишемо поки JARVIS говорить
        self._recording_data = []
        time.sleep(0.3)  # буфер на акустичний хвіст
        print("[LISTENING...]")
        try:
            from modules.hud_module import update_hud
            update_hud("status", "LISTENING")
        except Exception:
            pass

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
                # нормалізуємо гучність — підсилюємо тихий голос перед STT
                audio_float = audio_combined.astype(np.float32)
                peak = np.max(np.abs(audio_float))
                if peak > 0 and peak < 16384:  # тихий запис — підсилюємо
                    audio_combined = np.clip(audio_float * (16384 / peak), -32768, 32767).astype(np.int16)
                write(filename, self.fs, audio_combined)
                with sr.AudioFile(filename) as source:
                    audio = recognizer.record(source)
                    try:
                        if _lang_mode == "uk":
                            user_text = recognizer.recognize_google(audio, language="uk-UA")
                            lang = "uk"
                        else:
                            user_text = recognizer.recognize_google(audio, language="en-US")
                            lang = "en"

                        # страховка: чи це наше власне відлуння
                        if _is_echo(user_text):
                            print(f"[ECHO FILTERED] '{user_text}'")
                            return None, _lang_mode

                        print(f">>> YOU ({lang.upper()}): {user_text}")
                        try:
                            from modules.hud_module import add_message
                            add_message("user", user_text)
                        except Exception: pass
                        return user_text, lang

                    except sr.UnknownValueError:
                        return None, _lang_mode

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
    """HOME MODE — постійна сесія (HOME або ULTRON), закривається тільки по 'goodbye'."""
    safe_speak_func = make_echo_aware(safe_speak_func)  # фільтр самовідлуння
    listener = SpeechListener()
    mode_label = (getattr(jarvis_brain, 'personality', None)
                  or getattr(jarvis_brain, 'mode', None)
                  or 'HOME')
    mode_label = str(mode_label).upper()
    print(f"[{mode_label} MODE] Сесію активовано.")

    _fade_volume(jarvis_brain, target=20)

    while True:
        user_text, lang = listener.listen()

        # Тиша — НЕ закриваємо, просто слухаємо далі
        if not user_text:
            print(f"[{mode_label} MODE] Тиша — слухаю далі...")
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

        # Перемикання режимів — тільки явні команди, не відлуння
        if mode_callback:
            if any(p in lower for p in ["switch to iron man", "activate iron man", "iron man mode"]):
                if not lower.startswith("iron man mode activated"):  # ігноруємо відлуння
                    mode_callback("iron man")
                    _restore_volume(jarvis_brain)
                    return
            # На HOME/JARVIS повертаємось тільки якщо ми НЕ в HOME (тобто з ULTRON)
            if mode_label != "HOME" and any(p in lower for p in
                    ["switch to home", "switch to jarvis", "home mode", "jarvis mode",
                     "режим джарвіс", "режим хоум"]):
                if not lower.startswith("home mode activated"):
                    mode_callback("home")
                    _restore_volume(jarvis_brain)
                    return
            # У ULTRON переходимо тільки якщо ми НЕ в ULTRON
            if mode_label != "ULTRON" and any(p in lower for p in
                    ["switch to ultron", "activate ultron", "ultron mode", "режим альтрон"]):
                if not lower.startswith("ultron mode online"):
                    mode_callback("ultron")
                    _restore_volume(jarvis_brain)
                    return

        # Завершення сесії тільки по "goodbye"
        exit_phrases = ["goodbye", "good bye", "до побачення", "вийди", "досить", "вільно"]
        if any(p in lower for p in exit_phrases):
            msg = "Як бажаєте, сер." if lang == "uk" else "Goodbye, Sir. Standing by."
            safe_speak_func(msg, lang)
            _restore_volume(jarvis_brain)
            return

        try:
            try:
                from modules.hud_module import update_hud
                update_hud("status", "THINKING")
            except Exception:
                pass

            response = jarvis_brain.process(user_text, lang=lang)

            if response:
                clean_to_speak = re.sub(r'\[.*?\]', '', response).replace("/", " ").strip()
                if clean_to_speak:
                    safe_speak_func(clean_to_speak, lang)

        except Exception as e:
            print(f"[{mode_label} MODE ERROR] {e}")
            safe_speak_func("Sir, there is an error.", "en")
        finally:
            try:
                from modules.hud_module import update_hud
                update_hud("status", "STANDBY")
            except Exception:
                pass

        print(f"[{mode_label} MODE] Слухаю далі...")


def start_ironman_conversation(jarvis_brain, safe_speak_func, mode_callback=None):
    """IRON MAN MODE — разова сесія, закривається по тиші."""
    safe_speak_func = make_echo_aware(safe_speak_func)  # фільтр самовідлуння
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

        # Перемикання режимів — тільки явні команди, не відлуння
        if mode_callback:
            if any(p in lower for p in ["switch to home", "home mode", "switch to jarvis",
                                         "режим джарвіс", "режим хоум"]):
                if not lower.startswith("home mode activated"):  # ігноруємо відлуння
                    mode_callback("home")
                    _restore_volume(jarvis_brain)
                    return
            if any(p in lower for p in ["switch to ultron", "activate ultron", "ultron mode", "режим альтрон"]):
                if not lower.startswith("ultron mode online"):
                    mode_callback("ultron")
                    _restore_volume(jarvis_brain)
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


# Блеклист пристроїв, що не дозволяють керувати гучністю (timestamp до якого не пробуємо)
_volume_blocked_until = 0.0


def _fade_volume(jarvis_brain, target: int, steps: int = 8, delay: float = 0.06):
    global _volume_blocked_until
    if time.time() < _volume_blocked_until:
        return  # пристрій неконтрольований — не пробуємо
    try:
        current = jarvis_brain.music_module.sp.current_playback()
        if not current or not current.get("device"):
            return  # нічого не грає — нема що міняти
        start_vol = current["device"].get("volume_percent", 90)
        step_size = (target - start_vol) / steps
        for i in range(steps):
            vol = int(start_vol + step_size * (i + 1))
            try:
                jarvis_brain.music_module.set_volume(vol)
            except Exception:
                # 403 / device unavailable — блекаємо на 5 хв, цикл стоп
                _volume_blocked_until = time.time() + 300
                return
            time.sleep(delay)
    except Exception:
        pass


def _restore_volume(jarvis_brain):
    _fade_volume(jarvis_brain, target=90)