"""
calendar_module.py — Google Calendar для JARVIS
Читає найближчі події, створює нові
"""

import logging
from datetime import datetime, timedelta, timezone
from googleapiclient.discovery import build
from google_auth import get_credentials

logger = logging.getLogger(__name__)


class CalendarModule:
    def __init__(self):
        creds = get_credentials()
        self._service = build("calendar", "v3", credentials=creds)

    # ------------------------------------------------------------------ #

    def get_upcoming(self, hours: int = 24, max_results: int = 5) -> list[dict]:
        """
        Повертає найближчі події в межах `hours` годин.
        Кожен елемент: {title, start, end, location, description}
        """
        try:
            now = datetime.now(timezone.utc)
            until = now + timedelta(hours=hours)

            result = self._service.events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=until.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()

            events = []
            for e in result.get("items", []):
                start_raw = e["start"].get("dateTime") or e["start"].get("date")
                end_raw   = e["end"].get("dateTime")   or e["end"].get("date")

                # Парсимо час
                try:
                    start_dt = datetime.fromisoformat(start_raw)
                    start_str = start_dt.strftime("%H:%M")
                except Exception:
                    start_str = start_raw

                events.append({
                    "title":       e.get("summary", "(no title)"),
                    "start":       start_str,
                    "start_raw":   start_raw,
                    "location":    e.get("location", ""),
                    "description": e.get("description", ""),
                })
            return events

        except Exception as e:
            logger.error(f"[CALENDAR] get_upcoming error: {e}")
            return []

    def get_upcoming_summary(self, hours: int = 24) -> str:
        """Повертає рядок для Джарвіса з найближчими подіями."""
        events = self.get_upcoming(hours)
        if not events:
            return f"No events in the next {hours} hours, Sir."

        lines = [f"Upcoming events in the next {hours} hours, Sir:"]
        for e in events:
            loc = f" at {e['location']}" if e["location"] else ""
            lines.append(f"{e['start']} — {e['title']}{loc}.")

        return " ".join(lines)

    def create_event(self, title: str, start_iso: str, end_iso: str,
                     location: str = "", description: str = "") -> str:
        """
        Створює подію в Google Calendar.
        start_iso / end_iso — рядок ISO 8601, наприклад '2025-05-20T15:00:00+03:00'
        """
        try:
            body = {
                "summary":  title,
                "location": location,
                "description": description,
                "start": {"dateTime": start_iso, "timeZone": "Europe/Kyiv"},
                "end":   {"dateTime": end_iso,   "timeZone": "Europe/Kyiv"},
            }
            event = self._service.events().insert(
                calendarId="primary",
                body=body,
            ).execute()

            link = event.get("htmlLink", "")
            logger.info(f"[CALENDAR] Створено: {title} о {start_iso}")
            return f"Event '{title}' created for {start_iso[:16].replace('T', ' ')}, Sir."

        except Exception as e:
            logger.error(f"[CALENDAR] create_event error: {e}")
            return f"Sir, I couldn't create the event: {e}"

    def get_today_summary(self) -> str:
        """Короткий підсумок на сьогодні — для ранкового брифінгу."""
        return self.get_upcoming_summary(hours=24)
