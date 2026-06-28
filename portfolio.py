import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def register(app, monitor, notifications):
    from telegram.ext import CommandHandler, CallbackQueryHandler
    app.add_handler(CommandHandler("list", lambda u, c: list_command(u, c, monitor)))
    app.add_handler(CommandHandler("remove", lambda u, c: remove_command(u, c, monitor)))
    app.add_handler(CommandHandler("status", lambda u, c: status_command(u, c, monitor)))


async def my_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE, monitor, peak_monitor=None):
    from keyboards import main_keyboard
    chat_id = str(update.effective_chat.id)
    own = monitor.get_own_accounts(chat_id)

    if not own:
        await update.message.reply_text(
            "💼 Свого акаунту ще немає.\n\nДодай через ➕ Додати → 💼 Мій акаунт",
            reply_markup=main_keyboard()
        )
        return

    msg = await update.message.reply_text("⏳ Завантажую портфель...")
    bot = update.get_bot()

    for trader in own:
        address = trader["address"]
        positions, pnl_stats = await asyncio.gather(
            monitor.get_positions_report(address),
            monitor.get_pnl_stats(address)
        )
        from notifications import send_positions_report
        await send_positions_report(bot, chat_id, address, positions,
                                     context=context, pnl_stats=pnl_stats, monitor=monitor)
    try:
        await msg.delete()
    except Exception:
        pass


async def watched_traders(update: Update, context: ContextTypes.DEFAULT_TYPE, monitor):
    from keyboards import main_keyboard
    chat_id = str(update.effective_chat.id)
    watched = monitor.get_watched_traders(chat_id)

    if not watched:
        await update.message.reply_text(
            "👥 Ще нікого не відстежуєш.\n\nДодай через ➕ Додати → 👁 Відстежувати трейдера",
            reply_markup=main_keyboard()
        )
        return

    keyboard = []
    for t in watched:
        nick = t.get("nickname") or f"{t['address'][:10]}...{t['address'][-6:]}"
        keyboard.append([InlineKeyboardButton(
            f"📊 {nick}", callback_data=f"viewpos:{t['address']}"
        )])

    await update.message.reply_text(
        "👥 *Відстежувані трейдери*\n\nОбери чиї позиції показати:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE, monitor):
    from keyboards import main_keyboard
    chat_id = str(update.effective_chat.id)
    own = monitor.get_own_accounts(chat_id)
    watched = monitor.get_watched_traders(chat_id)

    if not own and not watched:
        await update.message.reply_text("📋 Список порожній. Додай через ➕", reply_markup=main_keyboard())
        return

    lines = ["📋 *Всі акаунти:*\n"]
    if own:
        lines.append("💼 *Мої акаунти:*")
        for t in own:
            nick = t.get("nickname", "")
            addr = f"`{t['address'][:10]}...{t['address'][-6:]}`"
            lines.append(f"  • {addr}" + (f" — *{nick}*" if nick else ""))
    if watched:
        lines.append("\n👥 *Відстежувані:*")
        for t in watched:
            nick = t.get("nickname", "")
            addr = f"`{t['address'][:10]}...{t['address'][-6:]}`"
            lines.append(f"  • {addr}" + (f" — *{nick}*" if nick else ""))

    keyboard = []
    for t in own + watched:
        nick = t.get("nickname") or f"{t['address'][:10]}...{t['address'][-6:]}"
        icon = "💼" if t.get("is_own") else "👁"
        keyboard.append([InlineKeyboardButton(f"🗑 {icon} {nick}", callback_data=f"remove:{t['address']}")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE, monitor):
    from keyboards import main_keyboard
    chat_id = str(update.effective_chat.id)
    traders = monitor.get_traders(chat_id)
    if not traders:
        await update.message.reply_text("📋 Список порожній.", reply_markup=main_keyboard())
        return

    keyboard = []
    for t in traders:
        nick = t.get("nickname") or f"{t['address'][:10]}...{t['address'][-6:]}"
        icon = "💼" if t.get("is_own") else "👁"
        keyboard.append([InlineKeyboardButton(f"🗑 {icon} {nick}", callback_data=f"remove:{t['address']}")])

    await update.message.reply_text("Оберіть для видалення:", reply_markup=InlineKeyboardMarkup(keyboard))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          monitor, metar_monitor, correction_monitor, peak_monitor):
    from keyboards import main_keyboard
    chat_id = str(update.effective_chat.id)
    own = monitor.get_own_accounts(chat_id)
    watched = monitor.get_watched_traders(chat_id)
    metar_stations = metar_monitor.get_stations(chat_id)
    is_corrections = correction_monitor.is_subscribed(chat_id)
    is_peak = peak_monitor.is_subscribed(chat_id)
    stats = correction_monitor.get_stats()

    corrections_status = "🟢 Активно" if is_corrections else "🔴 Вимкнено"
    peak_status = "🟢 Активно" if is_peak else "🔴 Вимкнено"
    last_check = stats.get("last_check") or "ще не перевірялось"
    checked = stats.get("checked_stations", 0)
    total = stats.get("total_stations", 0)
    total_corr = stats.get("total_corrections", 0)

    await update.message.reply_text(
        f"📈 *Статус бота*\n\n"
        f"🟢 Бот активний\n\n"
        f"*Polymarket:*\n"
        f"💼 Моїх акаунтів: *{len(own)}*\n"
        f"👥 Відстежуваних: *{len(watched)}*\n"
        f"⏱ Перевірка угод: кожні 30 сек\n\n"
        f"*METAR станції:*\n"
        f"✈️ Твоїх станцій: *{len(metar_stations)}*\n"
        f"⏱ Перевірка: кожну хвилину\n\n"
        f"*Виправлення METAR:*\n"
        f"⚠️ Статус: {corrections_status}\n"
        f"🌐 Перевірено: *{checked}/{total}*\n"
        f"🕐 Остання перевірка: {last_check}\n"
        f"📊 Виправлень знайдено: *{total_corr}*\n\n"
        f"*Ранній пік:*\n"
        f"🌅 Статус: {peak_status}",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
