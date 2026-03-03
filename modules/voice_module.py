import edge_tts
import os
import asyncio
import time
import pygame

def speak(text):
    # Очищуємо текст, щоб TTS не читав символи розмітки
    clean_text = text.replace("*", "").replace("#", "").strip()
    if not clean_text:
        return

    # Налаштування циклу подій (необхідно для Python 3.12 у потоках)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(_generate_and_play(clean_text))

async def _generate_and_play(text):
    voice = "en-GB-RyanNeural"
    # Використовуємо унікальне ім'я, щоб уникнути WinError 32
    filename = os.path.abspath(f"voice_{int(time.time() * 1000)}.mp3")
    
    try:
        # 1. Генерація аудіо (Edge-TTS працює дуже швидко)
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(filename)

        # 2. Ініціалізація Pygame Mixer (тільки якщо ще не запущено)
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        # 3. Відтворення прямо з коду (без зовнішніх плеєрів)
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        # Чекаємо завершення мовлення
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)

        # Звільняємо файл для видалення
        pygame.mixer.music.unload()
        
    except Exception as e:
        print(f"JARVIS Voice Error: {e}")
    finally:
        # 4. Видалення тимчасового файлу
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass # Якщо файл все ще зайнятий, він не покладе програму