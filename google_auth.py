"""
google_auth.py — OAuth2 авторизація для всіх Google API
Перший запуск: відкриває браузер → логін → зберігає token.json
Наступні запуски: використовує token.json автоматично
При invalid_grant (revoked/expired) — стирає token.json і запускає OAuth flow знов
"""

import os
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

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


def _notify_reauth(reason: str):
    """Шле в Telegram повідомлення про потрібну переавторизацію."""
    msg = f"⚠️ Google OAuth: {reason}\nЗапускаю OAuth flow — відкриється браузер."
    for path in ("modules.telegram_module", "telegram_module"):
        try:
            mod = __import__(path, fromlist=["send_message"])
            mod.send_message(msg)
            return
        except Exception:
            continue


def _run_oauth_flow() -> Credentials:
    """Запускає OAuth flow у браузері, повертає свіжі credentials."""
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            "credentials.json not found. "
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )
    print("[GOOGLE_AUTH] Відкриваю браузер для OAuth...")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    print("[GOOGLE_AUTH] ✓ Авторизація успішна")
    return creds


def _save_credentials(creds: Credentials):
    """Зберігає credentials у token.json."""
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def _delete_token(reason: str = ""):
    """Видаляє мертвий token.json."""
    if os.path.exists(TOKEN_FILE):
        try:
            os.remove(TOKEN_FILE)
            print(f"[GOOGLE_AUTH] Старий token.json видалено ({reason})")
        except Exception as e:
            logger.warning(f"[GOOGLE_AUTH] Не вдалось видалити токен: {e}")


def get_credentials(force_reauth: bool = False) -> Credentials:
    """
    Повертає валідні credentials.

    Логіка:
      1. Є валідний token.json → повертаємо
      2. Прострочений + є refresh_token → пробуємо оновити
      3. Refresh падає з invalid_grant → стираємо token, OAuth flow знов
      4. Нема token.json → перший запуск, OAuth flow

    Передай force_reauth=True щоб примусово переавторизуватись.
    """
    if force_reauth:
        _delete_token("force_reauth")

    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logger.warning(f"[GOOGLE_AUTH] Не вдалось прочитати {TOKEN_FILE}: {e}")
            _delete_token("corrupt token file")
            creds = None

    # 1. Валідний — повертаємо
    if creds and creds.valid:
        return creds

    # 2. Прострочений з refresh_token — пробуємо оновити
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
            logger.info("[GOOGLE_AUTH] Токен оновлено через refresh")
            return creds
        except RefreshError as e:
            error_str = str(e).lower()
            print(f"[GOOGLE_AUTH] ⚠️ Refresh провалився: {e}")
            if "invalid_grant" in error_str or "expired" in error_str or "revoked" in error_str:
                _notify_reauth("refresh token revoked/expired")
                _delete_token("invalid_grant")
            else:
                _notify_reauth(f"refresh error: {e}")
                _delete_token("refresh error")

    # 3/4. Повний OAuth flow
    creds = _run_oauth_flow()
    _save_credentials(creds)
    print("[GOOGLE_AUTH] ✓ Токен збережено в token.json")
    return creds