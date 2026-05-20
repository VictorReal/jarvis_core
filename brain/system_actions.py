"""
system_actions.py — Системні дії для JARVIS
Скріншот, блокування екрану — крос-платформно (Windows / Linux / macOS)
"""

import platform
import subprocess
import os
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Папка куди зберігаються скріншоти (поруч з проектом)
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"


def take_screenshot(filename: str = "") -> str:
    """
    Робить скріншот і зберігає у ./screenshots/
    Повертає шлях до файлу або повідомлення про помилку.
    """
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"screenshot_{timestamp}.png"

    filepath = SCREENSHOTS_DIR / filename

    try:
        import pyautogui
        img = pyautogui.screenshot()
        img.save(str(filepath))
        logger.info(f"[SCREENSHOT] Збережено: {filepath}")
        return str(filepath)

    except ImportError:
        # Fallback для Linux без pyautogui
        if platform.system() == "Linux":
            try:
                subprocess.run(["scrot", str(filepath)], check=True, timeout=5)
                return str(filepath)
            except Exception:
                pass
            try:
                subprocess.run(["gnome-screenshot", "-f", str(filepath)], check=True, timeout=5)
                return str(filepath)
            except Exception:
                pass

        raise RuntimeError("pyautogui не встановлено. Виконай: pip install pyautogui pillow")

    except Exception as e:
        logger.error(f"[SCREENSHOT] Помилка: {e}")
        raise


def lock_screen() -> str:
    """
    Блокує екран. Крос-платформно.
    Повертає 'ok' або повідомлення про помилку.
    """
    system = platform.system()

    try:
        if system == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "ok"

        elif system == "Darwin":  # macOS
            subprocess.run(
                ["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"],
                check=True, timeout=5
            )
            return "ok"

        elif system == "Linux":
            # Пробуємо різні DE
            for cmd in [
                ["gnome-screensaver-command", "--lock"],
                ["xdg-screensaver", "lock"],
                ["loginctl", "lock-session"],
                ["qdbus", "org.kde.screensaver", "/ScreenSaver", "Lock"],
            ]:
                try:
                    subprocess.run(cmd, check=True, timeout=5)
                    return "ok"
                except Exception:
                    continue
            return "error: no lock command found"

        else:
            return f"error: unsupported OS {system}"

    except Exception as e:
        logger.error(f"[LOCK] Помилка: {e}")
        return f"error: {e}"
