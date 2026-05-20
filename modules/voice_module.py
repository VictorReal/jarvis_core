import edge_tts
import os
import asyncio
import time
import pygame

pygame.mixer.init()

class VoiceModule:
    VOICES = {
        "en": "en-GB-RyanNeural",
        "uk": "uk-UA-OstapNeural",
    }

    def __init__(self):
        self.current_voice = self.VOICES["en"]

    def speak(self, text: str, lang: str = "en"):
        clean_text = text.replace("*", "").replace("#", "").strip()
        if not clean_text:
            return

        self.current_voice = self.VOICES.get(lang, self.VOICES["en"])

        try:
            asyncio.run(self._generate_and_play(clean_text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._generate_and_play(clean_text))
            finally:
                loop.close()

    async def _generate_and_play(self, text: str):
        filename = os.path.abspath(f"voice_{int(time.time() * 1000)}.mp3")
        try:
            communicate = edge_tts.Communicate(text, self.current_voice)
            await communicate.save(filename)

            # Чекаємо поки файл реально з'явиться і не порожній
            for _ in range(20):
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    break
                await asyncio.sleep(0.05)
            else:
                print("[VoiceModule ERROR] No audio was received. Please verify that your parameters are correct.")
                return

            # Зупиняємо попереднє відтворення якщо є
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
                await asyncio.sleep(0.1)

            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception as e:
            print(f"[VoiceModule ERROR] {e}")
        finally:
            await asyncio.sleep(0.15)  # даємо pygame звільнити файл
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception as e:
                    print(f"[VoiceModule] Не вдалось видалити файл: {e}")


_voice = VoiceModule()

def speak(text: str, lang: str = "en"):
    _voice.speak(text, lang)