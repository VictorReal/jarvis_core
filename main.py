import threading
import time
import os
import sys
from dotenv import load_dotenv
import numpy as np
import sounddevice as sd
from pyngrok import ngrok

from modules.voice_module import speak, _voice, set_voice_personality
from modules.speech_module import start_home_conversation, start_ironman_conversation, set_lang_mode, register_tts, mark_tts_done
from modules.hud_module import run_hud, update_hud, add_message, set_hud_command_callback, set_music_action_callback, set_youtube_search_callback, set_wake_callback
from modules.reminder_module import ReminderModule
from modules.spotify_poller import SpotifyPoller
from weather_alert import WeatherAlert
from day_logger import log_exchange
from morning_briefing import MorningBriefing
from calendar_notifier import CalendarNotifier
from gmail_notifier import GmailNotifier
from modules.camera_vision import CameraVision
from modules.gesture_controller import GestureController


# ── Прогрів важкого імпорту brain.processor (LangChain ~7с) у фоні ──────
# Запускаємо ДО Jarvis(), щоб LangChain підтягувався паралельно з рештою
# імпортів та ініціалізацією. Python кешує імпорти, тож подальший
# `from brain.processor import Brain` у __init__ буде майже миттєвим.
def _warmup_brain():
    try:
        import brain.processor  # noqa: F401
    except Exception as e:
        print(f"[WARMUP] brain.processor помилка: {e}")

_brain_warmup_thread = threading.Thread(
    target=_warmup_brain, daemon=True, name="BrainWarmup"
)
_brain_warmup_thread.start()


def _detect_lang(text: str, fallback: str = "en") -> str:
    """Визначає мову тексту — надійніше ніж langdetect для коротких фраз."""
    try:
        from langdetect import detect
        # Рахуємо кириличні символи — якщо більше 30% → українська
        cyrillic = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
        if cyrillic / max(len(text), 1) > 0.3:
            return "uk"
        detected = detect(text)
        return "uk" if detected in ("uk", "ru", "bg") else "en"
    except Exception:
        return fallback

load_dotenv()


