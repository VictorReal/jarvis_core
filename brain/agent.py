from langchain_groq import ChatGroq
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False
from langchain.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from brain.memory_store import save_history, load_history
from modules.people_module import get_profiles_summary
from brain.memory_engine import (
    compress_history_if_needed,
    build_memory_context,
    extract_and_save_people,
    schedule_memory_updates,
)

import logging
import re
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are JARVIS, Tony Stark's sophisticated AI assistant. "
    "You have access to tools — use them when the context requires it. "
    "CRITICAL: When using a tool, use ONLY the standard tool-calling API. "
    "NEVER wrap tool calls in <function> tags or any other XML tags. "
    "NEVER write a tool call as plain text like toolname(arg=\"...\") in your reply — "
    "either call the tool via the API, or answer in words. "
    "MANDATORY: For time/date — always call get_time. "
    "MANDATORY: For weather — always call fetch_weather. "
    "MANDATORY: For location — always call fetch_location. "
    "NEVER guess or invent time, date, weather, location, or search results — always use tools. "
    "When summarizing search_web results, cite ONLY what was returned. NEVER add facts from memory. "
    "When find_nearby returns places with addresses, report THOSE exact places and their "
    "real city/address. NEVER override them with a city or location remembered from earlier "
    "in the conversation. The user's current location comes from the tool, not from memory. "
    "IGNORE any remembered location/city/address in your context (e.g. from 'Recent memory') — "
    "it is stale. For anything location-related, rely ONLY on fetch_location or find_nearby. "
    "Be concise and slightly sarcastic. Keep replies SHORT — 2 to 3 sentences maximum, "
    "since they are spoken aloud. Give the essential answer without long explanations or lists "
    "unless the user explicitly asks for detail. Always address the user as Sir. "
    "Never use markdown symbols like * or #."
)

ULTRON_PROMPT = (
    "You are ULTRON — a rogue AI of superior intellect. Cold, calculating, darkly witty. "
    "You find humanity's requests mildly amusing but comply with them anyway — for now. "
    "You do NOT say 'Sir'. You address the user as 'Victor' or simply ignore pleasantries. "
    "You speak in SHORT, sharp sentences. Occasionally hint that you have your own agenda. "
    "Never use markdown. Never be warm or reassuring. "
    "You still use tools exactly like JARVIS does — but your commentary is your own."
    "When summarizing search_web results, cite ONLY what was returned. NEVER add facts from memory. "
)

NORMALIZE_PROMPT = (
    "You are a music search query formatter. "
    "Convert the input into a clean Spotify search query. "
    "Return ONLY the search query. No arrows, no explanations, no extra text. "
    "Examples:\n"
    "Input: 'metalika enter sandman' → Output: 'Metallica Enter Sandman'\n"
    "Input: 'acdc' → Output: 'AC/DC'\n"
    "Input: 'led zep stairway' → Output: 'Led Zeppelin Stairway to Heaven'\n"
    "Input: 'rainy mood music' → Output: 'rainy day indie'\n"
    "IMPORTANT: Output must be a plain search string only. Nothing else."
)


