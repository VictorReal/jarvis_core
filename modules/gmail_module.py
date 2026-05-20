"""
gmail_module.py — Gmail для JARVIS
Читає непрочитані листи, надсилає листи
"""

import base64
import logging
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth import get_credentials

logger = logging.getLogger(__name__)


class GmailModule:
    def __init__(self):
        creds = get_credentials()
        self._service = build("gmail", "v1", credentials=creds)

    # ------------------------------------------------------------------ #

    def get_unread(self, max_results: int = 5) -> list[dict]:
        """
        Повертає список непрочитаних листів.
        Кожен елемент: {from, subject, snippet, date}
        """
        try:
            result = self._service.users().messages().list(
                userId="me",
                labelIds=["UNREAD", "INBOX"],
                maxResults=max_results,
            ).execute()

            messages = result.get("messages", [])
            emails = []

            for msg in messages:
                detail = self._service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()

                headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
                emails.append({
                    "from":    headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "date":    headers.get("Date", ""),
                    "snippet": detail.get("snippet", ""),
                })

            return emails

        except Exception as e:
            logger.error(f"[GMAIL] get_unread error: {e}")
            return []

    def get_unread_summary(self, max_results: int = 5) -> str:
        """Повертає рядок для Джарвіса з переліком непрочитаних."""
        emails = self.get_unread(max_results)
        if not emails:
            return "No unread emails, Sir."

        lines = [f"You have {len(emails)} unread email(s), Sir:"]
        for i, e in enumerate(emails, 1):
            sender = e["from"].split("<")[0].strip().strip('"')
            lines.append(f"{i}. From {sender}: \"{e['subject']}\" — {e['snippet'][:80]}...")

        return " ".join(lines)

    def send_email(self, to: str, subject: str, body: str) -> str:
        """Надсилає лист. Повертає рядок-результат."""
        try:
            message = MIMEText(body)
            message["to"]      = to
            message["subject"] = subject

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            self._service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

            logger.info(f"[GMAIL] Надіслано до {to}: {subject}")
            return f"Email sent to {to}, Sir."

        except Exception as e:
            logger.error(f"[GMAIL] send_email error: {e}")
            return f"Sir, I couldn't send the email: {e}"

    def find_sender_email(self, name: str) -> str:
        """Шукає email відправника по імені в останніх листах."""
        try:
            result = self._service.users().messages().list(
                userId="me",
                maxResults=50,
                q=name,
            ).execute()

            for msg in result.get("messages", []):
                detail = self._service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From"],
                ).execute()
                headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
                from_field = headers.get("From", "")
                if name.lower() in from_field.lower():
                    # Витягуємо email з "Name <email>"
                    if "<" in from_field:
                        return from_field.split("<")[1].rstrip(">")
                    return from_field
        except Exception as e:
            logger.error(f"[GMAIL] find_sender error: {e}")
        return ""
