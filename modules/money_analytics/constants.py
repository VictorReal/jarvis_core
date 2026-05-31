"""
constants.py — конфіг для аналітики Money Manager.
"""

# Шлях за замовчуванням — куди класти експорти .xlsx
DEFAULT_EXPORT_DIR = "data/money_manager"

# Категорії-маркери (для аналізу "needs vs wants")
NEEDS_CATEGORIES = {
    "Groceries", "Health", "Phone", "Bills", "Transport", "Rent",
    "Utilities", "Communication", "Pharmacy",
}
WANTS_CATEGORIES = {
    "Cafe", "Alco", "Games", "Party", "Entertainment",
    "Shopping", "Gifts", "Restaurants",
}

# Колір категорій (HUD-friendly палітра)
CATEGORY_COLORS = [
    "#00d4ff",  # cyan
    "#ff9500",  # orange
    "#00ff88",  # green
    "#9b59b6",  # purple
    "#ff3b30",  # red
    "#3a6df0",  # blue
    "#ffcc00",  # yellow
    "#5ac8fa",  # light blue
    "#ff2d55",  # pink
    "#34c759",  # green2
    "#af52de",  # purple2
    "#ff6482",  # salmon
]