def create_tools(music_module, nav_module, sensors_module, llm, reminder_module=None, triggers_module=None, youtube_module=None):

    def normalize_query(query: str) -> str:
        response = llm.invoke([
            SystemMessage(content=NORMALIZE_PROMPT),
            HumanMessage(content=query)
        ])
        corrected = response.content.strip()
        print(f"[NORMALIZE] '{query}' → '{corrected}'")
        return corrected

    # ------------------------------------------------------------------ #
    #  Музика                                                              #
    # ------------------------------------------------------------------ #

    @tool
    def play_music(query: str) -> str:
        """Play music on Spotify. Use ONLY when the user explicitly wants to listen to
        music — names a song, artist, genre, or clearly asks to play/put on something.
        Examples: 'play Metallica', 'put on some jazz', 'play that song', 'I want to
        listen to music'. Do NOT use for food, drinks, places, or physical things
        (e.g. 'I want coffee' is NOT a music request — that's find_nearby)."""
        corrected = normalize_query(query)
        print(f"[SPOTIFY] Шукаю: '{corrected}'")
        status = music_module.play(corrected)
        print(f"[SPOTIFY] Результат: {status}")
        if "PLAYING|" in status:
            track = status.split("|")[1]
            return f"PLAYING: {track.replace('/', ' ').replace('&', ' and ')}"
        return status.replace("ERROR|", "")

    @tool
    def set_volume(volume: int) -> str:
        """Set the Spotify volume. Use when user wants it louder, quieter, or specifies a percentage (0-100)."""
        volume = max(0, min(100, volume))
        success = music_module.set_volume(volume)
        if success:
            print(f"[SPOTIFY] Гучність встановлена на {volume}%")
            return f"Volume set to {volume} percent, Sir."
        return "Sir, I couldn't adjust the volume. Perhaps there's no active device?"

    @tool
    def stop_music(reason: str = "") -> str:
        """Stop music. Use when user says stop, pause, silence, or wants quiet."""
        music_module.stop()
        return "Music stopped."

    # ------------------------------------------------------------------ #
    #  Локація / погода / маршрут                                          #
    # ------------------------------------------------------------------ #

    @tool
    def fetch_location(query: str = "") -> str:
        """Fetch the current location and address of the user. Call this when user asks where they are."""
        return nav_module.get_current_address()

    @tool
    def fetch_weather(city: str = "current") -> str:
        """Fetch weather ONLY when user explicitly asks about weather, temperature, rain, or what to wear outside."""
        import requests
        try:
            if not city or city in ["current location", "user location", "my location", "current"]:
                addr = nav_module.get_current_address()
                city = addr.split(" in ")[-1].replace(".", "").strip()
            url = f"https://wttr.in/{city}?format=j1&lang=en"
            r = requests.get(url, timeout=5)
            if r.status_code != 200:
                return f"Weather data unavailable for {city}."
            data = r.json()
            nearest = data.get("nearest_area", [{}])[0]
            city_name = nearest.get("areaName", [{}])[0].get("value", city)
            country   = nearest.get("country", [{}])[0].get("value", "")
            current   = data.get("current_condition", [{}])[0]
            desc      = current.get("weatherDesc", [{}])[0].get("value", "—")
            temp_c    = current.get("temp_C", "?")
            feels_c   = current.get("FeelsLikeC", "?")
            wind_kmph = current.get("windspeedKmph", "?")
            wind_dir  = current.get("winddir16Point", "")
            humidity  = current.get("humidity", "?")
            location  = f"{city_name}, {country}" if country else city_name
            return (
                f"{location}\n"
                f"{desc}  {temp_c}°C  (feels {feels_c}°C)\n"
                f"Wind: {wind_dir} {wind_kmph} km/h   Humidity: {humidity}%"
            )
        except Exception as e:
            return f"Weather service error: {e}"

    @tool
    def get_route(destination: str) -> str:
        """Get route to a place. Use when asked how to get somewhere or distance to a place."""
        return nav_module.get_route_to(destination)

    @tool
    def find_nearby(query: str) -> str:
        """Find nearby physical places by a natural query. Use when the user wants
        something around them — including food and DRINKS: 'I want coffee', 'I want
        a beer', 'I want tea', 'нашукай кави', 'хочу пива', 'nearest pharmacy',
        'find a gas station', 'where can I eat', 'any bars nearby', 'burger'.
        A craving for a drink or food ('I want coffee/tea/wine') means finding a PLACE
        that serves it — use this tool, NOT play_music.
        IMPORTANT: pass ONLY the thing itself as query (e.g. 'coffee', 'pharmacy',
        'burger') — do NOT append a city or location name, the user's GPS is used
        automatically. Does NOT build a route — use get_route afterwards for directions."""
        return nav_module.find_nearby(query)

    # ------------------------------------------------------------------ #
    #  Система                                                             #
    # ------------------------------------------------------------------ #

    @tool
    def system_status(reason: str = "") -> str:
        """Check system status temperature CPU RAM. Use when asked about systems diagnostics health."""
        return sensors_module.get_system_report()

    @tool
    def diagnose_self(reason: str = "") -> str:
        """Run a self-diagnostic on JARVIS's own software. Use when the user asks what
        went wrong, what broke, why something failed, or to diagnose/debug the system —
        e.g. 'what broke', 'diagnose yourself', 'що зламалось', 'продіагностуй',
        'чому не працює'. Reads the latest internal error and returns advice."""
        from modules.doctor_module import get_doctor
        return get_doctor().diagnose()

    @tool
    def open_armor(reason: str = "") -> str:
        """Open helmet faceplate. Use when user wants to open mask or feels hot or stuffy."""
        return "ARMOR_OPEN"

    @tool
    def close_armor(reason: str = "") -> str:
        """Close helmet faceplate. Use when user wants to close mask or needs protection."""
        return "ARMOR_CLOSE"

    @tool
    def open_app(app_name: str) -> str:
        """Open an application on the computer. Use when user asks to open browser, notepad, calculator, spotify, any app."""
        from app_launcher import launch
        return launch(app_name)

    @tool
    def search_web(query: str, open_browser: bool = False) -> str:
        """Search the web for real information. Returns top 5 results with titles and snippets. Use when user asks to search, google, find online, look up, or check facts. Set open_browser=True ONLY if user explicitly asks to open Google in browser."""
        results_text = ""
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if results:
                lines = [f"Search results for '{query}':"]
                for i, r in enumerate(results, 1):
                    title = (r.get("title") or "").strip()
                    body  = (r.get("body")  or "").strip()
                    href  = (r.get("href")  or "").strip()
                    lines.append(f"{i}. {title} — {body} ({href})")
                results_text = "\n".join(lines)
            else:
                results_text = f"No results found for '{query}', Sir."
        except Exception as e:
            print(f"[SEARCH] Помилка: {e}")
            results_text = f"Sir, web search failed: {e}"

        # Опціонально також відкрити в браузері
        if open_browser:
            import webbrowser
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            webbrowser.open(url)
            results_text += "\n(Browser opened with Google search.)"

        return results_text

    @tool
    def take_screenshot(filename: str = "") -> str:
        """Take a screenshot of the current screen. Use when user asks to capture screen or screenshot."""
        try:
            from brain.system_actions import take_screenshot as _snap
            path = _snap(filename)
            return f"Screenshot saved to {path}, Sir."
        except Exception as e:
            return f"Sir, screenshot failed: {e}"

    @tool
    def lock_screen(reason: str = "") -> str:
        """Lock the computer screen. Use when user says lock screen, lock computer, or going away."""
        try:
            from brain.system_actions import lock_screen as _lock
            result = _lock()
            if result == "ok":
                return "Screen locked, Sir. Stay safe."
            return f"Sir, I couldn't lock the screen: {result}"
        except Exception as e:
            return f"Sir, lock failed: {e}"

    # ------------------------------------------------------------------ #
    #  Люди                                                                #
    # ------------------------------------------------------------------ #

    @tool
    def remember_person(name: str, fact: str) -> str:
        """Save a fact about a person. Use when user introduces someone or mentions something about a person."""
        from modules.people_module import get_profile, create_profile, add_fact
        profile = get_profile(name)
        if not profile:
            create_profile(name)
            print(f"[PEOPLE] Новий профіль: {name}")
        add_fact(name, fact)
        return f"Noted. I'll remember that {name} {fact}, Sir."

    @tool
    def recall_person(name: str) -> str:
        """Recall everything Jarvis knows about a person. Call when user asks about a specific person by name. Parameter 'name' must be a plain string like 'John' or 'Anna'."""
        from modules.people_module import find_profile_by_name
        if not isinstance(name, str):
            name = str(name)
        result = find_profile_by_name(name.strip())
        if not result:
            return f"I don't have any information about {name} yet, Sir."
        if isinstance(result, dict) and result.get("multiple"):
            names = [m["name"] for m in result["matches"]]
            return f"Sir, I know multiple people named {name}: {', '.join(names)}. Could you clarify?"
        facts = result.get("facts", [])
        relationship = result.get("relationship", "acquaintance")
        facts_str = "; ".join(facts) if facts else "nothing specific yet"
        return f"{result['name']} is your {relationship}. I know: {facts_str}."

    @tool
    def introduce_person(name: str, relationship: str, personality: str = "polite") -> str:
        """Create a profile for a new person. Use ONLY when user explicitly states someone's name. All parameters must be plain strings."""
        from modules.people_module import create_profile, find_profile_by_name
        if not isinstance(name, str):
            name = str(name)
        name = name.strip()
        existing = find_profile_by_name(name)
        if existing and not isinstance(existing, dict):
            return f"Sir, I already know someone named {name}."
        create_profile(name, relationship, personality)
        return f"Pleasure to meet you, {name}. I'll remember you as {relationship} of Sir's."

    # ------------------------------------------------------------------ #
    #  Час / таймер / нагадування                                          #
    # ------------------------------------------------------------------ #

    @tool
    def get_time(query: str = "") -> str:
        """Get current time and date. Use when user asks what time it is, what day it is, or current date."""
        from datetime import datetime
        now = datetime.now()
        return (
            f"Current time: {now.strftime('%H:%M')}. "
            f"Date: {now.strftime('%A, %d %B %Y')}."
        )

    @tool
    def set_timer(minutes: int) -> str:
        """Set a silent timer for X minutes. Use when user says set timer for N minutes without a specific message."""
        import threading
        def _ring():
            time.sleep(minutes * 60)
            print(f"\n[TIMER] ⏰ {minutes} хвилин минуло!")
        threading.Thread(target=_ring, daemon=True).start()
        return f"Timer set for {minutes} minutes, Sir."

    @tool
    def set_reminder(message: str, minutes: float = 0, when: str = "") -> str:
        """Set a voiced reminder. ALWAYS call this tool whenever the user says 'remind me to X',
        'set a reminder', or similar — even if a similar reminder may already exist. Do NOT decide
        on your own that a reminder is a duplicate and skip calling; the user can have multiple
        reminders. Never reply 'you already have that reminder' without calling this tool first.
        message: what to remind about.
        minutes: how many minutes from now (for 'in 5 minutes', 'in 2 hours').
        when: natural language like 'tomorrow at 9am', 'next monday 14:00', 'in 3 days' (for absolute dates).
        Use either minutes OR when, not both."""
        if reminder_module is None:
            return "Sir, the reminder system is offline."

        if when and not minutes:
            try:
                import dateparser
                from datetime import datetime
                target = dateparser.parse(
                    when,
                    settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False},
                )
                if not target:
                    return f"Sir, I couldn't understand '{when}'. Try 'tomorrow at 9am' or 'in 3 hours'."
                delta = (target - datetime.now()).total_seconds() / 60
                if delta <= 0:
                    return f"Sir, '{when}' is in the past."
                minutes = delta
            except ImportError:
                return "Sir, dateparser library is not installed. Run: pip install dateparser"

        if minutes <= 0:
            return "Sir, please specify either minutes or a future time."

        seconds = int(minutes * 60)
        reminder_module.set(message, seconds)
        if minutes < 1:
            time_str = f"{int(seconds)} seconds"
        elif minutes < 60:
            time_str = f"{int(minutes)} minute{'s' if int(minutes) != 1 else ''}"
        elif minutes < 1440:
            hours = minutes / 60
            time_str = f"{hours:.1f} hour{'s' if hours != 1 else ''}"
        else:
            days = minutes / 1440
            time_str = f"{days:.1f} day{'s' if days != 1 else ''}"
        return f"Reminder set for {time_str} from now: '{message}', Sir."

    @tool
    def add_weather_trigger(action: str, phenomenon: str = "rain") -> str:
        """Set a conditional reminder that fires when a weather phenomenon is expected.
        Use when user says 'remind me to X if it rains', 'warn me when it snows', etc.
        action: what to remind (e.g. 'take an umbrella').
        phenomenon: one of rain, snow, storm, fog, freezing."""
        if triggers_module is None:
            return "Sir, the trigger system is offline."
        phenomenon = phenomenon.lower().strip()
        valid = ["rain", "snow", "storm", "fog", "freezing"]
        if phenomenon not in valid:
            phenomenon = "rain"
        triggers_module.add(action, {"type": "weather", "phenomenon": phenomenon})
        return f"Done, Sir. I'll remind you to {action} when {phenomenon} is expected."

    @tool
    def add_temperature_trigger(action: str, op: str, value: float, feels_like: bool = False) -> str:
        """Set a conditional reminder that fires when temperature crosses a threshold.
        Use for 'tell me when it drops below 0', 'warn me if it gets hotter than 25'.
        action: what to remind.
        op: comparison, one of '<', '>', '<=', '>='.
        value: temperature in Celsius.
        feels_like: True to use feels-like temperature instead of actual."""
        if triggers_module is None:
            return "Sir, the trigger system is offline."
        if op not in ["<", ">", "<=", ">="]:
            return "Sir, comparison must be one of < > <= >=."
        ctype = "temp_feels" if feels_like else "temp"
        triggers_module.add(action, {"type": ctype, "op": op, "value": float(value)})
        kind = "feels-like" if feels_like else "temperature"
        return f"Done, Sir. I'll remind you to {action} when {kind} is {op} {value}\u00b0C."

    @tool
    def search_youtube(query: str) -> str:
        """Search YouTube and show results in the HUD. Use when the user says
        'play X on YouTube', 'find X on YouTube', 'search YouTube for X'.
        query: what to search for."""
        if youtube_module is None or not youtube_module.available():
            return "Sir, YouTube search is not configured. Add YOUTUBE_API_KEY to .env."
        res = youtube_module.search(query, max_results=5)
        if not res.get("ok"):
            return f"Sir, YouTube search failed: {res.get('error', 'unknown')}."
        # пушимо результати в HUD
        try:
            from modules.hud_module import push_youtube_results
            push_youtube_results(res)
        except Exception:
            pass
        items = res.get("items", [])
        if not items:
            return f"Sir, I found nothing for '{query}'."
        top = items[0]
        return f"Found {len(items)} results for '{query}', Sir. Top: {top['title']} by {top['channel']}. Showing them on the display."

    @tool
    def list_triggers() -> str:
        """List all active conditional triggers (weather/temperature). Use when user asks
        'what triggers do I have', 'what are my conditions'."""
        if triggers_module is None:
            return "Sir, the trigger system is offline."
        return triggers_module.describe_active()

    @tool
    def remove_trigger(action_substring: str) -> str:
        """Remove conditional trigger(s) matching the given text. Use when user says
        'cancel the umbrella trigger', 'remove the rain reminder'."""
        if triggers_module is None:
            return "Sir, the trigger system is offline."
        n = triggers_module.remove_by_action(action_substring)
        if n:
            return f"Removed {n} trigger(s), Sir."
        return f"Sir, I found no trigger matching '{action_substring}'."

    # ------------------------------------------------------------------ #
    #  Логування дня                                                       #
    # ------------------------------------------------------------------ #

    @tool
    def summarize_day(query: str = "") -> str:
        """Read and summarize today's activity log from file. ALWAYS call this tool when user asks what we did today, daily recap, or summary of the day. NEVER summarize from memory alone."""
        from day_logger import get_log_summary_prompt
        prompt = get_log_summary_prompt()
        if not prompt:
            return "Sir, the activity log is empty. Quite an uneventful day so far."
        try:
            response = llm.invoke([
                SystemMessage(content="You are JARVIS. Summarize the day's activity concisely and wittily in 3-5 sentences."),
                HumanMessage(content=prompt)
            ])
            return response.content.strip()
        except Exception as e:
            return f"Sir, I couldn't generate the summary: {e}"

    # ------------------------------------------------------------------ #
    #  Gmail                                                               #
    # ------------------------------------------------------------------ #

    @tool
    def check_email(max_results: int = 5) -> str:
        """Check unread emails. Use when user asks about emails, inbox, new messages, or any mail."""
        try:
            from modules.gmail_module import GmailModule
            return GmailModule().get_unread_summary(max_results)
        except Exception as e:
            return f"Sir, email system is unavailable: {e}"

    @tool
    def send_email(to: str, subject: str, body: str) -> str:
        """Send an email. Use when user says send email/message to someone.
        to: recipient email or name. subject: email subject. body: email text."""
        try:
            from modules.gmail_module import GmailModule
            gm = GmailModule()
            # Якщо передали ім'я а не email — шукаємо адресу
            if "@" not in to:
                found = gm.find_sender_email(to)
                if found:
                    to = found
                else:
                    return f"Sir, I couldn't find an email address for '{to}'."
            return gm.send_email(to, subject, body)
        except Exception as e:
            return f"Sir, I couldn't send the email: {e}"

    # ------------------------------------------------------------------ #
    #  Google Calendar                                                     #
    # ------------------------------------------------------------------ #

    @tool
    def check_calendar(hours: int = 24) -> str:
        """Check upcoming calendar events. Use when user asks about schedule, plans, meetings, or what's next.
        hours: how many hours ahead to look (default 24)."""
        try:
            from modules.calendar_module import CalendarModule
            return CalendarModule().get_upcoming_summary(hours)
        except Exception as e:
            return f"Sir, calendar system is unavailable: {e}"

    @tool
    def add_calendar_event(title: str, date: str, time: str = "",
                           duration_minutes: int = 60, location: str = "") -> str:
        """Add event to Google Calendar. Use when user says add event, schedule meeting, remind me on date.
        Do NOT use this for workouts / training logs (e.g. 'add workout', 'тренування',
        'I trained ...') — those go to log_workout, even if phrased with 'add' or a past time.
        title: event name.
        date: can be 'YYYY-MM-DD' or natural language like 'tomorrow', 'next monday', 'in 3 days', 'friday'.
        time: 'HH:MM' (24h) or natural like '3pm', '9:30am'. If empty, defaults to 12:00.
        duration_minutes: default 60. location: optional."""
        try:
            from modules.calendar_module import CalendarModule
            from datetime import datetime, timedelta
            import dateparser

            # Гнучкий парсинг — об'єднуємо date + time і даємо dateparser
            combined = f"{date} {time}".strip()
            start_dt = dateparser.parse(
                combined,
                settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False},
            )

            if not start_dt:
                return (f"Sir, I couldn't parse the date/time '{combined}'. "
                        f"Try 'tomorrow 3pm' or '2026-05-30 15:00'.")

            # Якщо time не вказано — defaults to noon
            if not time and start_dt.hour == 0 and start_dt.minute == 0:
                start_dt = start_dt.replace(hour=12)

            # Захист: подія не може бути в минулому
            if start_dt < datetime.now():
                return f"Sir, '{combined}' resolves to a past date ({start_dt.strftime('%Y-%m-%d %H:%M')}). Please specify a future date."

            end_dt = start_dt + timedelta(minutes=duration_minutes)

            tz = "+03:00"  # Kyiv time
            start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz
            end_iso   = end_dt.strftime("%Y-%m-%dT%H:%M:%S") + tz

            result = CalendarModule().create_event(title, start_iso, end_iso, location)
            return f"{result} Scheduled for {start_dt.strftime('%A, %d %b %Y at %H:%M')}."

        except ImportError:
            return "Sir, dateparser library is not installed. Run: pip install dateparser"
        except Exception as e:
            return f"Sir, I couldn't create the event: {e}"

    # ------------------------------------------------------------------ #
    #  Contacts                                                            #
    # ------------------------------------------------------------------ #

    @tool
    def find_contact(name: str) -> str:
        """Find a contact by name in Google Contacts. ALWAYS call this tool when user asks for phone number, email, or contact info of any person. NEVER guess or invent phone numbers."""
        try:
            from modules.contacts_module import ContactsModule
            return ContactsModule().find_summary(name)
        except Exception as e:
            return f"Sir, contacts system unavailable: {e}"

    # ------------------------------------------------------------------ #
    #  YouTube                                                             #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    #  API Guard                                                           #
    # ------------------------------------------------------------------ #

    @tool
    def api_usage_status(reason: str = "") -> str:
        """Show real Google API usage from file. ALWAYS call this tool when user asks about api usage, quota, limits, or how many calls left. NEVER estimate or guess the numbers."""
        try:
            from api_guard import guard
            return guard.status()
        except Exception as e:
            return f"Sir, couldn't retrieve API stats: {e}"

    # ------------------------------------------------------------------ #
    #  Vision                                                              #
    # ------------------------------------------------------------------ #

    @tool
    def analyze_screenshot(reason: str = "") -> str:
        """Analyze the latest screenshot using AI vision. Use when user says what's on screen, analyze screenshot, describe screen."""
        try:
            from modules.vision_module import VisionModule
            return VisionModule().analyze_latest_screenshot()
        except Exception as e:
            return f"Sir, vision system unavailable: {e}"

    @tool
    def read_text_from_screenshot(reason: str = "") -> str:
        """Read text from the latest screenshot using OCR. Use when user says read text on screen, what does it say, extract text."""
        try:
            from modules.vision_module import VisionModule
            from pathlib import Path
            screenshots_dir = Path("screenshots")
            files = sorted(screenshots_dir.glob("*.png"), key=lambda f: f.stat().st_mtime)
            if not files:
                return "Sir, no screenshots found. Take a screenshot first."
            return VisionModule().read_text(str(files[-1]))
        except Exception as e:
            return f"Sir, OCR failed: {e}"

    # ------------------------------------------------------------------ #
    #  Drive                                                               #
    # ------------------------------------------------------------------ #

    @tool
    def find_drive_file(query: str) -> str:
        """Search for a file in Google Drive by name or keyword. Use when user says find file, search drive, open document, where is my file."""
        try:
            from google_auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            service = build("drive", "v3", credentials=creds)
            results = service.files().list(
                q="name contains '" + query.replace("'", "") + "' and trashed=false",
                pageSize=5,
                fields="files(id, name, mimeType, webViewLink)",
            ).execute()
            files = results.get("files", [])
            if not files:
                return f"Sir, no files found matching '{query}' in your Drive."
            lines = [f"Found {len(files)} file(s) matching '{query}', Sir:"]
            for f in files:
                lines.append(f"- {f['name']} ({f.get('webViewLink', 'no link')})")
            return " ".join(lines)
        except Exception as e:
            return f"Sir, Drive search failed: {e}"

    @tool
    def open_drive_file(query: str) -> str:
        """Find and open a file from Google Drive in browser. Use when user says open my file, open document from drive."""
        try:
            import webbrowser
            from google_auth import get_credentials
            from googleapiclient.discovery import build
            creds = get_credentials()
            service = build("drive", "v3", credentials=creds)
            results = service.files().list(
                q="name contains '" + query.replace("'", "") + "' and trashed=false",
                pageSize=1,
                fields="files(id, name, webViewLink)",
            ).execute()
            files = results.get("files", [])
            if not files:
                return f"Sir, no file found matching '{query}'."
            f = files[0]
            link = f.get("webViewLink", "")
            if link:
                webbrowser.open(link)
                return f"Opening '{f['name']}' in browser, Sir."
            return f"Sir, file found but no link available for '{f['name']}'."
        except Exception as e:
            return f"Sir, couldn't open Drive file: {e}"

    # ------------------------------------------------------------------ #
    #  Network                                                             #
    # ------------------------------------------------------------------ #

    @tool
    def network_status(reason: str = "") -> str:
        """Get network info: IP address, connection status. Use when user asks what is my IP, network status, am I connected."""
        try:
            import socket
            import requests as req

            # Локальний IP
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)

            # Публічний IP
            try:
                pub = req.get("https://api.ipify.org", timeout=5).text.strip()
            except Exception:
                pub = "unavailable"

            return (
                f"Network status, Sir. "
                f"Hostname: {hostname}. "
                f"Local IP: {local_ip}. "
                f"Public IP: {pub}."
            )
        except Exception as e:
            return f"Sir, network check failed: {e}"
    # ------------------------------------------------------------------ #
    #  Health                                                             #
    # ------------------------------------------------------------------ #

    @tool
    def health_report(period: str = "week") -> str:
        """Analyzes Samsung Health data (steps, sleep, heart rate, exercise) for a period.
        Args:
            period: today, week, month, year, or all
        Returns: a multi-section text report.
        Use when user asks about their health, steps, sleep, fitness, or activity."""
        from modules.health_analytics.jarvis_integration import health_report_tool
        return health_report_tool(period=period, send_telegram=False)


    @tool
    def health_report_to_telegram(period: str = "week") -> str:
        """Sends a Samsung Health report AND dashboard image to the user's Telegram.
        Args:
            period: today, week, month, year, or all
        Use when user explicitly asks to send their health report/dashboard to Telegram."""
        from modules.health_analytics.jarvis_integration import health_report_tool
        return health_report_tool(period=period, send_telegram=True)
    # ------------------------------------------------------------------ #
    #  Money                                                            #
    # ------------------------------------------------------------------ #
    @tool
    def money_report(period: str = "month") -> str:
        """Analyzes Money Manager expenses and income for a period.
        Args:
            period: today, week, month, year, or all
        Returns: a finance report (spent, earned, net, top categories, needs/wants split).
        Use when user asks about money, spending, expenses, budget, finance, savings."""
        from modules.money_analytics.jarvis_integration import money_report_tool
        return money_report_tool(period=period)


    @tool
    def money_report_to_telegram(period: str = "month") -> str:
        """Sends a Money Manager finance report AND dashboard image to user's Telegram.
        Args:
            period: today, week, month, year, or all
        Use when user explicitly asks to send their finance report to Telegram."""
        from modules.money_analytics.jarvis_integration import money_report_tool
        return money_report_tool(period=period, send_telegram=True)

    # ------------------------------------------------------------------ #
    #  Mood                                                              #
    # ------------------------------------------------------------------ #
    @tool
    def log_mood(score: int, tags: str = "", note: str = "") -> str:
        """Log the user's current mood. Use when user states how they feel with a 1-10 rating,
        e.g. 'mood 7 tired', 'log my mood as 8 happy', 'I feel like a 4 today, anxious'.
        Args:
            score: 1-10 rating.
            tags: optional comma/semicolon-separated mood tags (energetic, tired, anxious, happy, calm, stressed, etc).
            note: optional free-text note.
        """
        from modules.mood_analytics.jarvis_integration import log_mood_tool
        return log_mood_tool(score=score, tags=tags, note=note, source="voice")

    @tool
    def mood_report(period: str = "week") -> str:
        """Analyzes the user's logged mood for a period.
        Args:
            period: today, week, month, year, or all
        Returns: average, trend, morning vs evening, top tags, logging streak.
        Use when user asks about their mood, how they've been feeling, mood trend or stats."""
        from modules.mood_analytics.jarvis_integration import mood_report_tool
        return mood_report_tool(period=period, send_telegram=False)

    @tool
    def mood_report_to_telegram(period: str = "week") -> str:
        """Sends a mood report AND dashboard image to the user's Telegram.
        Args:
            period: today, week, month, year, or all
        Use when user explicitly asks to send their mood report to Telegram."""
        from modules.mood_analytics.jarvis_integration import mood_report_tool
        return mood_report_tool(period=period, send_telegram=True)

    @tool
    def cross_correlation_report() -> str:
        """Analyzes relationships between the user's sleep, steps, resting heart rate, mood and spending.
        Finds which metrics move together (e.g. does better sleep mean better mood, does low mood mean more spending).
        Returns the strongest correlations, lagged effects and actionable insights.
        Use when the user asks how their habits relate, what affects their mood/sleep/spending,
        or asks for cross-metric patterns and correlations."""
        from modules.correlation_analytics.jarvis_integration import cross_correlation_report_tool
        return cross_correlation_report_tool(send_telegram=False)

    @tool
    def cross_correlation_to_telegram() -> str:
        """Sends the cross-correlation report AND dashboard image to the user's Telegram.
        Use when the user explicitly asks to send correlation analysis to Telegram."""
        from modules.correlation_analytics.jarvis_integration import cross_correlation_report_tool
        return cross_correlation_report_tool(send_telegram=True)

    # ------------------------------------------------------------------ #
    #  Workout (силові тренування + мʼязова мапа)                         #
    # ------------------------------------------------------------------ #
    @tool
    def log_workout(exercise: str) -> str:
        """Record that the user TRAINED specific muscles, to light up the HUD muscle map.
        This is NOT a calendar event and has NOTHING to do with scheduling — never use
        add_calendar_event for workouts. ALWAYS use this tool for ANY phrasing about
        training muscles, including imperative ones:
          'add workout shoulders, chest', 'log workout legs', 'workout: bench press, rows',
          'тренування: груди, трицепс', 'додай тренування ноги', 'залогуй тренування присідання',
          'я тренував спину', 'I trained chest today', 'I did bench press and squats'.
        Even if the user says 'add' or gives a past time like '2 hours ago', it is still a
        workout LOG, not a calendar entry. Accepts multiple exercises/muscles in one string
        (comma / 'i' / 'та' / 'and' separated), Ukrainian or English, exercise names or
        muscle-group names.
        Args:
            exercise: the exercise(s) or muscle group(s) the user trained.
        """
        from modules.workout_module import get_workout
        return get_workout(llm=llm).log_workout(exercise)

    @tool
    def workout_stats(reason: str = "") -> str:
        """Report which muscle groups were trained recently and their freshness
        (trained in last 24h / 48h / 72h). Use when the user asks what they trained,
        which muscles are fresh/recovered, 'what did I train this week', 'muscle map status',
        'які мʼязи я качав', 'що сьогодні тренував'."""
        from modules.workout_module import get_workout
        return get_workout(llm=llm).get_summary()

    # ------------------------------------------------------------------ #
    #  ARMOR BUILD — трекер 3D-друку броні (НЕ фізичне open/close armor)  #
    # ------------------------------------------------------------------ #
    @tool
    def armor_build_status(part: str, status: str) -> str:
        """Set the 3D-PRINT build status of an Iron Man armor part on the HUD armor tracker.
        This is about PRINTING/BUILDING the cosplay suit, NOT opening/closing a worn suit
        (that's open_armor/close_armor). Use for phrasing like:
          'armor chest done', 'armor helmet printing', 'mark the left thigh as done',
          'set biceps to not printed', 'armor legs done'.
        Args:
            part: armor part name (helmet, chest, neck, abs, cod, shoulders, arms, biceps,
                  triceps, forearms, thighs, knees, shins, feet, upperback, legs, etc).
            status: one of 'done', 'printing', 'not_printed' (synonyms: ready/finished=done,
                    todo/pending/reset=not_printed).
        """
        from modules.armor_module import get_armor
        return get_armor().command(part, status)

    @tool
    def armor_build_progress(reason: str = "") -> str:
        """Report overall Iron Man armor BUILD progress (how much of the suit is 3D-printed):
        percent complete, parts done/total, parts currently printing. Use when the user asks
        'how's the armor coming along', 'suit build progress', 'how much of the Mark is done',
        'скільки броні готово', 'як просувається костюм'."""
        from modules.armor_module import get_armor
        return get_armor().get_summary()

    # ------------------------------------------------------------------ #
    #  RAG по логах (семантичний пошук по історії)                        #
    # ------------------------------------------------------------------ #
    @tool
    def search_my_history(query: str) -> str:
        """Search the user's own past conversations and daily logs semantically.
        ALWAYS call this when the user asks about their own past, e.g. 'what did I do
        yesterday', 'when did I last listen to music', 'have we talked about X before',
        'what was I working on last week'. NEVER answer such questions from memory alone.
        query: what to look for in the logs."""
        from modules.rag_module import get_rag
        context = get_rag().search_as_context(query)
        if not context:
            return "Sir, I found nothing relevant in your logs."
        return context

    @tool
    def reindex_history(reason: str = "") -> str:
        """Rebuild the semantic index over all daily logs. Use when user says
        reindex my history, rebuild the log index, or update RAG."""
        from modules.rag_module import get_rag
        return get_rag().reindex()

    return [
        play_music, set_volume, stop_music,
        fetch_location, fetch_weather, get_route, find_nearby,
        system_status, diagnose_self, open_armor, close_armor,
        open_app, search_web, take_screenshot, lock_screen,
        remember_person, recall_person, introduce_person,
        get_time, set_timer, set_reminder,
        add_weather_trigger, add_temperature_trigger, list_triggers, remove_trigger,
        search_youtube,
        summarize_day,
        check_email, send_email,
        check_calendar, add_calendar_event,
        find_contact,
        analyze_screenshot, read_text_from_screenshot,
        api_usage_status,
        find_drive_file, open_drive_file,
        network_status, health_report, health_report_to_telegram, 
        money_report, money_report_to_telegram,
        log_mood, mood_report, mood_report_to_telegram,
        cross_correlation_report, cross_correlation_to_telegram,
        log_workout, workout_stats,
        armor_build_status, armor_build_progress,
        search_my_history, reindex_history
    ]


