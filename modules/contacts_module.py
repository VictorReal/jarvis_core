"""
contacts_module.py — Google People/Contacts API для JARVIS
Шукає контакти по імені, повертає телефон і email
"""

import logging
from googleapiclient.discovery import build
from google_auth import get_credentials

logger = logging.getLogger(__name__)


class ContactsModule:
    def __init__(self):
        creds = get_credentials()
        self._service = build("people", "v1", credentials=creds)

    def find(self, name: str) -> list[dict]:
        """
        Шукає контакти по імені.
        Повертає список {name, phones, emails}
        """
        try:
            results = self._service.people().searchContacts(
                query=name,
                readMask="names,phoneNumbers,emailAddresses",
                pageSize=5,
            ).execute()

            contacts = []
            for r in results.get("results", []):
                person = r.get("person", {})
                display = (person.get("names") or [{}])[0].get("displayName", "Unknown")
                phones  = [p["value"] for p in person.get("phoneNumbers", [])]
                emails  = [e["value"] for e in person.get("emailAddresses", [])]
                contacts.append({"name": display, "phones": phones, "emails": emails})

            return contacts

        except Exception as e:
            logger.error(f"[CONTACTS] find error: {e}")
            return []

    def find_summary(self, name: str) -> str:
        """Повертає рядок для Джарвіса."""
        contacts = self.find(name)
        if not contacts:
            return f"Sir, I couldn't find anyone named '{name}' in your contacts."

        lines = []
        for c in contacts:
            parts = [c["name"]]
            if c["phones"]:
                parts.append("phone: " + ", ".join(c["phones"]))
            if c["emails"]:
                parts.append("email: " + ", ".join(c["emails"]))
            lines.append(" — ".join(parts))

        return "Found: " + "; ".join(lines) + "."
