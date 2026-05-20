import re
from modules.sensors_module import get_system_report

# УВАГА: НЕ імпортуємо і НЕ створюємо MusicModule/NavigationModule тут!
# Вони вже живуть у Brain і передаються через аргументи — так правильно

def _clean_tags(text: str) -> str:
    """Видаляє всі технічні теги [TAG] з тексту."""
    # re.sub замінює все що підходить під паттерн на порожній рядок
    return re.sub(r'\[.*?\]', '', text).strip()

def _handle_music(command: str, ai_response: str, music_module) -> str:
    """Обробляє команди пов'язані з музикою."""
    search_query = (
        command.lower()
        .replace("jarvis", "")
        .replace("play", "")
        .strip()
    )

    status = music_module.play(search_query)
    print(f"[DEBUG] Spotify: {status}")

    if "PLAYING|" in status:
        track_name = status.split("|")[1]
        # Очищаємо назву від символів які погано читає TTS
        safe_name = track_name.replace("/", " ").replace("&", " and ")
        return f"Sir, I've started playing {safe_name} for you. [PLAYING]"

    # Якщо помилка Spotify
    error_msg = status.replace("ERROR|", "")
    return f"Sir, I encountered an issue: {error_msg}"

def _handle_stop(music_module) -> str:
    """Зупиняє музику і повертає команду виходу."""
    music_module.stop()
    return "As you wish, Sir. Silence restored. [EXIT]"

def _handle_location(ai_response: str, nav_module) -> str:
    address = nav_module.get_current_address()
    clean = _clean_tags(ai_response)                    # прибирає [GET_LOCATION]
    clean = clean.replace("GET_LOCATION", "").strip()   # прибирає GET_LOCATION без дужок
    return f"{address}".strip()  # ← повертаємо ТІЛЬКИ реальну адресу, без AI вигадки

def _handle_status(ai_response: str) -> str:
    """Повертає системний звіт про стан комп'ютера."""
    report = get_system_report()
    clean = _clean_tags(ai_response)
    return f"{clean} {report}".strip()

def _handle_armor(ai_response: str, tag: str, memory) -> str:
    """Відкриває або закриває маску шолому."""
    # Імпорт тут бо armor_module може бути відсутній на деяких пристроях
    from modules.armor_module import open_mask, close_mask
    if tag == "ARMOR_OPEN":
        open_mask(memory)
    else:
        close_mask(memory)
    return _clean_tags(ai_response)

def _handle_exit(ai_response: str, music_module, memory) -> str:
    """Завершує сесію — зупиняє музику, закриває маску."""
    try:
        music_module.stop()
        print("[DEBUG] Audio: Offline")
    except Exception as e:
        print(f"[DEBUG] Не вдалось зупинити музику: {e}")

    try:
        from modules.armor_module import close_mask
        close_mask(memory)
        print("[DEBUG] Armor: Secured")
    except Exception as e:
        print(f"[DEBUG] Не вдалось закрити маску: {e}")

    clean = _clean_tags(ai_response)
    return f"[EXIT] {clean}"


# Головна функція — тепер отримує модулі як аргументи, не створює сама
def route(command: str, memory, music_module, nav_module, ai_module) -> str:
    """
    Маршрутизує команду до потрібного обробника.
    Всі модулі передаються ззовні — немає дублювання.
    """
    cmd_upper = command.upper()

    # --- ЖОРСТКІ КОМАНДИ (без AI) ---
    # Ці слова завжди означають "стоп" — не питаємо AI
    stop_triggers = ["STOP", "OFF", "PAUSE", "SHUT UP", "SILENCE", "HALT"]
    if any(f" {word} " in f" {cmd_upper} " for word in stop_triggers):
        print("[DEBUG] Hard-stop triggered.")
        return _handle_stop(music_module)

    # --- AI ВІДПОВІДЬ ---
    ai_response = ai_module.ask(command)
    res_upper = ai_response.upper()
    print(f"[DEBUG] AI response: {ai_response}")

    # --- МАРШРУТИЗАЦІЯ ПО ТЕГАХ ---
    # Порядок важливий — перевіряємо від найпріоритетнішого
    if "PLAY_MUSIC" in res_upper:
        print("[DEBUG] Intent: Music")
        return _handle_music(command, ai_response, music_module)

    if "STOP_MUSIC" in res_upper or "PAUSE_MUSIC" in res_upper:
        print("[DEBUG] Intent: Stop music")
        return _handle_stop(music_module)

    if "GET_STATUS" in res_upper:
        print("[DEBUG] Intent: System status")
        return _handle_status(ai_response)

    if "ARMOR_OPEN" in res_upper:
        print("[DEBUG] Intent: Armor open")
        return _handle_armor(ai_response, "ARMOR_OPEN", memory)

    if "ARMOR_CLOSE" in res_upper:
        print("[DEBUG] Intent: Armor close")
        return _handle_armor(ai_response, "ARMOR_CLOSE", memory)

    if "GET_LOCATION" in res_upper:
        print("[DEBUG] Intent: Location")
        return _handle_location(ai_response, nav_module)

    if any(word in res_upper for word in ["GOODBYE", "DISMISSED", "EXIT"]):
        print("[DEBUG] Intent: Exit")
        return _handle_exit(ai_response, music_module, memory)

    # Якщо жоден тег не знайдено — повертаємо відповідь AI як є
    return ai_response