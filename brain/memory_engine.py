"""
memory_engine.py — Система пам'яті JARVIS

Три рівні:
  1. Session summary  — стискає старі повідомлення в один рядок щоб не рости нескінченно
  2. Short memory     — data/short_memory.json  (7 днів, факти з кожного дня)
  3. Long memory      — data/long_memory.json   (назавжди, тільки найважливіше)

Авто-оновлення досьє — після кожної розмови LLM витягує нові факти про людей
і зберігає їх у people profiles.
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR        = Path("data")
SHORT_MEM_FILE  = DATA_DIR / "short_memory.json"
LONG_MEM_FILE   = DATA_DIR / "long_memory.json"
SESSION_SUM_FILE= DATA_DIR / "session_summary.txt"

SHORT_MEMORY_DAYS = 7
SUMMARY_TRIGGER   = 16   # стискаємо коли chat_history > N пар (32 повідомлення)


# ─────────────────────────────────────────────────────────────────────────────
#  Утиліти
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_dir():
    DATA_DIR.mkdir(exist_ok=True)


def _load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[MEMORY ENGINE] Помилка читання {path}: {e}")
    return default


def _save_json(path: Path, data):
    _ensure_dir()
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[MEMORY ENGINE] Помилка збереження {path}: {e}")


def _safe_json_array(raw: str):
    """
    Парсить JSON-масив з відповіді LLM, переживаючи типові поломки:
      - markdown-обгортку ```json ... ```
      - зайвий текст до/після масиву
      - ОБІРВАНИЙ вивід (ліміт токенів) — Unterminated string / немає ']'
    Повертає list (можливо неповний, але валідний) або [] якщо нічого не врятувати.
    """
    if not raw:
        return []
    # Прибираємо markdown-огорожу
    raw = raw.replace("```json", "").replace("```", "").strip()
    # Вирізаємо від першої '[' до останньої ']'
    start = raw.find("[")
    if start < 0:
        return []
    end = raw.rfind("]")
    candidate = raw[start:end + 1] if end > start else raw[start:]

    # Спроба 1: цілісний масив
    try:
        result = json.loads(candidate)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        pass

    # Спроба 2: вивід обірвано — збираємо цілі елементи поелементно.
    # Дужку-відкривачку відкидаємо і парсимо кожен top-level елемент окремо.
    body = candidate[1:]  # без '['
    items = []
    depth = 0
    in_str = False
    esc = False
    buf = []
    for ch in body:
        if esc:
            buf.append(ch); esc = False; continue
        if ch == "\\":
            buf.append(ch); esc = True; continue
        if ch == '"':
            in_str = not in_str; buf.append(ch); continue
        if in_str:
            buf.append(ch); continue
        if ch in "{[":
            depth += 1; buf.append(ch); continue
        if ch in "}]":
            if depth == 0:  # дійшли до закриття масиву
                break
            depth -= 1; buf.append(ch); continue
        if ch == "," and depth == 0:
            piece = "".join(buf).strip()
            if piece:
                try:
                    items.append(json.loads(piece))
                except json.JSONDecodeError:
                    pass
            buf = []
            continue
        buf.append(ch)
    # Останній елемент (якщо він повний)
    piece = "".join(buf).strip()
    if piece:
        try:
            items.append(json.loads(piece))
        except json.JSONDecodeError:
            pass  # обірваний хвіст — свідомо ігноруємо

    if items:
        logger.info(f"[MEMORY ENGINE] JSON обірвано — врятовано {len(items)} елементів")
    return items


# ─────────────────────────────────────────────────────────────────────────────
#  1. Session summary  (стискання старої частини chat_history)
# ─────────────────────────────────────────────────────────────────────────────

def compress_history_if_needed(chat_history: list, llm) -> list:
    """
    Якщо chat_history > SUMMARY_TRIGGER*2 повідомлень — стискає стару половину
    в один SystemMessage-рядок і повертає скорочену копію.
    Оригінальний список не змінює.
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    if len(chat_history) <= SUMMARY_TRIGGER * 2:
        return chat_history

    # Беремо стару половину для стиснення, нову — залишаємо
    split_point = len(chat_history) // 2
    old_part  = chat_history[:split_point]
    keep_part = chat_history[split_point:]

    # Форматуємо для LLM
    text_for_sum = "\n".join(
        ("SIR: " if isinstance(m, HumanMessage) else "JARVIS: ") + m.content
        for m in old_part
        if hasattr(m, "content")
    )

    try:
        resp = llm.invoke([
            SystemMessage(content=(
                "Summarize this conversation in 3-5 concise sentences. "
                "Focus on facts, decisions, preferences, and important context. "
                "Write in third person: 'Sir asked...', 'JARVIS reported...'. "
                "Output only the summary, no preamble."
            )),
            HumanMessage(content=text_for_sum),
        ])
        summary_text = resp.content.strip()
    except Exception as e:
        logger.warning(f"[MEMORY ENGINE] Помилка стиснення: {e}")
        return chat_history

    # Зберігаємо summary на диск (додаємо до файлу)
    _ensure_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(SESSION_SUM_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {summary_text}")

    # Повертаємо: [SystemMessage(summary)] + нова частина
    compressed = [SystemMessage(content=f"[Previous context]: {summary_text}")] + keep_part
    logger.info(f"[MEMORY ENGINE] Стиснуто {len(old_part)} → 1 повідомлення")
    return compressed


def get_session_summary() -> str:
    """Повертає останні summary з файлу для підстановки в system prompt."""
    if not SESSION_SUM_FILE.exists():
        return ""
    try:
        lines = SESSION_SUM_FILE.read_text(encoding="utf-8").strip().splitlines()
        # Беремо останні 3 записи
        recent = [l for l in lines if l.strip()][-3:]
        return " ".join(recent)
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
#  2. Short memory (7 днів)
# ─────────────────────────────────────────────────────────────────────────────

def _is_location_fact(fact: str) -> bool:
    """True якщо факт про місцеперебування користувача — такі НЕ зберігаємо
    в пам'яті (локація завжди береться live через тули, інакше застаріває
    і нав'язується моделі, напр. 'Sir is in Ataki, Moldova')."""
    f = fact.lower()
    markers = (
        "is in ", "is near", "located", "location", "whereabouts",
        "in otaci", "in ataki", "moldova", "strada", "vulytsya", "вулиц",
        "знаходиться", "перебува", "поблизу", " near ", "address",
    )
    # фрази про переміщення/координати
    return any(m in f for m in markers)


def update_short_memory(llm):
    """
    Читає лог сьогоднішнього дня і витягує факти → short_memory.json.
    Викликати раз на день (при старті або вночі).
    """
    try:
        try:
            from day_logger import get_today_log
        except ImportError:
            from day_logger import get_today_log
        log = get_today_log()
        if not log or len(log) < 100:
            return

        from langchain_core.messages import HumanMessage, SystemMessage
        resp = llm.invoke([
            SystemMessage(content=(
                "Extract key facts from today's JARVIS activity log. "
                "Return a JSON array of short fact strings (max 10). "
                "Focus on: preferences, decisions, people mentioned, tasks done. "
                "Do NOT include the user's location, city, or current whereabouts — "
                "location is always taken live, never remembered. "
                "Example: [\"Sir prefers jazz in the morning\", \"Called mom\"]. "
                "Output ONLY the JSON array, nothing else."
            )),
            HumanMessage(content=log[:3000]),  # не більше 3к символів
        ])

        raw = resp.content.strip()
        # Чистимо markdown і рятуємо навіть обірваний JSON
        facts = _safe_json_array(raw)
        if not facts:
            return

        # Викидаємо факти про локацію — вони застарівають і нав'язуються моделі
        facts = [f for f in facts if isinstance(f, str) and not _is_location_fact(f)]
        if not facts:
            return

        data = _load_json(SHORT_MEM_FILE, {"entries": []})
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Видаляємо старий запис за сьогодні якщо є
        data["entries"] = [e for e in data["entries"] if e.get("date") != today_str]

        # Видаляємо записи старші 7 днів
        cutoff = (datetime.now() - timedelta(days=SHORT_MEMORY_DAYS)).strftime("%Y-%m-%d")
        data["entries"] = [e for e in data["entries"] if e.get("date", "") >= cutoff]

        data["entries"].append({"date": today_str, "facts": facts})
        _save_json(SHORT_MEM_FILE, data)
        logger.info(f"[MEMORY ENGINE] Short memory оновлено: {len(facts)} фактів за {today_str}")

    except Exception as e:
        logger.warning(f"[MEMORY ENGINE] update_short_memory error: {e}")


def get_short_memory_context(max_facts: int = 5) -> str:
    """Повертає топ-N фактів з короткої пам'яті для system prompt."""
    data = _load_json(SHORT_MEM_FILE, {"entries": []})
    entries = sorted(data.get("entries", []), key=lambda e: e.get("date", ""), reverse=True)

    all_facts = []
    for entry in entries[:3]:  # останні 3 дні
        all_facts.extend(entry.get("facts", []))

    # На читанні теж відсіюємо локацію — захищає від старих записів у файлі,
    # які ще не перезаписані новою (вже відфільтрованою) логікою.
    all_facts = [f for f in all_facts if isinstance(f, str) and not _is_location_fact(f)]

    if not all_facts:
        return ""

    selected = all_facts[:max_facts]
    return "Recent memory: " + "; ".join(selected) + "."


# ─────────────────────────────────────────────────────────────────────────────
#  3. Long memory (назавжди)
# ─────────────────────────────────────────────────────────────────────────────

def update_long_memory(llm):
    """
    Читає short_memory.json і витягує тільки ключове → long_memory.json.
    Викликати раз на тиждень.
    """
    try:
        data = _load_json(SHORT_MEM_FILE, {"entries": []})
        if not data["entries"]:
            return

        all_facts = []
        for entry in data["entries"]:
            all_facts.extend(entry.get("facts", []))

        if not all_facts:
            return

        existing = _load_json(LONG_MEM_FILE, {"facts": [], "updated": ""})
        combined = existing.get("facts", []) + all_facts

        from langchain_core.messages import HumanMessage, SystemMessage
        resp = llm.invoke([
            SystemMessage(content=(
                "From this list of facts about a person, extract the most important long-term facts. "
                "Remove duplicates and minor details. Keep max 20 facts. "
                "Return a JSON array of strings. Output ONLY the JSON array."
            )),
            HumanMessage(content=json.dumps(combined, ensure_ascii=False)),
        ])

        raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
        facts = _safe_json_array(raw)
        if not facts:
            return

        _save_json(LONG_MEM_FILE, {
            "facts": facts,
            "updated": datetime.now().strftime("%Y-%m-%d"),
        })
        logger.info(f"[MEMORY ENGINE] Long memory оновлено: {len(facts)} фактів")

    except Exception as e:
        logger.warning(f"[MEMORY ENGINE] update_long_memory error: {e}")


def get_long_memory_context() -> str:
    """Повертає довгу пам'ять для system prompt."""
    data = _load_json(LONG_MEM_FILE, {"facts": []})
    facts = data.get("facts", [])
    if not facts:
        return ""
    return "Long-term memory: " + "; ".join(facts[:10]) + "."


# ─────────────────────────────────────────────────────────────────────────────
#  4. Авто-оновлення досьє людей
# ─────────────────────────────────────────────────────────────────────────────

_PERSON_EXTRACT_PROMPT = (
    "Analyze this conversation exchange and extract any new facts about PEOPLE only. "
    "Look for: names of people, relationships ('my sister', 'my boss'), personality "
    "traits, preferences, jobs, or personal details about a person. "
    "Do NOT extract cities, countries, places, businesses, or geographic locations — "
    "only actual people. "
    "Return a JSON array of objects: [{\"name\": str, \"relationship\": str, \"fact\": str}]. "
    "If no new person-facts found, return empty array []. "
    "Output ONLY the JSON array, nothing else."
)


def extract_and_save_people(user_input: str, jarvis_response: str, llm):
    """
    Після кожної розмови аналізує пару user/jarvis і авто-зберігає нові факти.
    Запускається в окремому потоці щоб не гальмувати відповідь.
    """
    def _run():
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            exchange = f"SIR: {user_input}\nJARVIS: {jarvis_response}"
            resp = llm.invoke([
                SystemMessage(content=_PERSON_EXTRACT_PROMPT),
                HumanMessage(content=exchange),
            ])
            raw = resp.content.strip().replace("```json", "").replace("```", "").strip()
            items = _safe_json_array(raw)
            if not items:
                return

            from modules.people_module import get_profile, create_profile, add_fact

            STOP_NAMES = {
                "sir", "victor", "вікторе", "вiкторе", "jarvis", "ultron",
                "ai", "system", "user", "assistant", "you", "i",
                "home", "iron", "man", "сер", "пан",
            }

            def _normalize_name(n: str) -> str:
                """Прибирає кличний відмінок -е/-є якщо це українське ім'я."""
                if len(n) > 3 and n[-1].lower() in ("е", "є"):
                    return n[:-1]  # Вікторе → Віктор
                return n

            # Факти, що означають "це просто локація" — не створюємо профіль.
            # (екстрактор раніше плодив профілі міст: "Ataki: location")
            LOCATION_FACTS = {
                "location", "is a location", "a location", "place", "is a place",
                "city", "is a city", "country", "is a country", "локація",
                "місце", "місто", "країна",
            }

            for item in items:
                name = item.get("name", "").strip()
                relationship = item.get("relationship", "acquaintance")
                fact = item.get("fact", "").strip()
                if not name or not fact or len(name) > 50 or len(name) < 2:
                    continue
                if name.lower() in STOP_NAMES:
                    continue
                # пропускаємо геосутності (факт = просто "location"/"city"/...)
                if fact.lower() in LOCATION_FACTS:
                    logger.debug(f"[MEMORY ENGINE] Пропущено локацію: {name} ({fact})")
                    continue
                name = _normalize_name(name)

                profile = get_profile(name)
                if not profile:
                    create_profile(name, relationship)
                    logger.info(f"[MEMORY ENGINE] Новий профіль: {name}")

                add_fact(name, fact)
                logger.info(f"[MEMORY ENGINE] Факт про {name}: {fact}")

        except Exception as e:
            logger.debug(f"[MEMORY ENGINE] extract_people error: {e}")

    threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  5. Повний контекст для system prompt
# ─────────────────────────────────────────────────────────────────────────────

def build_memory_context() -> str:
    """Збирає весь контекст пам'яті в один рядок для system prompt."""
    parts = []

    long_mem = get_long_memory_context()
    if long_mem:
        parts.append(long_mem)

    short_mem = get_short_memory_context()
    if short_mem:
        parts.append(short_mem)

    session_sum = get_session_summary()
    if session_sum:
        parts.append(session_sum)

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
#  6. Планувальник фонових задач
# ─────────────────────────────────────────────────────────────────────────────

def schedule_memory_updates(llm):
    """
    Запускає фонові оновлення пам'яті:
      - short_memory: щодня при старті (якщо є лог)
      - long_memory: раз на тиждень
    """
    def _run():
        import time

        # Short memory — одразу при старті (з затримкою)
        time.sleep(30)
        update_short_memory(llm)

        # Long memory — якщо не оновлювалась більше 7 днів
        data = _load_json(LONG_MEM_FILE, {"updated": ""})
        last_updated = data.get("updated", "")
        if last_updated:
            try:
                delta = datetime.now() - datetime.strptime(last_updated, "%Y-%m-%d")
                if delta.days >= 7:
                    update_long_memory(llm)
            except Exception:
                pass
        else:
            update_long_memory(llm)

    threading.Thread(target=_run, daemon=True, name="MemoryScheduler").start()
    logger.info("[MEMORY ENGINE] Планувальник запущено")