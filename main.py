import threading
import pvporcupine
from pvrecorder import PvRecorder
import sounddevice as sd
from scipy.io.wavfile import write
import speech_recognition as sr
import os
import numpy as np
import time
from brain.processor import Brain
from modules.voice_module import speak

# Налаштування
ACCESS_KEY = "pSPrmyV6BT8ORuYrr2Y2vTHj/L+fHe/AbZgjcrMT5Y100FKrdAhU+Q==" 
recognizer = sr.Recognizer()
jarvis_brain = Brain()

def listen_and_process():
    """Слухає, поки ви говорите, і зупиняється на тиші"""
    fs = 44100
    filename = "temp_command.wav"
    silence_threshold = 0.01  
    silence_duration = 1.5    
    
    print("[Слухаю...]")
    recording = []
    
    def callback(indata, frames, time_info, status):
        recording.append(indata.copy())

    try:
        with sd.InputStream(samplerate=fs, channels=1, callback=callback, dtype='int16'):
            silent_chunks = 0
            while True:
                if len(recording) > 0:
                    latest_chunk = recording[-1]
                    volume_norm = np.linalg.norm(latest_chunk) / np.sqrt(len(latest_chunk)) / 32768.0
                    
                    if volume_norm < silence_threshold:
                        silent_chunks += 1
                    else:
                        silent_chunks = 0
                    
                    if silent_chunks > (fs / 1024 * silence_duration):
                        break
                sd.sleep(100)

        full_recording = np.concatenate(recording, axis=0)
        write(filename, fs, full_recording)

        with sr.AudioFile(filename) as source:
            audio = recognizer.record(source)
            # Додаємо обробку порожнього результату
            user_text = recognizer.recognize_google(audio, language="en-US")
            print(f"Ви сказали: {user_text}")
            
            response = jarvis_brain.process(user_text)
            print(f"Jarvis: {response}")
            speak(response)
            
    except sr.UnknownValueError:
        print("Джарвіс: Я не почув команди або не зрозумів слів.")
    except Exception as e:
        print(f"Джарвіс не зміг обробити голос: {e}")
    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except:
                pass

def background_listener():
    """Постійно шукає 'Jarvis'"""
    try:
        porcupine = pvporcupine.create(access_key=ACCESS_KEY, keywords=['jarvis'])
        recorder = PvRecorder(frame_length=porcupine.frame_length)
        recorder.start()
        
        while True:
            pcm = recorder.read()
            if porcupine.process(pcm) >= 0:
                print("\n[Активація!] Почув ім'я.")
                
                # 1. Зупиняємо рекордер Picovoice
                recorder.stop()
                
                # 2. Кажемо "Yes Sir" і чекаємо, поки звук закінчиться
                speak("Yes Sir")
                time.sleep(1) # Даємо час вимовити фразу
                
                # 3. Слухаємо команду
                listen_and_process()
                
                # 4. Повертаємося до чергування
                recorder.start()
                
    except Exception as e:
        print(f"Помилка вуха: {e}")

def main():
    print("Джарвіс: Системи онлайн. Слухаю (Голос/Текст), сер.")

    # Запуск фонового прослуховування
    threading.Thread(target=background_listener, daemon=True).start()

    # Можливість писати текстом паралельно
    while True:
        command = input("You: ")
        if command.lower() in ["exit", "stop"]:
            speak("Goodbye Sir")
            break
        response = jarvis_brain.process(command)
        print("Jarvis:", response)
        speak(response)

if __name__ == "__main__":
    main()