from telegram import ReplyKeyboardMarkup, KeyboardButton


def main_keyboard():
    keyboard = [
        [KeyboardButton("💼 Мій портфель"), KeyboardButton("👥 Трейдери")],
        [KeyboardButton("➕ Додати"), KeyboardButton("📋 Список")],
        [KeyboardButton("✈️ Станції"), KeyboardButton("⚠️ Виправлення")],
        [KeyboardButton("🌅 Ранній пік"), KeyboardButton("📈 Статус")],
        [KeyboardButton("❓ Допомога")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
