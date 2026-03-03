import speech_recognition as sr
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
import os
import time

from modules.sensors_module import get_system_report

recognizer = sr.Recognizer()

# Виносимо запис у глобальну змінну модуля для callback
_recording_data = []

def audio_callback(indata, frames, time_info, status):
    if status:
        print(status)
    _recording_data.append(indata.copy())

def listen_and_process():
    global _recording_data
    fs = 44100
    filename = "temp_command.wav"
    silence_threshold = 0.01  # Зменшено для кращої чутливості
    silence_duration = 0.7    # Трохи більше часу на роздуми
    time.sleep(0.1)
    _recording_data = []
    print("[СЛУХАЮ...]")
    
    try:
        # Відкриваємо потік
        with sd.InputStream(samplerate=fs, channels=1, callback=audio_callback, dtype='int16'):
            silent_chunks = 0
            while True:
                if len(_recording_data) > 0:
                    latest_chunk = _recording_data[-1]
                    # Обчислюємо гучність
                    volume_norm = np.linalg.norm(latest_chunk) / np.sqrt(len(latest_chunk)) / 32768.0
                    
                    if volume_norm < silence_threshold:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0
                    
                    # Якщо тиша триває довше ліміту
                    if silent_chunks > (fs / 1024 * silence_duration):
                        print("[Тиша зафіксована]")
                        break
                time.sleep(0.05)

        if not _recording_data:
            return None

        # Зберігаємо у файл
        audio_combined = np.concatenate(_recording_data, axis=0)
        write(filename, fs, audio_combined)

        # Розпізнавання
        with sr.AudioFile(filename) as source:
            audio = recognizer.record(source)
            # Додаємо спробу розпізнавання
            try:
                user_text = recognizer.recognize_google(audio, language="en-US")
                print(f">>> YOU: {user_text}") # ЦЕЙ РЯДОК ОБОВ'ЯЗКОВИЙ
                return user_text
            except sr.UnknownValueError:
                print("[ВУХА] Не розпізнано жодного слова.")
                return None
    except Exception as e:
        print(f"Speech Error: {e}")
        return None
    finally:
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass

def start_conversation(jarvis_brain, safe_speak_func):
    while True:
        user_text = listen_and_process()
        
        if not user_text:
            print("[Сесія закрита: тиша]")
            break

        text_lower = user_text.lower()    
        print(f"You: {user_text}")
        
        if any(word in text_lower for word in ["status", "report", "system state", "temperature"]):
            # Джарвіс відповідає миттєво, не питаючи нейромережу
            status_info = get_system_report()
            safe_speak_func(status_info)
            continue
        # 2. НАВІГАЦІЯ (АТБ, ПАБИ) - поки що логіка-заглушка
        if any(word in text_lower for word in ["find", "where is", "closest", "navigate"]):
            safe_speak_func("Accessing global maps... I'm searching for the nearest locations, Sir.")
            # Тут буде виклик вашого navigation_module
            continue
        # 3. МУЗИКА (SPOTIFY)
        if any(word in text_lower for word in ["music", "play", "spotify", "volume", "next track"]):
            safe_speak_func("Adjusting media playback.")
            # Тут буде виклик вашого spotify_module
            continue
        if any(word in text_lower for word in ["stop", "exit", "dismissed", "goodbye", "bye"]):
            safe_speak_func("As you wish, Sir. Systems standing by.")
            break

        response = jarvis_brain.process(user_text)
        safe_speak_func(response)
        print("[Слухаю далі...]")
