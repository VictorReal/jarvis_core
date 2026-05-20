"""
app_launcher.py — Запуск застосунків для JARVIS
Fuzzy match назви → команда. Крос-платформно (Windows / Linux / macOS).
"""

import subprocess
import platform
import logging
from difflib import get_close_matches

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  База застосунків: alias → (windows_cmd, linux_cmd, mac_cmd)
#  None = не підтримується на цій ОС
# --------------------------------------------------------------------------- #
APP_MAP = {
    # Браузери
    "chrome":       ("chrome",              "google-chrome",        "open -a 'Google Chrome'"),
    "google chrome":("chrome",              "google-chrome",        "open -a 'Google Chrome'"),
    "firefox":      ("firefox",             "firefox",              "open -a Firefox"),
    "edge":         ("msedge",              "microsoft-edge",       "open -a 'Microsoft Edge'"),
    "browser":      ("chrome",              "google-chrome",        "open -a 'Google Chrome'"),

    # Редактори / IDE
    "notepad":      ("notepad",             "gedit",                "open -a TextEdit"),
    "vscode":       ("code",                "code",                 "open -a 'Visual Studio Code'"),
    "vs code":      ("code",                "code",                 "open -a 'Visual Studio Code'"),
    "visual studio":("devenv",              None,                   None),
    "sublime":      ("subl",                "subl",                 "open -a 'Sublime Text'"),
    "pycharm":      ("pycharm",             "pycharm",              "open -a PyCharm"),

    # Термінал
    "terminal":     ("cmd",                 "x-terminal-emulator",  "open -a Terminal"),
    "cmd":          ("cmd",                 "bash",                 "open -a Terminal"),
    "powershell":   ("powershell",          "bash",                 "open -a Terminal"),

    # Музика / медіа
    "spotify":      ("spotify",             "spotify",              "open -a Spotify"),
    "vlc":          ("vlc",                 "vlc",                  "open -a VLC"),

    # Офіс
    "word":         ("winword",             "libreoffice --writer", "open -a 'Microsoft Word'"),
    "excel":        ("excel",               "libreoffice --calc",   "open -a 'Microsoft Excel'"),
    "powerpoint":   ("powerpnt",            "libreoffice --impress","open -a 'Microsoft PowerPoint'"),
    "libreoffice":  ("soffice",             "libreoffice",          "open -a LibreOffice"),

    # Месенджери
    "telegram":     ("telegram",            "telegram-desktop",     "open -a Telegram"),
    "discord":      ("discord",             "discord",              "open -a Discord"),
    "slack":        ("slack",               "slack",                "open -a Slack"),
    "teams":        ("teams",               None,                   "open -a 'Microsoft Teams'"),
    "whatsapp":     ("whatsapp",            None,                   "open -a WhatsApp"),

    # Система
    "calculator":   ("calc",                "gnome-calculator",     "open -a Calculator"),
    "explorer":     ("explorer",            "nautilus",             "open -a Finder"),
    "finder":       ("explorer",            "nautilus",             "open -a Finder"),
    "task manager": ("taskmgr",             "gnome-system-monitor", "open -a 'Activity Monitor'"),
    "settings":     ("ms-settings:",        "gnome-control-center", "open -a 'System Preferences'"),
    "paint":        ("mspaint",             "gimp",                 "open -a Preview"),
    "gimp":         ("gimp",                "gimp",                 "open -a GIMP"),
    "obs":          ("obs64",               "obs",                  "open -a OBS"),
    "steam":        ("steam",               "steam",                "open -a Steam"),
    "postman":      ("postman",             "postman",              "open -a Postman"),
    "figma":        ("figma",               None,                   "open -a Figma"),
}

OS_INDEX = {"Windows": 0, "Linux": 1, "Darwin": 2}


def launch(app_name: str) -> str:
    """
    Запускає застосунок за назвою.
    Повертає рядок-результат для Джарвіса.
    """
    key = app_name.lower().strip()
    system = platform.system()
    os_idx = OS_INDEX.get(system, 1)

    # 1. Точний збіг
    entry = APP_MAP.get(key)

    # 2. Fuzzy match якщо точного нема
    if not entry:
        matches = get_close_matches(key, APP_MAP.keys(), n=1, cutoff=0.6)
        if matches:
            entry = APP_MAP[matches[0]]
            logger.info(f"[LAUNCHER] Fuzzy: '{key}' → '{matches[0]}'")

    # 3. Якщо взагалі нічого — пробуємо запустити як є
    cmd = entry[os_idx] if entry else None

    if cmd is None:
        return f"Sir, I don't have '{app_name}' mapped for {system}."

    try:
        if system == "Windows":
            subprocess.Popen(cmd, shell=True)
        elif system == "Darwin":
            subprocess.Popen(cmd, shell=True)
        else:
            # Linux — пробуємо як список, fallback на shell
            try:
                subprocess.Popen(cmd.split())
            except FileNotFoundError:
                subprocess.Popen(cmd, shell=True)

        display = app_name.title()
        logger.info(f"[LAUNCHER] Запущено: {cmd}")
        return f"Opening {display}, Sir."

    except Exception as e:
        logger.error(f"[LAUNCHER] Помилка: {e}")
        return f"Sir, I couldn't launch {app_name}: {e}"