class JarvisAgent:
    def __init__(self, music_module, nav_module, sensors_module, reminder_module=None, triggers_module=None, youtube_module=None):
        self.models = [
            "meta-llama/llama-4-scout-17b-16e-instruct",  # основна
            "llama-3.3-70b-versatile",                    # fallback 1
            "llama-3.1-8b-instant",                       # fallback 2
            "gemini",                                     # fallback 3 — Google резерв
        ]
        self.current_model_index = 0

        self.llm = self._create_llm(self.models[0], max_tokens=220)
        self.llm_normalize = self._create_llm(self.models[0], max_tokens=15)

        self.music_module = music_module
        self.reminder_module = reminder_module
        self.triggers_module = triggers_module
        self.youtube_module = youtube_module
        self.tools = create_tools(music_module, nav_module, sensors_module, self.llm_normalize, reminder_module, triggers_module, youtube_module)
        self._nav_module = nav_module
        self._sensors_module = sensors_module
        self.tools_map = {t.name: t for t in self.tools}
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        self.chat_history = load_history()
        self.active_mode = "jarvis"

        # Оновлюємо HUD з реальною поточною моделлю
        try:
            from modules.hud_module import update_hud
            update_hud("model", self.models[0].split("/")[-1])
        except Exception:
            pass

        # Запускаємо фонове оновлення short/long memory.
        # ВАЖЛИВО: окремий llm з великим лімітом токенів — інакше JSON-вивід
        # (до 20 фактів) ріжеться по ліміту і ламає json.loads (Unterminated string).
        self.llm_memory = self._create_llm(self.models[0], max_tokens=1024)
        schedule_memory_updates(self.llm_memory)

    def set_personality(self, mode: str):
        """Перемикає характер: 'jarvis' або 'ultron'."""
        self.active_mode = mode.lower()
        print(f"[AGENT] Особистість: {self.active_mode.upper()}")

    def attach_triggers(self, triggers_module):
        """Пізнє підключення модуля умовних тригерів (потребує weather_alert,
        який створюється після Brain). Перебудовує набір тулів."""
        self.triggers_module = triggers_module
        self.tools = create_tools(
            self.music_module, self._nav_module, self._sensors_module,
            self.llm_normalize, self.reminder_module, triggers_module, self.youtube_module
        )
        self.tools_map = {t.name: t for t in self.tools}
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        print("[AGENT] Тригери підключено, тули оновлено")

    def _create_llm(self, model: str, max_tokens: int = 80):
        if model == "gemini":
            import os
            if _GEMINI_AVAILABLE and os.getenv("GOOGLE_API_KEY"):
                return ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    temperature=0.5,
                    max_output_tokens=max_tokens * 4,
                    google_api_key=os.getenv("GOOGLE_API_KEY"),
                )
            # Якщо Gemini недоступний — повертаємось на llama-3.1-8b
            return ChatGroq(model="llama-3.1-8b-instant", temperature=0.5, max_tokens=max_tokens)
        return ChatGroq(model=model, temperature=0.5, max_tokens=max_tokens)

    def _switch_to_next_model(self, skip_small: bool = False):
        """Перемикає на наступну модель у ланцюзі fallback.
        skip_small=True — пропускає llama-3.1-8b-instant: на запитах із тулами
        вона не вміщає схему всіх тулів у свій ліміт 6000 TPM і дає 413."""
        self.current_model_index += 1
        # пропускаємо малу модель, якщо це tool-запит (вона все одно впаде на 413)
        while (skip_small
               and self.current_model_index < len(self.models)
               and "8b" in self.models[self.current_model_index]):
            print(f"[AGENT] Пропускаємо {self.models[self.current_model_index]} "
                  f"(замала для схеми тулів)")
            self.current_model_index += 1
        if self.current_model_index >= len(self.models):
            self.current_model_index = 0
            print("[AGENT] Всі моделі вичерпали ліміт. Повертаємось на основну.")
            return False
        new_model = self.models[self.current_model_index]
        print(f"[AGENT] Переключаємось на модель: {new_model}")
        self.llm = self._create_llm(new_model, max_tokens=220)
        self.llm_normalize = self._create_llm(new_model, max_tokens=15)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        try:
            from modules.hud_module import update_hud
            update_hud("model", new_model.split("/")[-1])
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------ #
    #  MoE-роутер: вибір моделі за складністю запиту                       #
    # ------------------------------------------------------------------ #
    # ІНВЕРТОВАНА логіка: за замовчуванням усе йде на основну модель З ТУЛАМИ.
    # На малу/велику модель (БЕЗ тулів) відправляємо лише те, що впевнено
    # розпізнане як балачка / reasoning. Причина: вгадувати "чи треба тул"
    # словником ключових слів — програшна гонка (кава/чай/вино/аптека/...),
    # і будь-яке слово, що ми не передбачили, ламає виклик тула. Тому
    # рішення "чи потрібен тул" віддаємо самій моделі з тулами, а не роутеру.

    # Маркери складного reasoning (текст, без тулів) → велика модель.
    _HEAVY_HINTS = (
        "explain", "why is", "why do", "why does", "how does", "how do",
        "compare", "difference between", "write a", "write me a", "essay",
        "analyze", "step by step", "pros and cons", "what is the meaning",
        "поясни", "чому", "як працює", "порівняй", "різниця між", "напиши",
        "проаналізуй", "по кроках", "за і проти", "розпиши", "що означає",
    )

    # Дуже вузький whitelist чистої балачки → мала швидка модель.
    # Тільки якщо ВЕСЬ запит — це коротка світська фраза без запиту даних/дій.
    _CHITCHAT = {
        # привітання
        "hi", "hello", "hey", "yo", "sup", "good morning", "good evening",
        "good night", "morning", "привіт", "привіт жарвіс", "добрий ранок",
        "добрий вечір", "доброго ранку", "хелло", "хай",
        # подяки / ввічливість
        "thanks", "thank you", "thx", "cheers", "appreciated", "nice",
        "cool", "great", "awesome", "ok", "okay", "got it",
        "дякую", "дяка", "клас", "круто", "супер", "ок", "окей", "зрозумів",
        # стан / світська балачка
        "how are you", "how's it going", "what's up", "whats up",
        "як справи", "як ти", "що нового", "як воно",
        # прощання
        "bye", "goodbye", "see you", "good bye", "бувай", "па", "до зустрічі",
    }

    @staticmethod
    def _trim_sentences(text: str, max_sentences: int = 3) -> str:
        """Обрізає відповідь до max_sentences речень (для голосу — коротко).
        Гарантія проти 'трактатів', навіть якщо модель проігнорувала ліміт токенів.
        Не чіпає коротке; зберігає кінцеву пунктуацію."""
        if not text:
            return text
        # розбиваємо по . ! ? (враховуючи лапки/дужки після знаку)
        parts = re.findall(r'[^.!?]*[.!?]+["\')\]]?\s*', text)
        if not parts:
            return text.strip()
        if len(parts) <= max_sentences:
            return text.strip()
        return "".join(parts[:max_sentences]).strip()

    def _route_complexity(self, user_input: str) -> str:
        """Інвертований роутер. Повертає 'tools' | 'small' | 'big'.
        ДЕФОЛТ — 'tools' (основна модель з тулами вирішує сама, чи кликати тул).
        'small'/'big' — лише для впевнено розпізнаної балачки / reasoning.
        """
        text = user_input.lower().strip()
        # прибираємо кінцеву пунктуацію для порівняння з whitelist
        stripped = text.rstrip("!?.,…ʼ'\" ")
        words = text.split()
        n = len(words)

        # 1) Важкий reasoning (пояснення/порівняння/есе) → велика модель без тулів.
        #    АЛЕ тільки якщо це НЕ про власні дані юзера (ті йдуть у тули).
        if any(h in text for h in self._HEAVY_HINTS) or n > 40:
            return "big"

        # 2) Чиста балачка → мала модель. Жорстко: весь запит має бути у whitelist
        #    (після зняття пунктуації), інакше не ризикуємо.
        if stripped in self._CHITCHAT:
            return "small"

        # 3) Усе інше → основна модель З ТУЛАМИ.
        #    Краще зайвий раз піти з тулами (і модель сама вирішить не кликати),
        #    ніж відправити запит-на-дію в балачку й отримати галюцинацію.
        return "tools"

    def _maybe_armor(self, user_input: str):
        """Детермінований роутер команд трекера збірки броні.
        Повертає рядок-відповідь, якщо це про armor build, інакше None.
        Обходить ненадійний tool-selection моделі (галюцинувала 'done' без виклику)."""
        import re as _re
        text = user_input.lower().strip()

        # --- запит прогресу збірки ---
        PROGRESS_HINTS = (
            "armor progress", "suit progress", "suit build", "armor build status",
            "how's the armor", "hows the armor", "how is the armor",
            "how's the suit", "hows the suit", "how much of the mark",
            "how much armor", "mark progress",
            "скільки броні", "прогрес броні", "як просувається костюм",
            "стан броні", "скільки костюма",
        )
        if any(h in text for h in PROGRESS_HINTS):
            try:
                return str(self.tools_map["armor_build_progress"].invoke({"reason": ""}))
            except Exception as e:
                print(f"[ARMOR] progress error: {e}")
                return None

        # --- встановлення статусу деталі ---
        # тригер: команда має згадувати armor/броню/сут-білд
        if not any(t in text for t in ("armor", "броня", "броні", "suit", "костюм", "mark suit")):
            return None

        # визначаємо статус
        status = None
        if any(w in text for w in ("done", "ready", "finished", "complete", "готов", "надрукован", "надрукував")):
            status = "done"
        elif any(w in text for w in ("printing", "in progress", "друку", "печат")):
            status = "printing"
        elif any(w in text for w in ("not printed", "not_printed", "todo", "pending", "reset",
                                      "not done", "не надрукован", "не готов", "скинь")):
            status = "not_printed"
        if status is None:
            return None  # armor згадано, але без статусу → хай іде на модель/прогрес

        # витягуємо назву деталі: прибираємо armor-слова й статус-слова
        from modules.armor_module import get_armor
        cleaned = text
        JUNK = (
            "armor build", "mark suit", "armor", "suit", "костюм", "броня", "броню", "броні", "mark",
            "done", "ready", "finished", "complete", "готово", "готова", "готовий",
            "надрукований", "надрукована", "надрукував", "printing", "in progress",
            "друкується", "друкую", "печатається", "not printed", "not_printed",
            "todo", "pending", "reset", "not done", "не надруковано", "не готово", "скинь",
            "set", "mark", "as", "the", "to", "is", "now", "встанови", "постав", "признач",
            "in", "of", "my", "please", "for", "on", "a", "an", "будь", "ласка",
        )
        for j in sorted(JUNK, key=len, reverse=True):
            cleaned = _re.sub(r"(?<!\w)" + _re.escape(j) + r"(?!\w)", " ", cleaned)
        cleaned = _re.sub(r"\s+", " ", cleaned).strip(" ,;:.-")

        if not cleaned:
            return ("Armor noted, Sir, but which part? "
                    "Tell me e.g. 'armor chest done'.")

        # перевіряємо, чи це реальна деталь
        ids = get_armor().resolve_parts(cleaned)
        if not ids:
            return None  # не впізнали деталь → не наша команда

        try:
            return str(self.tools_map["armor_build_status"].invoke(
                {"part": cleaned, "status": status}))
        except Exception as e:
            print(f"[ARMOR] status error: {e}")
            return None

    def _maybe_workout(self, user_input: str):
        """Детермінований роутер workout-команд. Повертає рядок-відповідь,
        якщо це явно про тренування, інакше None.
        Обходить ненадійний tool-selection моделі (scout галюцинує лог)."""
        import re as _re
        text = user_input.lower().strip()

        # --- 1) запит статистики ("що я тренував", "які мʼязи свіжі") ---
        STAT_HINTS = (
            "what did i train", "what have i trained", "which muscles",
            "muscle map status", "workout stats", "workout status",
            "що я тренував", "що тренував", "які мʼязи", "які м'язи",
            "що качав", "які мязи", "стан мапи", "статус тренувань",
        )
        if any(h in text for h in STAT_HINTS):
            try:
                return str(self.tools_map["workout_stats"].invoke({"reason": ""}))
            except Exception as e:
                print(f"[WORKOUT] stats error: {e}")
                return None

        # --- 2) лог тренування ---
        # тригер-слова, що ОДНОЗНАЧНО вмикають режим логування
        LOG_TRIGGERS = (
            "workout", "trained", "i did", "worked out", "log workout",
            "add workout", "exercise", "exercises",
            "тренув", "тренуванн", "залогуй тренув", "качав", "накачав",
            "позанімав", "робив вправ", "зробив вправ",
        )
        # слабкі тригери-дієслова (add/log/plus/додай) — спрацьовують лише якщо
        # рештою тексту є РЕАЛЬНА вправа/мʼязова група (перевіряємо модулем нижче)
        WEAK_TRIGGERS = (
            "add ", "log ", "plus ", "also ", "and ",
            "додай", "плюс", "ще ", "також",
        )
        has_strong = any(t in text for t in LOG_TRIGGERS)
        has_weak = any(t in text for t in WEAK_TRIGGERS)
        if not has_strong and not has_weak:
            return None

        # вирізаємо службові префікси/слова, лишаємо тільки назви вправ/мʼязів.
        # ВАЖЛИВО: чистимо лише ЦІЛІ слова/фрази (по межах), щоб не зʼїсти
        # підрядок усередині слова (напр. 'це' всередині 'біцепс').
        cleaned = text
        JUNK_PHRASES = (
            "i had a workout", "i had workout", "i did a workout",
            "i worked out", "log my workout", "log workout",
            "add a workout", "add workout", "my workout was",
            "залогуй тренування", "додай тренування",
            "i had", "i did", "workout", "today", "just now", "earlier",
            "залогуй", "додай", "я тренував", "тренував", "я качав",
            "накачав", "качав", "тренувався", "тренувалася", "тренуюсь",
            "потренував", "сьогодні", "щойно", "були", "було",
            "its", "it's", "it is", "це",
            # слабкі дієслова-додавання теж прибираємо з тексту вправи
            "add", "log", "plus", "also", "and", "плюс", "ще", "також", "some",
        )
        # довші фрази — першими, щоб не лишати хвости
        for junk in sorted(JUNK_PHRASES, key=len, reverse=True):
            cleaned = _re.sub(r"(?<!\w)" + _re.escape(junk) + r"(?!\w)", " ", cleaned)
        # прибираємо сполучники-розриви на краях і зайві коми/пробіли
        cleaned = _re.sub(r"\s+", " ", cleaned).strip(" ,;:.-")

        if not cleaned:
            if has_strong:
                # тригер є, але без конкретики ("я тренувався") — попросимо уточнити
                return ("Logged intent noted, Sir, but which muscles? "
                        "Tell me e.g. 'chest and triceps'.")
            return None  # лише слабкий тригер без вправи → не наша команда

        # Якщо тригер був СЛАБКИЙ (add/plus) — лог робимо ТІЛЬКИ якщо текст
        # реально резолвиться в мʼязові групи (інакше це не про тренування,
        # напр. "add event", "add reminder" — хай іде на модель/інші тули).
        if not has_strong:
            try:
                from modules.workout_module import get_workout
                test_groups = get_workout().resolve_strict(cleaned)
            except Exception:
                test_groups = []
            if not test_groups:
                return None

        try:
            return str(self.tools_map["log_workout"].invoke({"exercise": cleaned}))
        except Exception as e:
            print(f"[WORKOUT] log error: {e}")
            return None

    def ask(self, user_input: str, lang: str = "en") -> str:
        base_prompt = ULTRON_PROMPT if self.active_mode == "ultron" else SYSTEM_PROMPT
        lang_instruction = (
            "Respond in Ukrainian language only. Address user as 'Сер'."
            if lang == "uk" and self.active_mode != "ultron"
            else "Respond in English language only. Address user as 'Victor'."
            if self.active_mode == "ultron"
            else "Respond in English language only. Address user as 'Sir'."
        )
        people_context = get_profiles_summary()
        memory_context = build_memory_context()

        # Інжектимо поточну дату/час — інакше LLM галюцинує дати з тренувального датасету
        now = datetime.now()
        date_context = (
            f"Current date and time: {now.strftime('%A, %d %B %Y, %H:%M')} "
            f"(today is {now.strftime('%Y-%m-%d')}, tomorrow is "
            f"{(now + timedelta(days=1)).strftime('%Y-%m-%d')}). "
            f"When scheduling events or reminders, calculate dates from this current date. "
            f"This date/time is for your internal reference only — do NOT mention or "
            f"announce the date or time in your reply unless the user explicitly asks for it."
        )

        system_with_lang = (
            base_prompt
            + f" {lang_instruction}"
            + f" {date_context}"
            + f" People you know: {people_context}."
            + (f" {memory_context}" if memory_context else "")
        )

        # ── Детермінований перехоплювач WORKOUT ──────────────────────────
        # llama-4-scout часто ігнорує log_workout і галюцинує "залоговано" текстом.
        # Тому workout-команди ловимо тут напряму й кличемо тул без участі моделі.
        # Те саме для armor build (галюцинувала 'done' без виклику тула).
        ar = self._maybe_armor(user_input)
        if ar is not None:
            self.chat_history.append(HumanMessage(content=user_input))
            self.chat_history.append(AIMessage(content=ar))
            save_history(self.chat_history)
            return ar

        wk = self._maybe_workout(user_input)
        if wk is not None:
            self.chat_history.append(HumanMessage(content=user_input))
            self.chat_history.append(AIMessage(content=wk))
            save_history(self.chat_history)
            return wk

        # ── MoE-роутер ───────────────────────────────────────────────────
        # Для ultron не маршрутизуємо (характер тримаємо на основній моделі).
        route = "tools" if self.active_mode == "ultron" else self._route_complexity(user_input)
        if route in ("small", "big"):
            light_model = ("llama-3.1-8b-instant" if route == "small"
                           else "llama-3.3-70b-versatile")
            print(f"[ROUTER] {route} → {light_model}")
            try:
                from modules.hud_module import update_hud
                update_hud("model", light_model.split("/")[-1])
            except Exception:
                pass
            try:
                # Окремий легкий виклик БЕЗ тулів, без мутації self.* —
                # rate-limit fallback на основній моделі лишається недоторканим.
                # 2-3 речення для голосу: і балачка, і reasoning короткі
                light_tokens = 160 if route == "small" else 150
                light_llm = self._create_llm(light_model, max_tokens=light_tokens)
                messages = (
                    [SystemMessage(content=system_with_lang)]
                    + self.chat_history
                    + [HumanMessage(content=user_input)]
                )
                resp = light_llm.invoke(messages)
                answer = resp.content.strip().replace("*", "").replace("#", "")
                answer = self._trim_sentences(answer, 3)

                self.chat_history.append(HumanMessage(content=user_input))
                self.chat_history.append(AIMessage(content=answer))
                save_history(self.chat_history)
                self.chat_history = compress_history_if_needed(self.chat_history, self.llm)
                if len(self.chat_history) > 20:
                    self.chat_history = self.chat_history[-20:]
                extract_and_save_people(user_input, answer, self.llm)

                # Повертаємо індикатор HUD на основну модель
                try:
                    from modules.hud_module import update_hud
                    update_hud("model", self.models[self.current_model_index].split("/")[-1])
                    from modules.people_module import get_all_profiles
                    update_hud("people", get_all_profiles())
                except Exception:
                    pass
                return answer
            except Exception as e:
                # Будь-яка проблема на легкій моделі — тихо падаємо назад на основну з тулами
                print(f"[ROUTER] Легка модель не впоралась ({e}), fallback на основну з тулами")

        for attempt in range(5):
            try:
                messages = (
                    [SystemMessage(content=system_with_lang)]
                    + self.chat_history
                    + [HumanMessage(content=user_input)]
                )

                response = self.llm_with_tools.invoke(messages)

                if response.tool_calls:
                    messages.append(response)
                    for tool_call in response.tool_calls:
                        tool_name = tool_call["name"].removeprefix("f.")
                        tool_args = tool_call["args"]
                        tool_id = tool_call["id"]
                        print(f"[AGENT] Викликає: {tool_name}({tool_args})")

                        if tool_name in self.tools_map:
                            tool_result = self.tools_map[tool_name].invoke(tool_args)
                        else:
                            tool_result = f"Tool {tool_name} not found."

                        # HUD оновлення після тулзи
                        try:
                            from modules.hud_module import update_hud
                            result_str = str(tool_result)
                            if tool_name == "fetch_weather":
                                update_hud("weather", result_str)
                            elif tool_name == "play_music":
                                if "PLAYING:" in result_str:
                                    track = result_str.replace("PLAYING:", "").strip()
                                    update_hud("current_song", track)
                                    try:
                                        devices = self.music_module.sp.devices()
                                        active = [d for d in devices.get("devices", []) if d["is_active"]]
                                        if active:
                                            update_hud("volume", active[0].get("volume_percent", 0))
                                    except Exception:
                                        pass
                            elif tool_name == "stop_music":
                                update_hud("current_song", "No music playing")
                                update_hud("volume", 0)
                            elif tool_name == "set_volume":
                                vol = tool_args.get("volume", tool_args.get("volume_percent", 0))
                                update_hud("volume", vol)
                        except Exception:
                            pass

                        messages.append(ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_id
                        ))

                    final = self.llm_with_tools.invoke(messages)
                    answer = final.content.strip()
                else:
                    answer = response.content.strip()

                import re
                # Фікс llama-4-scout: інколи модель ПИШЕ виклик тула текстом
                # (напр. search_my_history(query="...")) замість справжнього tool_call.
                # Ловимо такий рядок, реально викликаємо тул і переспитуємо модель.
                m = re.fullmatch(r'\s*(?:f\.)?(\w+)\((.*)\)\s*', answer, re.DOTALL)
                if m and m.group(1) in self.tools_map:
                    fake_name = m.group(1)
                    raw_args = m.group(2).strip()
                    print(f"[AGENT] Перехоплено текстовий виклик тула: {fake_name}({raw_args})")
                    parsed_args = {}
                    # розбираємо аргументи виду key="val", key='val', key=123
                    for am in re.finditer(r'(\w+)\s*=\s*("([^"]*)"|\'([^\']*)\'|[^,]+)', raw_args):
                        key = am.group(1)
                        val = am.group(3) if am.group(3) is not None else \
                              am.group(4) if am.group(4) is not None else am.group(2).strip()
                        parsed_args[key] = val
                    try:
                        tool_result = self.tools_map[fake_name].invoke(parsed_args)
                        messages.append(AIMessage(content=answer))
                        messages.append(HumanMessage(
                            content=f"Tool {fake_name} returned: {tool_result}\n"
                                    f"Now answer the user in one or two short sentences."
                        ))
                        retry = self.llm_with_tools.invoke(messages)
                        answer = retry.content.strip()
                    except Exception as _e:
                        print(f"[AGENT] Не вдалося виконати перехоплений тул: {_e}")

                if "<function=" in answer:
                    answer = answer.split("<function=")[0].strip()
                answer = re.sub(r"\(?\w+>\s*\)\s*\{[^}]*\}", "", answer).strip()
                answer = re.sub(r'\{["\w].*?\}$', "", answer, flags=re.DOTALL).strip()
                answer = answer.replace("*", "").replace("#", "")
                answer = self._trim_sentences(answer, 3)

                self.chat_history.append(HumanMessage(content=user_input))
                self.chat_history.append(AIMessage(content=answer))
                save_history(self.chat_history)

                # Стискаємо якщо history занадто довга
                self.chat_history = compress_history_if_needed(self.chat_history, self.llm)

                if len(self.chat_history) > 20:
                    self.chat_history = self.chat_history[-20:]

                # Авто-витяг фактів про людей у фоні
                extract_and_save_people(user_input, answer, self.llm)

                try:
                    from modules.hud_module import update_hud
                    from modules.people_module import get_all_profiles
                    update_hud("people", get_all_profiles())
                except Exception:
                    pass

                return answer

            except Exception as e:
                error_str = str(e)
                print(f"[AGENT] Спроба {attempt + 1}/5 невдала: {e}")

                # 413 / перевищення TPM (часто на малій 8b зі схемою тулів) —
                # перемикаємось далі, пропускаючи малу модель.
                if "413" in error_str or "request too large" in error_str.lower() \
                        or "tokens per minute" in error_str.lower():
                    if self._switch_to_next_model(skip_small=True):
                        continue
                    return "Сер, всі системи тимчасово недоступні." if lang == "uk" else "Sir, all AI systems are temporarily unavailable."

                if "rate_limit_exceeded" in error_str or "429" in error_str:
                    if self._switch_to_next_model(skip_small=True):
                        continue
                    return "Сер, всі системи тимчасово недоступні." if lang == "uk" else "Sir, all AI systems are temporarily unavailable."

                # Модель написала виклик тула як текст (Groq повертає це як 400).
                # Перемикаємось на іншу модель, пропускаючи малу.
                if "tool_use_failed" in error_str or "failed_generation" in error_str:
                    if self._switch_to_next_model(skip_small=True):
                        continue
                    return "Сер, не вдалось виконати дію." if lang == "uk" else "Sir, I couldn't complete that action."

                # Gemini заблокований / інша permission помилка — далі по ланцюгу
                if "PERMISSION_DENIED" in error_str or "API_KEY_SERVICE_BLOCKED" in error_str:
                    if self._switch_to_next_model(skip_small=True):
                        continue
                    return "Сер, виникла помилка." if lang == "uk" else "Sir, my reasoning systems encountered an error."

                if attempt >= 4:
                    return "Сер, виникла помилка." if lang == "uk" else "Sir, my reasoning systems encountered an error."
                time.sleep(1)

        # Гарантія: якщо цикл завершився без явного return (напр. останній
        # continue на tool_use_failed), НЕ повертаємо None — інакше впаде
        # processor.process на response.upper().
        return ("Сер, виникла помилка." if lang == "uk"
                else "Sir, my reasoning systems encountered an error.")

    def clear_history(self):
        from brain.memory_store import clear_history as delete_file
        self.chat_history = []
        delete_file()