"""
gmail_notifier.py — фоновий агент Gmail для JARVIS.
Кожні 15 хв перевіряє ВАЖЛИВІ непрочитані листи (Gmail-категорія IMPORTANT)
і надсилає сповіщення в Telegram + Activity-стрічку HUD.
Голос НЕ використовується (лист не вважається терміновим).

Анти-спам: id вже оброблених листів зберігаються у файл,
тож після перезапуску JARVIS не сповіщає повторно про ті самі листи.

Стиль і архітектура — як у calendar_notifier.py (окремий клас + daemon-тред).
"""

import json
import threading
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SEC = 15 * 60          # перевіряємо кожні 15 хв
SEEN_FILE = Path("data/gmail_seen.json")  # персист оброблених id (проти спаму)
MAX_PER_CHECK = 5                     # не більше N сповіщень за одну перевірку
SEEN_LIMIT = 500                      # скільки id тримати у файлі


class GmailNotifier:
    def __init__(self, gmail_module, notify_callback, tts_callback=None):
        """
        gmail_module     — GmailModule (має ._service до Gmail API)
        notify_callback  — telegram.notify_owner(text)
        tts_callback     — safe_speak(text), опційно (не використовується для пошти)
        """
        self._gmail   = gmail_module
        self._notify  = notify_callback
        self._speak   = tts_callback          # навмисно не задіяний — пошта не термінова
        self._running = False
        self._thread  = None
        self._seen    = self._load_seen()     # set(message_id), переживає рестарт

    # ------------------------------------------------------------------ #
    #  Персист "бачених" id (анти-спам)
    # ------------------------------------------------------------------ #

    def _load_seen(self) -> set:
        try:
            if SEEN_FILE.exists():
                data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
                return set(data) if isinstance(data, list) else set()
        except Exception as e:
            logger.warning(f"[GMAIL NOTIFIER] Не вдалося прочитати {SEEN_FILE}: {e}")
        return set()

    def _save_seen(self):
        try:
            SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            # тримаємо лише останні SEEN_LIMIT id, щоб файл не ріс безкінечно
            ids = list(self._seen)[-SEEN_LIMIT:]
            SEEN_FILE.write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
            self._seen = set(ids)
        except Exception as e:
            logger.warning(f"[GMAIL NOTIFIER] Не вдалося зберегти {SEEN_FILE}: {e}")

    # ------------------------------------------------------------------ #
    #  Запуск / зупинка
    # ------------------------------------------------------------------ #

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="GmailNotifier"
        )
        self._thread.start()
        logger.info("[GMAIL NOTIFIER] Запущено")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #
    #  Основний цикл
    # ------------------------------------------------------------------ #

    def _loop(self):
        # Перший прохід робимо одразу — але БЕЗ сповіщень: лише позначаємо
        # наявні важливі листи як "бачені", щоб не засипати юзера старою поштою.
        try:
            self._prime_seen()
        except Exception as e:
            logger.warning(f"[GMAIL NOTIFIER] prime error: {e}")

        while self._running:
            time.sleep(CHECK_INTERVAL_SEC)
            if not self._running:
                break
            try:
                self._check()
            except Exception as e:
                logger.warning(f"[GMAIL NOTIFIER] Помилка: {e}")

    def _fetch_important_unread(self, max_results: int = 10) -> list[dict]:
        """Тягне ВАЖЛИВІ непрочитані листи напряму через Gmail API.
        Не чіпає gmail_module.get_unread (там нема фільтра IMPORTANT)."""
        service = self._gmail._service
        result = service.users().messages().list(
            userId="me",
            labelIds=["IMPORTANT", "UNREAD", "INBOX"],
            maxResults=max_results,
        ).execute()

        out = []
        for msg in result.get("messages", []):
            mid = msg["id"]
            detail = service.users().messages().get(
                userId="me",
                id=mid,
                format="metadata",
                metadataHeaders=["From", "Subject"],
            ).execute()
            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            out.append({
                "id":      mid,
                "from":    headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": detail.get("snippet", ""),
            })
        return out

    def _prime_seen(self):
        """Перший прохід: позначаємо вже наявні важливі листи як бачені,
        НЕ надсилаючи сповіщень (інакше при кожному старті прилетить уся пошта)."""
        emails = self._fetch_important_unread()
        new_ids = [e["id"] for e in emails if e["id"] not in self._seen]
        if new_ids:
            self._seen.update(new_ids)
            self._save_seen()
            logger.info(f"[GMAIL NOTIFIER] Стартова синхронізація: "
                        f"{len(new_ids)} важливих листів позначено (без сповіщень)")

    def _check(self):
        emails = self._fetch_important_unread()
        fresh = [e for e in emails if e["id"] not in self._seen]
        if not fresh:
            return

        # Позначаємо одразу всі як бачені (щоб наступна перевірка не повторила),
        # але сповіщення шлемо не більше MAX_PER_CHECK за раз.
        for e in fresh:
            self._seen.add(e["id"])
        self._save_seen()

        to_notify = fresh[:MAX_PER_CHECK]
        extra = len(fresh) - len(to_notify)

        for e in to_notify:
            sender  = e["from"].split("<")[0].strip().strip('"') or e["from"]
            subject = e["subject"]
            snippet = (e["snippet"] or "")[:80]

            msg = f"Sir, important email from {sender}: \"{subject}\""
            if snippet:
                msg += f" — {snippet}..."

            logger.info(f"[GMAIL NOTIFIER] {msg}")

            # Telegram
            try:
                self._notify("[JARVIS] " + msg)
            except Exception as ex:
                logger.warning(f"[GMAIL NOTIFIER] Telegram error: {ex}")

            # HUD Activity-стрічка
            try:
                from modules.hud_module import log_activity
                log_activity(f"Important email from {sender}: {subject}", kind="info")
            except Exception as ex:
                logger.warning(f"[GMAIL NOTIFIER] HUD error: {ex}")

        if extra > 0:
            tail = f"Sir, plus {extra} more important email(s) waiting."
            try:
                self._notify("[JARVIS] " + tail)
            except Exception:
                pass
            try:
                from modules.hud_module import log_activity
                log_activity(f"+{extra} more important emails", kind="info")
            except Exception:
                pass
