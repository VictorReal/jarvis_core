import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

PROFILES_DIR = "data/profiles"

def _ensure_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)

def _profile_path(name: str) -> str:
    """Повертає шлях до файлу профілю."""
    return os.path.join(PROFILES_DIR, f"{name.lower()}.json")

def get_all_profiles() -> list:
    """Повертає список всіх профілів."""
    _ensure_dir()
    profiles = []
    for filename in os.listdir(PROFILES_DIR):
        if filename.endswith(".json"):
            try:
                with open(os.path.join(PROFILES_DIR, filename), "r", encoding="utf-8") as f:
                    profiles.append(json.load(f))
            except Exception as e:
                logger.warning(f"Не вдалось завантажити профіль {filename}: {e}")
    return profiles

def get_profile(name: str) -> dict | None:
    """Завантажує профіль по імені. Повертає None якщо не знайдено."""
    path = _profile_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Помилка завантаження профілю {name}: {e}")
        return None

def save_profile(profile: dict) -> bool:
    """Зберігає профіль у файл."""
    _ensure_dir()
    try:
        path = _profile_path(profile["name"])
        profile["last_seen"] = datetime.now().isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"[PEOPLE] Профіль збережено: {profile['name']}")
        return True
    except Exception as e:
        logger.error(f"Помилка збереження профілю: {e}")
        return False

def create_profile(name: str, relationship: str = "friend", personality: str = "polite") -> dict:
    """Створює новий профіль."""
    profile = {
        "name": name.capitalize(),
        "relationship": relationship,
        "personality_toward": personality,
        "facts": [],
        "first_met": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    }
    save_profile(profile)
    return profile

def add_fact(name: str, fact: str) -> bool:
    """Додає факт до профілю людини."""
    profile = get_profile(name)
    if not profile:
        return False
    if fact not in profile["facts"]:
        profile["facts"].append(fact)
        save_profile(profile)
        print(f"[PEOPLE] Додано факт про {name}: {fact}")
    return True

def find_profile_by_name(name: str) -> dict | None:
    """
    Шукає профіль по імені — нечутливо до регістру.
    Якщо є кілька людей з однаковим іменем — повертає список для уточнення.
    """
    name_lower = name.lower()
    matches = []
    for profile in get_all_profiles():
        if profile["name"].lower() == name_lower:
            matches.append(profile)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Повертаємо всі збіги — агент запитає уточнення
        return {"multiple": True, "matches": matches}
    return None

def get_profiles_summary() -> str:
    """
    Повертає короткий опис всіх знайомих — для контексту LLM.
    Наприклад: 'Alex (friend): likes cars, programming. Maria (colleague): likes art.'
    """
    profiles = get_all_profiles()
    if not profiles:
        return "No people in memory yet."

    parts = []
    for p in profiles:
        facts_str = ", ".join(p.get("facts", [])[:5])  # максимум 5 фактів
        parts.append(
            f"{p['name']} ({p.get('relationship', 'unknown')}): {facts_str or 'no facts yet'}"
        )
    return " | ".join(parts)