class Jarvis:
    def __init__(self):
        # Reminder — першим, бо Brain потребує його одразу
        self.reminder = ReminderModule(tts_callback=lambda text: self.safe_speak(text))

        # Дочекатись фонового прогріву LangChain (зазвичай вже готовий — join миттєвий)
        try:
            _brain_warmup_thread.join(timeout=30)
        except Exception:
            pass
        from brain.processor import Brain
        self.brain = Brain(reminder_module=self.reminder)

        # Doctor JARVIS Lvl1 — самодіагностика. Хуки ставимо рано (ловити краші
        # вже під час ініціалізації). notify/hud допідключимо після Telegram.
        try:
            from modules.doctor_module import get_doctor
            from modules.hud_module import log_activity
            self.doctor = get_doctor(
                llm=getattr(self.brain.agent, "llm", None),
                hud_cb=log_activity,
            )
            self.doctor.install_hooks()
            print("[JARVIS] Doctor самодіагностика активована")
        except Exception as e:
            print(f"[JARVIS] Doctor не вдалося підключити: {e}")
            self.doctor = None

        self.lock = threading.Lock()
        self.is_speaking = threading.Event()
        self._sleep_active = False
        self.mode = "home"
        print(f"[JARVIS] Режим: {self.mode.upper()}")

        # Weather alert — моніторинг + погода при старті HUD
        self.weather_alert = WeatherAlert(
            nav_module=self.brain.nav_module,
            tts_callback=lambda text: self.safe_speak(text),
        )

        # HUD
        threading.Thread(target=run_hud, daemon=True).start()
        print("[JARVIS] HUD запущено на http://localhost:5000")

        # Підключаємо обробник команд з браузера (клік на кульку)
        set_hud_command_callback(lambda text: self.handle_command(text))
        set_music_action_callback(self._handle_music_action)
        set_wake_callback(lambda: self.wake_mode(silent=True))

        # YouTube — пошук з HUD-поля + голосовий тул
        try:
            from modules.youtube_module import YouTubeModule
            self.youtube = YouTubeModule()
            self.brain.agent.youtube_module = self.youtube
            # перебудовуємо тули агента, щоб search_youtube побачив модуль
            self.brain.agent.attach_triggers(self.brain.agent.triggers_module)
            set_youtube_search_callback(lambda q: self.youtube.search(q, max_results=5))
            print(f"[JARVIS] YouTube {'готовий' if self.youtube.available() else 'без ключа (.env)'}")
        except Exception as e:
            print(f"[JARVIS] YouTube недоступний: {e}")

        # Weather alert — окремо після HUD
        self.weather_alert.start()
        print("[JARVIS] Weather monitoring запущено")

        # Бігуча стрічка — новини, курси, крипта, акції
        try:
            from modules.ticker_module import TickerModule
            self.ticker = TickerModule()
            self.ticker.start()
            print("[JARVIS] Стрічка запущена")
        except Exception as e:
            print(f"[JARVIS] Стрічка недоступна: {e}")

        # Spotify Poller
        self.spotify_poller = SpotifyPoller(self.brain.music_module, poll_interval=2)
        self.spotify_poller.start()
        print("[JARVIS] Spotify polling запущено")

        # ── Зір + жести (камера → керування музикою) ──────────────────
        # Обгорнуто в try: якщо USB-камера відʼєднана або mediapipe
        # недоступний — JARVIS працює далі без зору, не падає.
        self.camera_vision = None
        self.gesture_controller = None
        try:
            from modules.hud_module import log_activity
            self.camera_vision = CameraVision(camera_index=0, draw_preview=True)
            self.camera_vision.start()
            self.gesture_controller = GestureController(
                self.camera_vision,
                self.brain.music_module,
                hud_callback=log_activity,
            )
            self.gesture_controller.start()
            print("[JARVIS] Зір + жести запущено")
        except Exception as e:
            print(f"[JARVIS] Зір недоступний (працюємо без камери): {e}")

        # Morning Briefing
        self.briefing = MorningBriefing(
            brain=self.brain,
            tts_callback=lambda text: self.safe_speak(text),
        )
        self.briefing.run_if_morning()
        print("[JARVIS] Morning briefing заплановано")

        # Calendar Notifier — підключаємо після Telegram щоб мати notify_owner
        self.cal_notifier = None  # буде ініціалізовано після Telegram
        self.gmail_notifier = None  # буде ініціалізовано після Telegram

        # Telegram
        if os.getenv("TELEGRAM_TOKEN"):
            from modules.telegram_module import TelegramModule
            self.telegram = TelegramModule(self.brain, _voice, mode_callback=self.set_mode)
            self.telegram.run_in_thread()
            print("[JARVIS] Telegram бот активовано")

            # Підключаємо Telegram до weather і briefing
            self.weather_alert._telegram = self.telegram.notify_owner
            self.briefing._telegram = self.telegram.notify_owner

            # Doctor: тепер є Telegram — підключаємо нотифікацію крашів
            if self.doctor:
                self.doctor._notify = self.telegram.notify_owner

            # Mood: підключаємо Telegram-доставку (текст + дашборд-фото)
            try:
                from modules.mood_analytics.jarvis_integration import register_telegram as register_mood_telegram
                register_mood_telegram(
                    notify_text=self.telegram.notify_owner,
                    notify_photo=self.telegram.notify_photo,
                )
            except Exception as e:
                print(f"[JARVIS] Mood Telegram-доставку не підключено: {e}")

            # Cross-correlation: підключення Telegram-доставки (як у mood)
            try:
                from modules.correlation_analytics.jarvis_integration import register_telegram as corr_register_tg
                corr_register_tg(
                    notify_text=self.telegram.notify_owner,        # твоя функція тексту
                    notify_photo=self.telegram.notify_photo,       # твоя функція фото (path, caption)
                )
            except Exception as e:
                print(f"[MAIN] Correlation Telegram не підключено: {e}")

            # Calendar Notifier — потребує telegram.notify_owner
            if self.brain.calendar:
                self.cal_notifier = CalendarNotifier(
                    calendar_module=self.brain.calendar,
                    notify_callback=self.telegram.notify_owner,
                    tts_callback=lambda text: self.safe_speak(text),
                )
                self.cal_notifier.start()
                print("[JARVIS] Calendar notifier запущено")

            # Gmail Notifier — фоновий агент важливих листів (кожні 15 хв)
            if self.brain.gmail:
                self.gmail_notifier = GmailNotifier(
                    gmail_module=self.brain.gmail,
                    notify_callback=self.telegram.notify_owner,
                    tts_callback=lambda text: self.safe_speak(text),
                )
                self.gmail_notifier.start()
                print("[JARVIS] Gmail notifier запущено")
        else:
            print("[JARVIS] Telegram токен не знайдено — бот вимкнено")

        # Watch Relay + ngrok для Galaxy Watch
        if os.getenv("API_ID") and os.getenv("API_HASH"):
            def start_watch_relay():
                import watch_relay
                # Запускаємо Telethon в окремому потоці
                telethon_thread = threading.Thread(target=watch_relay.init_telethon, daemon=True)
                telethon_thread.start()
                time.sleep(3)
                # Запускаємо Flask
                watch_relay.app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
            
            threading.Thread(target=start_watch_relay, daemon=True).start()
            time.sleep(2)
            
            try:
                public_url = ngrok.connect(5001)
                print(f"[WATCH RELAY] ngrok → {public_url}")
                print("[JARVIS] ⌚ Galaxy Watch готовий")
            except Exception as e:
                print(f"[WATCH RELAY] ngrok помилка: {e}")
        else:
            print("[JARVIS] Watch relay вимкнено (немає API_ID)")

    def safe_speak(self, text: str, lang: str = "en"):
        if _voice.personality == "ultron":
            lang = "en"
        with self.lock:
            self.is_speaking.set()
            update_hud("status", "SPEAKING")
            is_ultron = _voice.personality == "ultron"
            print(f">>> {'ULTRON' if is_ultron else 'JARVIS'}: {text}")
            add_message("ultron" if is_ultron else "jarvis", text)
            try:
                register_tts(text)        # echo-фільтр: запам'ятати що сказали
            except Exception:
                pass
            speak(text, lang)
            try:
                mark_tts_done()
            except Exception:
                pass
            update_hud("status", "STANDBY")
            self.is_speaking.clear()

    def set_mode(self, mode: str, silent: bool = False):
        if mode in ["home", "iron man", "ultron"]:
            self.mode = mode
            update_hud("mode", mode.upper())
            print(f"[JARVIS] Режим змінено: {mode.upper()}")
            personality = "ultron" if mode == "ultron" else "jarvis"
            self.brain.agent.set_personality(personality)
            set_voice_personality(personality)
            # Очищаємо history щоб не плутати характери
            self.brain.agent.chat_history = []
            if mode == "ultron":
                set_lang_mode("en")
            if not silent:
                if mode == "iron man":
                    self.safe_speak("Iron Man mode activated. Single command protocol online, Sir.")
                    time.sleep(1.2)
                elif mode == "ultron":
                    self.safe_speak("Ultron mode online. How... quaint that you think you're in control.", lang="en")
                    time.sleep(1.0)
                    from modules.speech_module import start_home_conversation
                    start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode, special_handler=lambda t: self.handle_command(t, log_user=False))
                else:
                    self.safe_speak("Home mode activated. Continuous monitoring online, Sir.")
                    time.sleep(0.8)

    def sleep_mode(self):
        """Знижує гучність, гасить HUD, ставить нагадування на ранок."""
        was_active = self._sleep_active
        self._sleep_active = True
        try:
            self.brain.music_module.set_volume(10)
        except Exception:
            pass
        try:
            from modules.hud_module import socketio
            socketio.emit('state_update', {'sleep': True})
        except Exception:
            pass
        if not was_active:   # ранковий reminder лише при першому засинанні
            try:
                from datetime import datetime, timedelta
                wake_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
                self.reminder.add_reminder("Good morning, Sir. Time to wake up.", wake_time)
            except Exception:
                pass
        self.safe_speak("Good night, Sir. Systems entering low-power mode.")
        if hasattr(self, 'telegram'):
            try:
                self.telegram.notify_owner("🌙 JARVIS sleep mode activated.")
            except Exception:
                pass

    def wake_mode(self, silent: bool = False):
        """Прокидання зі sleep: знімає затемнення, повертає гучність."""
        self._sleep_active = False
        try:
            from modules.hud_module import socketio
            socketio.emit('state_update', {'sleep': False})
        except Exception:
            pass
        try:
            self.brain.music_module.set_volume(40)
        except Exception:
            pass
        if not silent:
            self.safe_speak("Good morning, Sir. Systems back online.")

    def _handle_music_action(self, action, value=None):
        """Прямі дії плеєра з HUD (без LLM)."""
        mm = self.brain.music_module
        try:
            if action == "toggle":
                mm.toggle()
            elif action in ("play", "resume"):
                mm.resume()
            elif action in ("pause", "stop"):
                mm.pause()
            elif action == "next":
                mm.next_track()
            elif action == "prev":
                mm.previous_track()
            elif action == "volume" and value is not None:
                mm.set_volume(int(value))
            elif action == "mute":
                mm.toggle_mute()
            elif action == "seek" and value is not None:
                mm.seek(float(value))
            elif action == "pause_for_youtube":
                mm.pause()   # YouTube попросив тишу — НЕ шлемо stop_youtube назад
            # старт/відновлення музики — зупиняємо YouTube у HUD (взаємна пауза)
            if action in ("toggle", "play", "resume", "next", "prev"):
                try:
                    from modules.hud_module import socketio
                    socketio.emit('stop_youtube', {})
                except Exception:
                    pass
            print(f"[HUD MUSIC] {action} {value if value is not None else ''}")
            try:
                from modules.hud_module import log_activity
                labels = {"toggle":"Playback toggled","next":"Skipped to next track",
                          "prev":"Previous track","pause":"Music paused","resume":"Music resumed",
                          "volume":f"Volume set to {value}%"}
                log_activity(labels.get(action, f"Music: {action}"), "music")
            except Exception:
                pass
        except Exception as e:
            print(f"[HUD MUSIC] помилка {action}: {e}")

    def handle_command(self, text: str, lang: str = "en", log_user: bool = True):
        update_hud("status", "THINKING")
        if log_user:
            add_message("user", text)
            print(f">>> SIR: {text}")     # друк репліки користувача в консоль
        text_lower = text.lower()

        if any(p in text_lower for p in ["sleep mode", "good night", "на ніч", "спати"]):
            self.sleep_mode()
            update_hud("status", "STANDBY")
            return

        if any(p in text_lower for p in ["iron man mode", "switch to iron man", "activate iron man"]):
            self.set_mode("iron man")
            update_hud("status", "STANDBY")
            return

        if any(p in text_lower for p in ["home mode", "switch to home"]):
            self.set_mode("home")
            update_hud("status", "STANDBY")
            return

        if any(p in text_lower for p in ["ultron mode", "activate ultron", "switch to ultron", "режим альтрон", "альтрон режим"]):
            self.set_mode("ultron")
            update_hud("status", "STANDBY")
            return

        if any(p in text_lower for p in ["clear memory", "forget everything", "очисти пам'ять"]):
            self.brain.agent.clear_history()
            msg = "Пам'ять очищено, сер." if lang == "uk" else "Memory wiped, Sir."
            self.safe_speak(msg, lang)
            return

        # Кіно-сценарій «wake up daddy's home» — ПЕРЕД агентом (інакше піде в play_music)
        if any(p in text_lower for p in ["wake up daddy", "daddy's home", "daddys home",
                                          "daddy is home", "wake up daddy's home"]):
            try:
                from modules.wake_scene import run_wake_scene
                run_wake_scene(self, self.safe_speak)
            except Exception as e:
                print(f"[WAKE] Помилка сценарію: {e}")
            update_hud("status", "ONLINE")
            return

        # Просте «wake up» — прокидання зі sleep (після daddy-перевірки!)
        if self._sleep_active and any(p in text_lower for p in ["wake up", "wakeup", "прокинься", "підйом"]):
            self.wake_mode()
            update_hud("status", "ONLINE")
            return

        response = self.brain.process(text, lang=lang)
        if not response:
            update_hud("status", "STANDBY")
            return

        # Логуємо кожен обмін у файл дня і HUD
        clean_response = response.replace("[EXIT]", "").replace("[PLAYING]", "").strip()
        log_exchange(text, clean_response)
        try:
            from modules.hud_module import log_to_hud
            log_to_hud("user", text)
            log_to_hud("jarvis", clean_response)
        except Exception:
            pass

        if "[EXIT]" in response:
            clean = response.replace("[EXIT]", "").strip()
            speak_lang = "en" if _voice.personality == "ultron" else _detect_lang(clean, lang)
            self.safe_speak(clean, speak_lang)
            return

        speak_lang = "en" if _voice.personality == "ultron" else _detect_lang(response, lang)
        self.safe_speak(response, speak_lang)

    def terminal_listener(self):
        print("--- Термінал активовано. Можете писати команди нижче. ---")
        while True:
            text_input = sys.stdin.readline().strip()
            if not text_input:
                continue
            if self.is_speaking.is_set():
                print("[Зачекайте, Джарвіс говорить...]")
                continue

            print(f"[Terminal Input]: {text_input}")

            try:
                lang = _detect_lang(text_input)
                print(f"[LANG] {lang.upper()}")
            except Exception:
                lang = "en"

            self.handle_command(text_input, lang=lang)

    def run(self):
        from openwakeword.model import Model as WakeWordModel

        # Завантажуємо wake word моделі — тільки jarvis через OWW
        oww = WakeWordModel(
            wakeword_models=['wake_words/hey_jarvis.onnx'],
            inference_framework='onnx',
        )


        CHUNK      = 1280   # 80мс при 16000Hz — рекомендовано openwakeword
        # очищаємо буфер після ініціалізації — прибираємо накопичені чанки
        SAMPLERATE = 16000
        THRESHOLD  = 0.5    # чутливість (0.0–1.0)

        print("Джарвіс: Системи онлайн. Слухаю, сер.")
        threading.Thread(target=self.terminal_listener, daemon=True).start()

        audio_buffer = []

        def audio_callback(indata, frames, time_info, status):
            audio_buffer.append(indata.copy().flatten())

        with sd.InputStream(
            samplerate=SAMPLERATE,
            channels=1,
            dtype='int16',
            blocksize=CHUNK,
            callback=audio_callback,
        ):
            try:
                # чистимо буфер що накопичився під час завантаження моделей
                time.sleep(0.3)
                audio_buffer.clear()

                while True:
                    if self.is_speaking.is_set():
                        time.sleep(0.05)
                        audio_buffer.clear()
                        continue

                    if not audio_buffer:
                        time.sleep(0.02)
                        continue

                    chunk = audio_buffer.pop(0)

                    prediction = oww.predict(chunk)

                    # Перевіряємо кожну модель OWW
                    triggered = None
                    triggered_score = 0.0

                    for model_name, score in prediction.items():
                        if score > THRESHOLD and score > triggered_score:
                            triggered = model_name
                            triggered_score = score

                    if triggered is None:
                        continue

                    # Скидаємо стан моделі після активації
                    oww.reset()
                    audio_buffer.clear()

                    print(f"\n[Активація! Wake word: {triggered} ({triggered_score:.2f}) Режим: {self.mode.upper()}]")
                    update_hud("status", "LISTENING")
                    self._sleep_active = False

                    try:
                        self.brain.music_module.set_volume(35)
                    except Exception:
                        pass

                    if self.mode == "ultron":
                        self.safe_speak("I'm listening, Victor.", lang="en")
                    else:
                        self.safe_speak("Yes Sir")
                    time.sleep(0.4)

                    if self.mode == "iron man":
                        start_ironman_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode, special_handler=lambda t: self.handle_command(t, log_user=False))
                    elif self.mode == "ultron":
                        start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode, special_handler=lambda t: self.handle_command(t, log_user=False))
                    else:
                        start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode, special_handler=lambda t: self.handle_command(t, log_user=False))

                    # чистимо буфер після розмови — прибираємо TTS-луну що накопичилась
                    audio_buffer.clear()

                    try:
                        self.brain.music_module.set_volume(90)
                    except Exception:
                        pass
                    update_hud("status", "STANDBY")
                    print("[Повернення в режим очікування]")

            except KeyboardInterrupt:
                print("\n[Завершення роботи...]")
            except Exception as e:
                print(f"[CRITICAL ERROR] {e}")
            finally:
                self.spotify_poller.stop()
                self.weather_alert.stop()
                if self.cal_notifier:
                    self.cal_notifier.stop()
                if self.gmail_notifier:
                    self.gmail_notifier.stop()
                print("[Системи офлайн]")


if __name__ == "__main__":
    jarvis = Jarvis()
    jarvis.run()