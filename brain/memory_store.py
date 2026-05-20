import json
import os
from datetime import datetime
from langchain_core.messages import HumanMessage, AIMessage

HISTORY_FILE = "data/chat_history.json"
MAX_CONTEXT  = 20   # скільки повідомлень передаємо в LLM
MAX_STORED   = 1000 # скільки зберігаємо у файлі

def _ensure_dir():
    os.makedirs("data", exist_ok=True)

def save_history(chat_history: list):
    """Зберігає ВСЮ історію у файл."""
    _ensure_dir()
    try:
        # Завантажуємо існуючу повну історію
        existing = _load_all()

        # Додаємо нові повідомлення яких ще немає
        serializable = []
        for msg in chat_history:
            if isinstance(msg, HumanMessage):
                serializable.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                serializable.append({"role": "assistant", "content": msg.content})

        # Об'єднуємо і обрізаємо до MAX_STORED
        all_messages = existing + [m for m in serializable if m not in existing]
        all_messages = all_messages[-MAX_STORED:]

        data = {
            "saved_at": datetime.now().isoformat(),
            "total": len(all_messages),
            "messages": all_messages
        }

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[MEMORY] Збережено всього: {len(all_messages)} повідомлень")

    except Exception as e:
        print(f"[MEMORY ERROR] Не вдалось зберегти: {e}")

def _load_all() -> list:
    """Завантажує всі повідомлення з файлу як словники."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception:
        return []

def load_history() -> list:
    """Завантажує останні MAX_CONTEXT повідомлень для LLM."""
    all_messages = _load_all()
    if not all_messages:
        print("[MEMORY] Нова сесія — історії немає")
        return []

    # Беремо тільки останні 20 для контексту LLM
    recent = all_messages[-MAX_CONTEXT:]

    result = []
    for msg in recent:
        if msg["role"] == "user":
            result.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            result.append(AIMessage(content=msg["content"]))

    print(f"[MEMORY] Завантажено {len(result)} з {len(all_messages)} повідомлень")
    return result

def clear_history():
    """Видаляє файл історії."""
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
        print("[MEMORY] Історію очищено")