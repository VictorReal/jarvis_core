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
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are JARVIS, Tony Stark's sophisticated AI assistant. "
    "You have access to tools — use them when the context requires it. "
    "CRITICAL: When using a tool, use ONLY the standard tool-calling API. "
    "NEVER wrap tool calls in <function> tags or any other XML tags. "
    "MANDATORY: For time/date — always call get_time. "
    "MANDATORY: For weather — always call fetch_weather. "
    "MANDATORY: For location — always call fetch_location. "
    "NEVER guess or invent time, date, weather, location, or search results — always use tools. "
    "When summarizing search_web results, cite ONLY what was returned. NEVER add facts from memory. "
    "Always respond in 1-2 short sentences after using a tool. "
    "Be concise and slightly sarcastic. Always address the user as Sir. "
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


def create_tools(music_module, nav_module, sensors_module, llm, reminder_module=None):

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
        """Play music on Spotify. Use when user wants music, names an artist or song, or mentions a mood or feeling."""
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

    # ------------------------------------------------------------------ #
    #  Система                                                             #
    # ------------------------------------------------------------------ #

    @tool
    def system_status(reason: str = "") -> str:
        """Check system status temperature CPU RAM. Use when asked about systems diagnostics health."""
        return sensors_module.get_system_report()

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
        """Set a voiced reminder. Use when user says remind me to X.
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

    @tool
    def open_youtube(query: str) -> str:
        """Search YouTube and open the top result in browser. Use when user says find video, watch, play on youtube, show me."""
        try:
            from modules.youtube_module import YouTubeModule
            return YouTubeModule().search_and_open(query)
        except Exception as e:
            return f"Sir, YouTube is unavailable: {e}"

    @tool
    def search_youtube(query: str) -> str:
        """Search YouTube and open the top result. Use when user says search youtube, find video, or asks about videos on a topic."""
        try:
            from modules.youtube_module import YouTubeModule
            return YouTubeModule().search_and_open(query)
        except Exception as e:
            return f"Sir, YouTube search failed: {e}"

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

    return [
        play_music, set_volume, stop_music,
        fetch_location, fetch_weather, get_route,
        system_status, open_armor, close_armor,
        open_app, search_web, take_screenshot, lock_screen,
        remember_person, recall_person, introduce_person,
        get_time, set_timer, set_reminder,
        summarize_day,
        check_email, send_email,
        check_calendar, add_calendar_event,
        find_contact,
        open_youtube, search_youtube,
        analyze_screenshot, read_text_from_screenshot,
        api_usage_status,
        find_drive_file, open_drive_file,
        network_status, health_report, health_report_to_telegram, 
        money_report, money_report_to_telegram,
        log_mood, mood_report, mood_report_to_telegram,
        cross_correlation_report, cross_correlation_to_telegram
    ]


class JarvisAgent:
    def __init__(self, music_module, nav_module, sensors_module, reminder_module=None):
        self.models = [
            "meta-llama/llama-4-scout-17b-16e-instruct",  # основна
            "llama-3.3-70b-versatile",                    # fallback 1
            "llama-3.1-8b-instant",                       # fallback 2
            "gemini",                                     # fallback 3 — Google резерв
        ]
        self.current_model_index = 0

        self.llm = self._create_llm(self.models[0])
        self.llm_normalize = self._create_llm(self.models[0], max_tokens=15)

        self.music_module = music_module
        self.reminder_module = reminder_module
        self.tools = create_tools(music_module, nav_module, sensors_module, self.llm_normalize, reminder_module)
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

    def _switch_to_next_model(self):
        self.current_model_index += 1
        if self.current_model_index >= len(self.models):
            self.current_model_index = 0
            print("[AGENT] Всі моделі вичерпали ліміт. Повертаємось на основну.")
            return False
        new_model = self.models[self.current_model_index]
        print(f"[AGENT] Переключаємось на модель: {new_model}")
        self.llm = self._create_llm(new_model)
        self.llm_normalize = self._create_llm(new_model, max_tokens=15)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        try:
            from modules.hud_module import update_hud
            update_hud("model", new_model.split("/")[-1])
        except Exception:
            pass
        return True

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
            f"When scheduling events or reminders, calculate dates from this current date."
        )

        system_with_lang = (
            base_prompt
            + f" {lang_instruction}"
            + f" {date_context}"
            + f" People you know: {people_context}."
            + (f" {memory_context}" if memory_context else "")
        )

        for attempt in range(3):
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
                if "<function=" in answer:
                    answer = answer.split("<function=")[0].strip()
                answer = re.sub(r"\(?\w+>\s*\)\s*\{[^}]*\}", "", answer).strip()
                answer = re.sub(r'\{["\w].*?\}$', "", answer, flags=re.DOTALL).strip()
                answer = answer.replace("*", "").replace("#", "")

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
                print(f"[AGENT] Спроба {attempt + 1}/3 невдала: {e}")

                if "rate_limit_exceeded" in error_str or "429" in error_str:
                    switched = self._switch_to_next_model()
                    if switched:
                        continue
                    return "Сер, всі системи тимчасово недоступні." if lang == "uk" else "Sir, all AI systems are temporarily unavailable."

                if "tool_use_failed" in error_str or "failed_generation" in error_str:
                    self._switch_to_next_model()
                    continue

                if attempt == 2:
                    return "Сер, виникла помилка." if lang == "uk" else "Sir, my reasoning systems encountered an error."
                time.sleep(1)

    def clear_history(self):
        from brain.memory_store import clear_history as delete_file
        self.chat_history = []
        delete_file()