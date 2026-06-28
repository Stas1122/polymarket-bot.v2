import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def corrections_command(update: Update, context: ContextTypes.DEFAULT_TYPE, correction_monitor):
    from keyboards import main_keyboard
    from monitors.metar import CORRECTION_WATCH_STATIONS
    chat_id = str(update.effective_chat.id)

    if correction_monitor.is_subscribed(chat_id):
        correction_monitor.unsubscribe(chat_id)
        await update.message.reply_text(
            "🔕 *Виправлення — ВИМКНЕНО*\n\n"
            "Алерти про виправлення METAR не надходитимуть.\n\n"
            "Натисни ⚠️ Виправлення щоб увімкнути знову.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    else:
        correction_monitor.subscribe(chat_id)
        await update.message.reply_text(
            f"✅ *Виправлення — АКТИВНО*\n\n"
            f"Моніториться *{len(CORRECTION_WATCH_STATIONS)} станцій* по всьому світу.\n\n"
            "Як тільки METAR виправить температуру — прийде алерт ⚠️\n\n"
            "Натисни ⚠️ Виправлення ще раз щоб вимкнути.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )


async def peak_command(update: Update, context: ContextTypes.DEFAULT_TYPE, peak_monitor):
    from keyboards import main_keyboard
    chat_id = str(update.effective_chat.id)

    if peak_monitor.is_subscribed(chat_id):
        peak_monitor.unsubscribe(chat_id)
        await update.message.reply_text(
            "🔕 *Ранній пік — ВИМКНЕНО*\n\nАлерти про ранній пік температури не надходитимуть.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    else:
        peak_monitor.subscribe(chat_id)
        await update.message.reply_text(
            "✅ *Ранній пік — АКТИВНО*\n\n"
            "Алерт приходить за 3-4 години до опівночі місцевого часу\n"
            "якщо максимум температури очікується в перші 6 годин доби.\n\n"
            "Натисни 🌅 Ранній пік ще раз щоб вимкнути.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
