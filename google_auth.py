"""
google_auth.py — OAuth2 авторизація для всіх Google API
Перший запуск: відкриває браузер → логін → зберігає token.json
Наступні запуски: використовує token.json автоматично
"""

import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/contacts.other.readonly",
    "https://www.googleapis.com/auth/user.phonenumbers.read",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE       = "token.json"


def get_credentials() -> Credentials:
    """
    Повертає валідні credentials.
    Якщо token.json є і не протух — повертає одразу.
    Якщо протух — оновлює через refresh.
    Якщо нема — запускає OAuth flow в браузері.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "credentials.json not found. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds
