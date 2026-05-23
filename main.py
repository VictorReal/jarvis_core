import threading
import pvporcupine
from pvrecorder import PvRecorder
import time
import os
import sys
from dotenv import load_dotenv

from modules.voice_module import speak, _voice, set_voice_personality
from modules.speech_module import start_home_conversation, start_ironman_conversation, set_lang_mode
from modules.hud_module import run_hud, update_hud, add_message, set_hud_command_callback
from modules.reminder_module import ReminderModule
from modules.spotify_poller import SpotifyPoller
from weather_alert import WeatherAlert
from day_logger import log_exchange
from morning_briefing import MorningBriefing
from calendar_notifier import CalendarNotifier


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
ACCESS_KEY = os.getenv("ACCESS_KEY")


class Jarvis:
    def __init__(self):
        # Reminder — першим, бо Brain потребує його одразу
        self.reminder = ReminderModule(tts_callback=lambda text: self.safe_speak(text))

        from brain.processor import Brain
        self.brain = Brain(reminder_module=self.reminder)

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

        # Weather alert — окремо після HUD
        self.weather_alert.start()
        print("[JARVIS] Weather monitoring запущено")

        # Spotify Poller
        self.spotify_poller = SpotifyPoller(self.brain.music_module, poll_interval=2)
        self.spotify_poller.start()
        print("[JARVIS] Spotify polling запущено")

        # Morning Briefing
        self.briefing = MorningBriefing(
            brain=self.brain,
            tts_callback=lambda text: self.safe_speak(text),
        )
        self.briefing.run_if_morning()
        print("[JARVIS] Morning briefing заплановано")

        # Calendar Notifier — підключаємо після Telegram щоб мати notify_owner
        self.cal_notifier = None  # буде ініціалізовано після Telegram

        # Telegram
        if os.getenv("TELEGRAM_TOKEN"):
            from modules.telegram_module import TelegramModule
            self.telegram = TelegramModule(self.brain, _voice, mode_callback=self.set_mode)
            self.telegram.run_in_thread()
            print("[JARVIS] Telegram бот активовано")

            # Підключаємо Telegram до weather і briefing
            self.weather_alert._telegram = self.telegram.notify_owner
            self.briefing._telegram = self.telegram.notify_owner

            # Calendar Notifier — потребує telegram.notify_owner
            if self.brain.calendar:
                self.cal_notifier = CalendarNotifier(
                    calendar_module=self.brain.calendar,
                    notify_callback=self.telegram.notify_owner,
                    tts_callback=lambda text: self.safe_speak(text),
                )
                self.cal_notifier.start()
                print("[JARVIS] Calendar notifier запущено")
        else:
            print("[JARVIS] Telegram токен не знайдено — бот вимкнено")

    def safe_speak(self, text: str, lang: str = "en"):
        if _voice.personality == "ultron":
            lang = "en"
        with self.lock:
            self.is_speaking.set()
            update_hud("status", "SPEAKING")
            is_ultron = _voice.personality == "ultron"
            print(f">>> {'ULTRON' if is_ultron else 'JARVIS'}: {text}")
            add_message("ultron" if is_ultron else "jarvis", text)
            speak(text, lang)
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
                    start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode)
                else:
                    self.safe_speak("Home mode activated. Continuous monitoring online, Sir.")
                    time.sleep(0.8)

    def sleep_mode(self):
        """Знижує гучність, гасить HUD, ставить нагадування на ранок."""
        if self._sleep_active:
            return
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

    def handle_command(self, text: str, lang: str = "en"):
        update_hud("status", "THINKING")
        add_message("user", text)
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
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keywords=['jarvis']
        )
        recorder = PvRecorder(frame_length=porcupine.frame_length)

        print("Джарвіс: Системи онлайн. Слухаю, сер.")
        threading.Thread(target=self.terminal_listener, daemon=True).start()

        try:
            while True:
                if self.is_speaking.is_set():
                    time.sleep(0.1)
                    continue

                if not recorder.is_recording:
                    recorder.start()

                pcm = recorder.read()

                if porcupine.process(pcm) >= 0:
                    self._sleep_active = False
                    print(f"\n[Активація! Режим: {self.mode.upper()}]")
                    recorder.stop()
                    update_hud("status", "LISTENING")

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
                        start_ironman_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode)
                    elif self.mode == "ultron":
                        start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode)
                    else:
                        start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode)

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
            recorder.delete()
            porcupine.delete()
            print("[Системи офлайн]")


if __name__ == "__main__":
    jarvis = Jarvis()
    jarvis.run()