from brain.memory import Memory
from brain.agent import JarvisAgent
from modules.music_module import MusicModule
from modules.navigation_module import NavigationModule
from modules.sensors_module import SensorsModule

class Brain:
    def __init__(self, reminder_module=None):
        self.memory = Memory()
        self.music_module = MusicModule()
        self.nav_module = NavigationModule()
        self.sensors = SensorsModule()

        # Gmail і Calendar — lazy init, тільки якщо credentials.json є
        import os
        if os.path.exists("credentials.json") or os.path.exists("token.json"):
            try:
                from modules.gmail_module import GmailModule
                from modules.calendar_module import CalendarModule
                self.gmail = GmailModule()
                self.calendar = CalendarModule()
                print("[BRAIN] Gmail + Calendar підключено")
            except Exception as e:
                print(f"[BRAIN] Google API недоступне: {e}")
                self.gmail = None
                self.calendar = None
        else:
            self.gmail = None
            self.calendar = None

        self.agent = JarvisAgent(
            music_module=self.music_module,
            nav_module=self.nav_module,
            sensors_module=self.sensors,
            reminder_module=reminder_module,
        )

        # MorningBriefing — ініціалізуємо тут, запускаємо з main після tts готовий
        self.morning_briefing = None  # буде присвоєно з main.py

    def process(self, command: str, lang: str = "en") -> str:
        command = command.lower().strip()

        stop_triggers = ["stop", "pause", "shut up", "silence", "halt",
                         "стоп", "пауза", "замовкни", "тихо"]
        if any(word in command for word in stop_triggers):
            self.music_module.stop()
            return "Як бажаєте, сер. [EXIT]" if lang == "uk" else "As you wish, Sir. [EXIT]"

        response = self.agent.ask(command, lang=lang)
        res_upper = response.upper()

        if any(w in res_upper for w in ["GOODBYE", "DISMISSED", "BYE", "БУВАЙТЕ", "ДО ПОБАЧЕННЯ"]):
            return f"{response} [EXIT]"

        music_hints = ["PLAYING:", "I'VE STARTED PLAYING", "NOW PLAYING", "I'M PLAYING", "ГРАЮ:"]
        if any(hint in res_upper for hint in music_hints):
            return f"{response} [PLAYING]"

        return response