"""
app_launcher.py — Запуск застосунків для JARVIS
Fuzzy match назви → команда. Крос-платформно (Windows / Linux / macOS).
Перевіряє доступність до запуску, повертає чесний результат.
"""

import subprocess
import platform
import logging
import shutil
import os
from difflib import get_close_matches

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  URI-схеми для UWP/Store-додатків на Windows
#  Працюють, якщо застосунок встановлений і зареєстрував свій handler
# --------------------------------------------------------------------------- #
WINDOWS_URI = {
    "whatsapp":     "whatsapp://",
    "telegram":     "tg://",
    "spotify":      "spotify:",
    "discord":      "discord://",
    "settings":     "ms-settings:",
    "store":        "ms-windows-store:",
    "ms store":     "ms-windows-store:",
    "skype":        "skype:",
    "zoom":         "zoommtg://",
    "outlook":      "outlook:",
}

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
    "outlook":      ("outlook",             None,                   "open -a 'Microsoft Outlook'"),

    # Месенджери
    "telegram":     ("telegram",            "telegram-desktop",     "open -a Telegram"),
    "discord":      ("discord",             "discord",              "open -a Discord"),
    "slack":        ("slack",               "slack",                "open -a Slack"),
    "teams":        ("teams",               None,                   "open -a 'Microsoft Teams'"),
    "whatsapp":     ("whatsapp",            None,                   "open -a WhatsApp"),
    "skype":        ("skype",               "skype",                "open -a Skype"),
    "zoom":         ("zoom",                "zoom",                 "open -a zoom.us"),

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


def _launch_windows(key: str, display: str, cmd: str | None) -> tuple[bool, str]:
    """
    Стратегії запуску на Windows у такому порядку:
      1. URI-схема (для UWP/Store: WhatsApp, Telegram, Spotify, тощо)
      2. shutil.which + Popen (звичайні exe у PATH)
      3. os.startfile (для зареєстрованих хендлерів типу ms-settings:)
    """
    # 1. URI-схема
    uri = WINDOWS_URI.get(key)
    if uri:
        try:
            os.startfile(uri)
            logger.info(f"[LAUNCHER] URI '{uri}' для {display}")
            return True, f"Opening {display}, Sir."
        except OSError as e:
            logger.info(f"[LAUNCHER] URI '{uri}' не зареєстровано: {e}")
            # йдемо далі — може це звичайний exe

    if not cmd:
        return False, f"Sir, {display} is not installed or not registered on this system."

    # 2. Перевірка через PATH
    first_word = cmd.split()[0]
    exe = shutil.which(first_word)
    if exe:
        try:
            if ' ' in cmd:
                subprocess.Popen(cmd, shell=True)
            else:
                subprocess.Popen([exe], shell=False)
            logger.info(f"[LAUNCHER] Запущено exe: {exe}")
            return True, f"Opening {display}, Sir."
        except Exception as e:
            logger.warning(f"[LAUNCHER] Popen помилка: {e}")

    # 3. os.startfile (для ms-settings: і подібних URI у APP_MAP)
    try:
        os.startfile(cmd)
        logger.info(f"[LAUNCHER] startfile: {cmd}")
        return True, f"Opening {display}, Sir."
    except OSError as e:
        logger.warning(f"[LAUNCHER] startfile fail: {e}")

    return False, f"Sir, I couldn't find {display} — not installed or not in PATH."


def _launch_unix(system: str, display: str, cmd: str | None) -> tuple[bool, str]:
    """Лінукс/мак: перевірка PATH + Popen."""
    if not cmd:
        return False, f"Sir, I don't have '{display}' mapped for {system}."

    # macOS використовує 'open -a "App"' — exec існує (open), тому перевірка пропускається
    if system != "Darwin":
        first_word = cmd.split()[0]
        if not shutil.which(first_word):
            return False, f"Sir, {first_word} doesn't seem to be installed."

    try:
        if system == "Darwin":
            subprocess.Popen(cmd, shell=True)
        else:
            try:
                subprocess.Popen(cmd.split())
            except FileNotFoundError:
                subprocess.Popen(cmd, shell=True)
        return True, f"Opening {display}, Sir."
    except Exception as e:
        logger.error(f"[LAUNCHER] Помилка: {e}")
        return False, f"Sir, I couldn't launch {display}: {e}"


def launch(app_name: str) -> str:
    """
    Запускає застосунок за назвою. Повертає рядок-результат для Джарвіса.
    На успіх: 'Opening X, Sir.'  На невдачу: чесне 'Sir, I couldn't...'.
    """
    key = app_name.lower().strip()
    system = platform.system()
    display = app_name.title()

    # Точний збіг
    entry = APP_MAP.get(key)
    matched_key = key

    # Fuzzy match якщо точного нема
    if not entry:
        matches = get_close_matches(key, APP_MAP.keys(), n=1, cutoff=0.6)
        if matches:
            matched_key = matches[0]
            entry = APP_MAP[matched_key]
            logger.info(f"[LAUNCHER] Fuzzy: '{key}' → '{matched_key}'")

    os_idx = OS_INDEX.get(system, 1)
    cmd = entry[os_idx] if entry else None

    if system == "Windows":
        success, msg = _launch_windows(matched_key, display, cmd)
    else:
        success, msg = _launch_unix(system, display, cmd)

    (logger.info if success else logger.warning)(f"[LAUNCHER] {msg}")
    return msg