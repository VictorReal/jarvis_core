from flask import Flask, request, jsonify
from telethon import TelegramClient
import asyncio
import threading
import os
from dotenv import load_dotenv
import logging
# Заглушуємо логи Flask polling запитів
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

load_dotenv()

app = Flask(__name__)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_USERNAME = os.getenv("BOT_USERNAME")

client = None
loop = None

# Зберігаємо останню відповідь для Watch
latest_response = {"text": "", "timestamp": 0}

def init_telethon():
    global client, loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    client = TelegramClient('watch_session', API_ID, API_HASH)
    
    async def start():
        await client.start()
        print("[WATCH RELAY] ✓ Telethon авторизовано")
    
    loop.run_until_complete(start())
    loop.run_forever()

@app.route('/watch_command', methods=['POST'])
def watch_command():
    """Приймає команду з годинника"""
    data = request.get_json()
    text = data.get('text', '')
    
    if not text:
        return jsonify({'ok': False, 'error': 'No text'}), 400
    
    print(f"[WATCH] Команда: {text}")
    
    # Надсилаємо в Telegram як повідомлення від користувача
    async def send():
        await client.send_message(BOT_USERNAME, text)
    
    asyncio.run_coroutine_threadsafe(send(), loop)
    
    return jsonify({'ok': True})

@app.route('/response', methods=['POST'])
def set_response():
    """Приймає відповідь від Jarvis для Watch"""
    global latest_response
    data = request.get_json()
    text = data.get('text', '')
    
    if text:
        import time
        latest_response = {"text": text, "timestamp": time.time()}
        print(f"[WATCH] Відповідь збережено: {text[:50]}...")
    
    return jsonify({'ok': True})

@app.route('/get_response', methods=['GET'])
def get_response():
    """Phone app опитує цей endpoint для нових відповідей"""
    return jsonify(latest_response)

if __name__ == '__main__':
    threading.Thread(target=init_telethon, daemon=True).start()
    import time
    time.sleep(3)
    print("[WATCH RELAY] Flask → http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)