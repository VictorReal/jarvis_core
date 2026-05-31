import asyncio
import os
import time
import threading
import logging
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes
)
from langdetect import detect, LangDetectException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))

class TelegramModule:
    """Телеграм інтерфейс для Джарвіса — текст і голос."""

    def __init__(self, jarvis_brain, voice_module, mode_callback=None):
        self.brain         = jarvis_brain
        self.voice_module  = voice_module
        self.mode_callback = mode_callback
        # Silent версія для Telegram — без голосу (async конфлікт)
        self._set_mode_silent = (lambda m: mode_callback(m, silent=True)) if mode_callback else None
        self.app          = Application.builder().token(TELEGRAM_TOKEN).build()

        # Реєструємо обробник текстових повідомлень
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        # Слухаємо повідомлення від самого бота з [WATCH]
        self.app.add_handler(
            MessageHandler(
                filters.TEXT & filters.Regex(r'^\[WATCH\]'),
                self.handle_watch_command
            )
        )
        # Inline-кнопки настрою (mood:score:N / mood:tag:NAME / mood:done / mood:skip)
        self.app.add_handler(CallbackQueryHandler(self.handle_mood_callback, pattern=r'^mood:'))
        # Проміжний стан поточної mood-сесії (між натисканнями кнопок)
        self._mood_session = {"score": None, "tags": [], "time_of_day": "adhoc"}
    def _is_authorized(self, user_id: int) -> bool:
        """Перевіряє чи це ти — щоб чужі не керували Джарвісом."""
        return user_id == TELEGRAM_USER_ID

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if not self._is_authorized(user_id):
            await update.message.reply_text("Access denied.")
            return

        user_text = update.message.text.strip()
        # Команда з годинника — обробляємо як свою
        if user_text.startswith("[WATCH]"):
            user_text = user_text.replace("[WATCH]", "").strip()
            print(f"[WATCH] Команда з годинника: {user_text}")
        # ← Тепер показуємо в терміналі і HUD
        print(f"[TELEGRAM] >>> YOU: {user_text}")
        try:
            from modules.hud_module import add_message
            add_message("user", f"[TG] {user_text}")
        except Exception:
            pass

        try:
            from langdetect import detect, LangDetectException
            detected = detect(user_text)
            lang = "uk" if detected == "uk" else "en"
        except Exception:
            lang = "en"

        print(f"[TELEGRAM] Мова: {lang.upper()}")

        import re
        lower = user_text.lower()

        # Перевірка зміни режиму — до відправки в brain
        if self._set_mode_silent:
            if any(p in lower for p in ["iron man mode", "switch to iron man", "activate iron man"]):
                self._set_mode_silent("iron man")
            elif any(p in lower for p in ["home mode", "switch to home"]):
                self._set_mode_silent("home")
            elif any(p in lower for p in ["ultron mode", "activate ultron", "switch to ultron", "режим альтрон"]):
                self._set_mode_silent("ultron")
            elif "switch" in lower:  # просто "switch" — toggle
                from modules.hud_module import hud_state
                current = hud_state.get("mode", "HOME").lower()
                self._set_mode_silent("iron man" if current == "home" else "home")

        # Скріншот HUD
        if any(p in lower for p in ["screenshot", "hud screenshot", "/hud", "покажи hud", "покажи хад"]):
            await self._send_hud_screenshot(update)
            return

        response = self.brain.process(user_text, lang=lang)


        clean = re.sub(r'\[.*?\]', '', response).replace("/", " ").strip()
        if not clean:
            clean = "As you wish, Sir." if lang == "en" else "Як бажаєте, сер."

        # Показуємо відповідь в терміналі і HUD
        print(f"[TELEGRAM] >>> JARVIS: {clean}")
        try:
            from modules.hud_module import add_message
            add_message("jarvis", f"[TG] {clean}")
        except Exception:
            pass

        await update.message.reply_text(clean)
        
        # Відправляємо відповідь на watch_relay для Watch
        try:
            import requests
            requests.post('http://localhost:5001/response', json={'text': clean}, timeout=1)
        except Exception:
            pass
        
        await self._send_voice(update, clean, lang)

    async def _send_voice(self, update: Update, text: str, lang: str):
        """Генерує MP3 і надсилає як голосове повідомлення."""
        import edge_tts
        from gtts import gTTS

        filename = f"tg_voice_{int(time.time() * 1000)}.mp3"

        try:
            if lang == "uk":
                # Українська через gTTS
                tts = gTTS(text=text, lang="uk", slow=False)
                tts.save(filename)
            else:
                # Англійська через Edge-TTS
                communicate = edge_tts.Communicate(text, "en-GB-RyanNeural")
                await communicate.save(filename)

            # Відправляємо файл як голосове
            with open(filename, "rb") as audio:
                await update.message.reply_voice(voice=audio)

        except Exception as e:
            logger.error(f"[TELEGRAM VOICE ERROR] {e}")
            await update.message.reply_text("(Voice generation failed)")

        finally:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass
    async def handle_watch_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обробляє команди з Galaxy Watch."""
        raw = update.message.text.strip()
        user_text = raw.replace("[WATCH]", "").strip()
        
        print(f"[WATCH] Команда з годинника: {user_text}")
        try:
            from modules.hud_module import add_message
            add_message("user", f"[⌚] {user_text}")
        except Exception:
            pass

        lang = "en"  # Watch завжди англійська
        response = self.brain.process(user_text, lang=lang)

        import re
        clean = re.sub(r'\[.*?\]', '', response).replace("/", " ").strip()
        if not clean:
            clean = "As you wish, Sir."

        print(f"[WATCH] Відповідь: {clean}")
        try:
            from modules.hud_module import add_message
            add_message("jarvis", f"[⌚] {clean}")
        except Exception:
            pass

        await update.message.reply_text(clean)
        
        # Відправляємо відповідь на watch_relay для Watch
        try:
            import requests
            requests.post('http://localhost:5001/response', json={'text': clean}, timeout=1)
        except Exception:
            pass
        
        await self._send_voice(update, clean, lang)
        
    # ── MOOD: inline-запит настрою ──────────────────────────────────
    def _mood_score_keyboard(self):
        """Клавіатура зі шкалою 1-10 (два ряди по 5)."""
        row1 = [InlineKeyboardButton(str(i), callback_data=f"mood:score:{i}") for i in range(1, 6)]
        row2 = [InlineKeyboardButton(str(i), callback_data=f"mood:score:{i}") for i in range(6, 11)]
        return InlineKeyboardMarkup([row1, row2])

    def _mood_tag_keyboard(self):
        """Клавіатура тегів + кнопки Done/Skip. Теги беремо з канонічного списку модуля."""
        try:
            from modules.mood_analytics.constants import MOOD_TAGS
            tags = MOOD_TAGS
        except Exception:
            tags = ["energetic", "tired", "anxious", "happy", "calm", "stressed"]
        selected = set(self._mood_session.get("tags", []))
        buttons, row = [], []
        for t in tags:
            label = ("✓ " if t in selected else "") + t
            row.append(InlineKeyboardButton(label, callback_data=f"mood:tag:{t}"))
            if len(row) == 3:
                buttons.append(row); row = []
        if row:
            buttons.append(row)
        buttons.append([
            InlineKeyboardButton("✅ Done", callback_data="mood:done"),
            InlineKeyboardButton("⏭ Skip tags", callback_data="mood:done"),
        ])
        return InlineKeyboardMarkup(buttons)

    def ask_mood(self, time_of_day: str = "adhoc"):
        """Надсилає запит настрою зі шкалою 1-10. Безпечно з будь-якого потоку."""
        if not TELEGRAM_USER_ID:
            return
        # Скидаємо сесію
        self._mood_session = {"score": None, "tags": [], "time_of_day": time_of_day}
        greeting = {
            "morning": "Good morning, Sir. How are you feeling? (1-10)",
            "evening": "Good evening, Sir. How was your day? Rate your mood (1-10)",
        }.get(time_of_day, "How are you feeling right now, Sir? (1-10)")

        async def _send():
            try:
                bot = Bot(token=TELEGRAM_TOKEN)
                await bot.send_message(
                    chat_id=TELEGRAM_USER_ID,
                    text=greeting,
                    reply_markup=self._mood_score_keyboard(),
                )
            except Exception as e:
                logger.error(f"[TELEGRAM] ask_mood error: {e}")

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send())
            loop.close()

        threading.Thread(target=_run, daemon=True).start()

    async def handle_mood_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обробляє натискання inline-кнопок настрою."""
        query = update.callback_query
        if not self._is_authorized(query.from_user.id):
            await query.answer("Access denied.")
            return
        await query.answer()
        data = query.data  # mood:score:N | mood:tag:NAME | mood:done

        parts = data.split(":")
        action = parts[1]

        if action == "score":
            self._mood_session["score"] = int(parts[2])
            print(f"[MOOD] Telegram score: {parts[2]}")
            # Переходимо до тегів
            await query.edit_message_text(
                text=f"Score {parts[2]}/10 noted, Sir. Any tags? (optional)",
                reply_markup=self._mood_tag_keyboard(),
            )

        elif action == "tag":
            tag = parts[2]
            tags = self._mood_session["tags"]
            if tag in tags:
                tags.remove(tag)
            else:
                tags.append(tag)
            # Перемальовуємо клавіатуру з оновленими галочками
            await query.edit_message_reply_markup(reply_markup=self._mood_tag_keyboard())

        elif action == "done":
            sess = self._mood_session
            if sess["score"] is None:
                await query.edit_message_text("Cancelled — no score selected, Sir.")
                return
            try:
                from modules.mood_analytics.jarvis_integration import log_mood_tool
                status = log_mood_tool(
                    score=sess["score"],
                    tags=";".join(sess["tags"]),
                    note="",
                    source="telegram",
                )
            except Exception as e:
                status = f"logged locally but analysis failed: {e}"
            tags_str = (", ".join(sess["tags"])) if sess["tags"] else "no tags"
            await query.edit_message_text(
                text=f"✓ Logged: {sess['score']}/10 ({tags_str}).\n{status}"
            )
            self._mood_session = {"score": None, "tags": [], "time_of_day": "adhoc"}

    def notify_owner(self, text: str):
        """
        Надсилає повідомлення власнику без очікування відповіді.
        Безпечно викликати з будь-якого потоку.
        """
        if not TELEGRAM_USER_ID:
            logger.warning("[TELEGRAM] TELEGRAM_USER_ID не задано — notify скасовано")
            return

        async def _send():
            try:
                bot = Bot(token=TELEGRAM_TOKEN)
                await bot.send_message(chat_id=TELEGRAM_USER_ID, text=text)
                logger.info(f"[TELEGRAM] Notify надіслано: {text[:60]}")
            except Exception as e:
                logger.error(f"[TELEGRAM] notify_owner error: {e}")

        # Запускаємо в окремому event loop щоб не конфліктувати з основним
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send())
            loop.close()

        threading.Thread(target=_run, daemon=True).start()

    def notify_photo(self, photo_path: str, caption: str = ""):
        """
        Надсилає фото (напр. mood/health/money дашборд) власнику.
        Безпечно з будь-якого потоку. caption обрізається до 1024 символів (ліміт Telegram).
        """
        if not TELEGRAM_USER_ID:
            logger.warning("[TELEGRAM] TELEGRAM_USER_ID не задано — notify_photo скасовано")
            return

        async def _send():
            try:
                bot = Bot(token=TELEGRAM_TOKEN)
                with open(photo_path, "rb") as img:
                    await bot.send_photo(
                        chat_id=TELEGRAM_USER_ID,
                        photo=img,
                        caption=(caption or "")[:1024],
                    )
                logger.info(f"[TELEGRAM] Photo надіслано: {photo_path}")
            except Exception as e:
                logger.error(f"[TELEGRAM] notify_photo error: {e}")

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send())
            loop.close()

        threading.Thread(target=_run, daemon=True).start()

    async def _send_hud_screenshot(self, update: Update):
        """Робить скріншот HUD (localhost:5000) і надсилає як фото."""
        import time
        filename = f"hud_{int(time.time() * 1000)}.png"
        try:
            # Використовуємо selenium або playwright якщо є, інакше pyautogui
            captured = False

            # Спроба 1: selenium (headless Chrome)
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                opts = Options()
                opts.add_argument("--headless")
                opts.add_argument("--window-size=1280,720")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-gpu")
                driver = webdriver.Chrome(options=opts)
                driver.get("http://localhost:5000")
                import asyncio as _asyncio
                await _asyncio.sleep(1.5)  # чекаємо рендер
                driver.save_screenshot(filename)
                driver.quit()
                captured = True
            except Exception:
                pass

            # Спроба 2: pyautogui (скріншот всього екрана — якщо HUD відкритий)
            if not captured:
                try:
                    import pyautogui
                    shot = pyautogui.screenshot()
                    shot.save(filename)
                    captured = True
                except Exception:
                    pass

            if captured and os.path.exists(filename):
                with open(filename, "rb") as img:
                    await update.message.reply_photo(photo=img, caption="HUD snapshot, Sir.")
            else:
                await update.message.reply_text("Sir, screenshot capture failed. Make sure HUD is running.")

        except Exception as e:
            logger.error(f"[TELEGRAM HUD SCREENSHOT] {e}")
            await update.message.reply_text(f"Screenshot error: {e}")
        finally:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass

    def run_in_thread(self):
        """Запускає Telegram бота в окремому потоці."""
        def _run():
            # Створюємо новий event loop для цього потоку
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            print("[TELEGRAM] Бот запущено. Очікую команди...")
            self.app.run_polling(allowed_updates=Update.ALL_TYPES)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread