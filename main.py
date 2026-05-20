import threading
import pvporcupine
from pvrecorder import PvRecorder
import time
import os
import sys
from dotenv import load_dotenv

from modules.voice_module import speak, _voice
from modules.speech_module import start_home_conversation, start_ironman_conversation
from modules.hud_module import run_hud, update_hud, add_message
from modules.reminder_module import ReminderModule
from modules.spotify_poller import SpotifyPoller
from weather_alert import WeatherAlert
from day_logger import log_exchange
from morning_briefing import MorningBriefing

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

        # Telegram
        if os.getenv("TELEGRAM_TOKEN"):
            from modules.telegram_module import TelegramModule
            self.telegram = TelegramModule(self.brain, _voice, mode_callback=self.set_mode)
            self.telegram.run_in_thread()
            print("[JARVIS] Telegram бот активовано")
        else:
            print("[JARVIS] Telegram токен не знайдено — бот вимкнено")

    def safe_speak(self, text: str, lang: str = "en"):
        """Єдиний метод озвучення — з HUD оновленням."""
        with self.lock:
            self.is_speaking.set()
            update_hud("status", "SPEAKING")
            print(f">>> JARVIS: {text}")
            add_message("jarvis", text)
            speak(text, lang)
            update_hud("status", "STANDBY")
            self.is_speaking.clear()

    def set_mode(self, mode: str, silent: bool = False):
        if mode in ["home", "iron man"]:
            self.mode = mode
            update_hud("mode", mode.upper())
            print(f"[JARVIS] Режим змінено: {mode.upper()}")
            if not silent:
                if mode == "iron man":
                    self.safe_speak("Iron Man mode activated. Single command protocol online, Sir.")
                else:
                    self.safe_speak("Home mode activated. Continuous monitoring online, Sir.")

    def handle_command(self, text: str, lang: str = "en"):
        update_hud("status", "THINKING")
        add_message("user", text)
        text_lower = text.lower()

        if any(p in text_lower for p in ["iron man mode", "switch to iron man", "activate iron man"]):
            self.set_mode("iron man")
            update_hud("status", "STANDBY")
            return

        if any(p in text_lower for p in ["home mode", "switch to home"]):
            self.set_mode("home")
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

        # Логуємо кожен обмін у файл дня
        log_exchange(text, response.replace("[EXIT]", "").replace("[PLAYING]", "").strip())

        if "[EXIT]" in response:
            self.safe_speak(response.replace("[EXIT]", "").strip(), lang)
            return

        self.safe_speak(response, lang)

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
                from langdetect import detect
                detected = detect(text_input)
                lang = "uk" if detected == "uk" else "en"
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
                    print(f"\n[Активація! Режим: {self.mode.upper()}]")
                    recorder.stop()
                    update_hud("status", "LISTENING")

                    self.brain.music_module.set_volume(35)
                    self.safe_speak("Yes Sir")

                    if self.mode == "iron man":
                        start_ironman_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode)
                    else:
                        start_home_conversation(self.brain, self.safe_speak, mode_callback=self.set_mode)

                    self.brain.music_module.set_volume(90)
                    update_hud("status", "STANDBY")
                    print("[Повернення в режим очікування]")

        except KeyboardInterrupt:
            print("\n[Завершення роботи...]")
        except Exception as e:
            print(f"[CRITICAL ERROR] {e}")
        finally:
            self.spotify_poller.stop()
            self.weather_alert.stop()
            recorder.delete()
            porcupine.delete()
            print("[Системи офлайн]")


if __name__ == "__main__":
    jarvis = Jarvis()
    jarvis.run()