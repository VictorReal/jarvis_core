import threading
import pvporcupine
from pvrecorder import PvRecorder
import time
import os
import sys
from dotenv import load_dotenv

from brain.processor import Brain
from modules.voice_module import speak
from modules.speech_module import start_conversation

load_dotenv()
ACCESS_KEY = os.getenv("ACCESS_KEY")

jarvis_lock = threading.Lock()
is_speaking = False
jarvis_brain = Brain()

def safe_speak(text):
    global is_speaking
    with jarvis_lock:
        is_speaking = True
        print(f">>> JARVIS: {text}")
        speak(text)
        is_speaking = False

def handle_command(text):
    """Центральна функція обробки тексту (і з голосу, і з терміналу)"""
    # Тут ми викликаємо логіку вашого процесора
    response = jarvis_brain.process(text) # Припустимо, у процесора є такий метод
    if response:
        safe_speak(response)

def terminal_listener():
    """Потік для ручного введення команд"""
    print("--- Термінал активовано. Можете писати команди нижче. ---")
    while True:
        text_input = sys.stdin.readline().strip()
        if text_input:
            if not is_speaking:
                print(f"[Terminal Input]: {text_input}")
                # Якщо це просто команда, обробляємо її через мозок
                handle_command(text_input)
            else:
                print("Зачекайте, Джарвіс говорить...")

def background_listener():
    porcupine = pvporcupine.create(access_key=ACCESS_KEY, keywords=['jarvis'])
    recorder = PvRecorder(frame_length=porcupine.frame_length)
    
    print("Джарвіс: Системи онлайн. Слухаю, сер.")

    threading.Thread(target=terminal_listener, daemon=True).start()

    try:
        while True:
            # Якщо Джарвіс говорить, Picovoice просто "пропускає" кадри
            if is_speaking:
                time.sleep(0.1)
                continue
                
            if not recorder.is_recording:
                recorder.start()
            
            pcm = recorder.read()
            if porcupine.process(pcm) >= 0:
                print("\n[Активація!] Канал відкрито.")
                
                # КРОК 1: Зупиняємо рекордер Picovoice миттєво
                recorder.stop()
                
                # КРОК 2: Відповідаємо (це тепер не блокує main)
                safe_speak("Yes Sir")
                
                # КРОК 3: Запускаємо діалог
                # Ми викликаємо його без 'with jarvis_lock', щоб він міг працювати вільно
                start_conversation(jarvis_brain, safe_speak)
                
                print("[Повернення в режим очікування]")
                # Після виходу з діалогу цикл сам повернеться до recorder.start()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    background_listener()


# import threading
# import pvporcupine
# from pvrecorder import PvRecorder
# import time

# # Імпортуємо ваші модулі
# from brain.processor import Brain
# from modules.voice_module import speak
# from modules.speech_module import start_conversation

# # Створюємо замок та статус
# jarvis_lock = threading.Lock()
# is_speaking = False
# jarvis_brain = Brain()

# # Налаштування Picovoice
# ACCESS_KEY = "pSPrmyV6BT8ORuYrr2Y2vTHj/L+fHe/AbZgjcrMT5Y100FKrdAhU+Q==" 

# def safe_speak(text):
#     global is_speaking
#     with jarvis_lock:
#         is_speaking = True
#         speak(text)
#         is_speaking = False

# def background_listener():
#     """Чекає на слово 'Jarvis'"""
#     porcupine = pvporcupine.create(access_key=ACCESS_KEY, keywords=['jarvis'])
#     recorder = PvRecorder(frame_length=porcupine.frame_length)
    
#     print("Джарвіс: Системи онлайн. Слухаю, сер.")
    
#     try:
#         while True:
#             # Не слухаємо активацію, якщо вже говоримо
#             if is_speaking or jarvis_lock.locked():
#                 time.sleep(0.1)
#                 continue
                
#             if not recorder.is_recording:
#                 recorder.start()
            
#             pcm = recorder.read()
#             if porcupine.process(pcm) >= 0:
#                 with jarvis_lock:
#                     print("\n[Активація!] Канал відкрито.")
#                     recorder.stop()
                    
#                     safe_speak("Yes Sir")
#                     # Запускаємо безперервний діалог
#                     start_conversation(jarvis_brain, safe_speak)
                    
#                     print("[Повернення в режим очікування активації]")
#     except Exception as e:
#         print(f"Background Listener Error: {e}")

# if __name__ == "__main__":
#     # Запускаємо в головному потоці
#     background_listener()