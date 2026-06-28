import asyncio
import logging
import os
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)

from config import (
    TELEGRAM_BOT_TOKEN, WAITING_ADDRESS, WAITING_NICKNAME,
    WAITING_TYPE, WAITING_METAR, POLYMARKET_CHECK_INTERVAL,
    METAR_CHECK_INTERVAL, HOURLY_INTERVAL, DAILY_INTERVAL
)
from keyboards import main_keyboard
from monitors import PolymarketMonitor, MetarMonitor, CorrectionMonitor, PeakForecastMonitor
from notifications import (
    send_trade_notification, send_positions_report,
    send_metar_notification, send_correction_alert, send_peak_alert
)
from handlers.portfolio import (
    my_portfolio, watched_traders, list_command,
    remove_command, status_command
)
from handlers.alerts import corrections_command, peak_command

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ініціалізація моніторів
monitor = PolymarketMonitor()
metar_monitor = MetarMonitor()
correction_monitor = CorrectionMonitor()
peak_monitor = PeakForecastMonitor()

pinned_messages = {}


# ============ КОМАНДИ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Polymarket Trade Monitor*\n\n"
        "Відстежую угоди та позиції на Polymarket + температуру аеропортів.\n\n"
        "💼 *Мій портфель* — твої особисті позиції з PnL\n"
        "👥 *Трейдери* — позиції тих за ким стежиш\n"
        "✈️ *Станції* — METAR моніторинг температури\n"
        "⚠️ *Виправлення* — алерт при виправленні METAR\n"
        "🌅 *Ранній пік* — алерт якщо пік температури вранці\n\n"
        "Починай з ➕ Додати"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Довідка*\n\n"
        "💼 *Мій портфель* — щогодинний звіт по своїх позиціях\n"
        "👥 *Трейдери* — позиції відстежуваних по запиту\n"
        "➕ *Додати* — додати свій або чужий акаунт\n"
        "📋 *Список* — всі акаунти\n"
        "✈️ *Станції* — додати METAR станцію\n"
        "⚠️ *Виправлення* — підписка на алерти виправлень METAR\n"
        "🌅 *Ранній пік* — підписка на алерти раннього піку\n\n"
        "🔔 *Сповіщення:*\n"
        "▸ Нова угода — одразу\n"
        "▸ Мій портфель — щогодини\n"
        "▸ Трейдери — раз на добу або по запиту\n"
        "▸ METAR — при кожному оновленні\n"
        "▸ Виправлення — при зміні даних заднім числом\n"
        "▸ Ранній пік — за 3-4 год до опівночі"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())


# ============ ДОДАВАННЯ ТРЕЙДЕРІВ ============

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [__import__('telegram').KeyboardButton("💼 Мій акаунт"),
         __import__('telegram').KeyboardButton("👁 Відстежувати трейдера")],
        [__import__('telegram').KeyboardButton("❌ Скасувати")],
    ]
    await update.message.reply_text(
        "Що хочеш додати?",
        reply_markup=__import__('telegram').ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return WAITING_TYPE


async def receive_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Скасувати":
        await update.message.reply_text("❌ Скасовано.", reply_markup=main_keyboard())
        return ConversationHandler.END

    if text == "💼 Мій акаунт":
        context.user_data["add_type"] = "own"
        label = "свого акаунту"
    else:
        context.user_data["add_type"] = "watch"
        label = "трейдера якого хочеш відстежувати"

    await update.message.reply_text(
        f"📝 Введи адресу {label}:\n\n"
        f"Приклад: `0xd5B86E84Be3bC0BD2D5A3D5f9b3b5a8b3c9e0f1a`\n\n"
        f"або /cancel для скасування",
        parse_mode="Markdown"
    )
    return WAITING_ADDRESS


async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip().lower()
    if not address.startswith("0x") or len(address) != 42:
        await update.message.reply_text(
            "❌ Невірний формат. Адреса починається з `0x` і має 42 символи.\nСпробуй ще раз:",
            parse_mode="Markdown"
        )
        return WAITING_ADDRESS

    context.user_data["new_address"] = address
    is_own = context.user_data.get("add_type", "watch") == "own"
    context.user_data["is_own"] = is_own
    label = "свій акаунт" if is_own else "трейдера"

    await update.message.reply_text(
        f"✅ Адресу отримано!\n\n"
        f"Дай нікнейм для цього {label}?\n"
        f"Наприклад: {'Мій акаунт' if is_own else 'Кит №1'}\n\n"
        f"Або /skip щоб пропустити",
        parse_mode="Markdown"
    )
    return WAITING_NICKNAME


async def receive_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    address = context.user_data.get("new_address", "")
    is_own = context.user_data.get("is_own", False)
    nickname = update.message.text.strip()
    monitor.add_trader(chat_id, address, nickname=nickname, is_own=is_own)
    type_label = "💼 Твій акаунт" if is_own else "👁 Відстежуваний трейдер"
    report_label = "Щогодинний звіт по позиціях" if is_own else "Звіт по запиту або раз на добу"
    await update.message.reply_text(
        f"✅ Додано!\n\n{type_label}\n🏷 {nickname}\n"
        f"📍 `{address[:10]}...{address[-6:]}`\n\n"
        f"🔔 Нові угоди — одразу\n📊 {report_label}",
        parse_mode="Markdown", reply_markup=main_keyboard()
    )
    return ConversationHandler.END


async def skip_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    address = context.user_data.get("new_address", "")
    is_own = context.user_data.get("is_own", False)
    monitor.add_trader(chat_id, address, is_own=is_own)
    type_label = "💼 Твій акаунт" if is_own else "👁 Відстежуваний трейдер"
    await update.message.reply_text(
        f"✅ Додано!\n\n{type_label}\n📍 `{address[:10]}...{address[-6:]}`\n🟢 Моніторинг активний",
        parse_mode="Markdown", reply_markup=main_keyboard()
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Скасовано.", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============ METAR СТАНЦІЇ ============

async def metar_stations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    stations = metar_monitor.get_stations(chat_id)
    keyboard = []
    for s in stations:
        code = s["code"]
        last_time = s.get("last_metar_time", "—")
        keyboard.append([
            InlineKeyboardButton(f"✈️ {code} | {last_time}", callback_data=f"metar_info:{code}"),
            InlineKeyboardButton("🗑", callback_data=f"metar_remove:{code}")
        ])
    active = len(stations)
    text = (
        f"✈️ *METAR Станції*\n\n"
        f"Активних: *{active}*\n"
        f"Сповіщення при кожному новому оновленні METAR.\n\n"
        f"Щоб додати — введи код(и) станції\n"
        f"Наприклад: `MMMX` або `MMMX ZUUU KSEA`"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )
    return WAITING_METAR


async def metar_receive_stations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    raw = update.message.text.strip().upper()
    codes = [c.strip() for c in raw.split() if c.strip()]

    if not codes:
        await update.message.reply_text("❌ Введи хоча б один код станції.")
        return WAITING_METAR

    msg = await update.message.reply_text("⏳ Перевіряю станції...")
    added = []
    failed = []

    for code in codes:
        if len(code) < 3 or len(code) > 5 or not code.isalpha():
            failed.append(f"{code} (невірний формат)")
            continue
        data = await metar_monitor.fetch_metar(code)
        if data is None:
            failed.append(f"{code} (не знайдено)")
            continue
        result = metar_monitor.add_station(chat_id, code)
        if result == "exists":
            added.append(f"{code} (вже є)")
        else:
            added.append(f"{code} — {data['temp_f']:.1f}°F ({data['temp_c']:.1f}°C)")

    lines = ["✅ *Результат:*\n"]
    if added:
        lines.append("*Додано:*")
        for a in added:
            lines.append(f"  ✈️ {a}")
    if failed:
        lines.append("\n*Не знайдено:*")
        for f in failed:
            lines.append(f"  ❌ {f}")

    try:
        await msg.delete()
    except Exception:
        pass

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_keyboard())
    return ConversationHandler.END


# ============ CALLBACKS ============

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    data = query.data

    if data.startswith("remove:"):
        address = data.split(":", 1)[1]
        monitor.remove_trader(chat_id, address)
        nick = address[:10] + "..." + address[-6:]
        await query.edit_message_text(f"✅ Видалено: `{nick}`", parse_mode="Markdown")

    elif data == "show_all_positions":
        address = context.user_data.get("full_positions_address", "")
        positions = context.user_data.get("full_positions_data", [])
        if positions and address:
            await send_positions_report(update.get_bot(), chat_id, address, positions,
                                         show_all=True, monitor=monitor)


async def metar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    data = query.data

    if data.startswith("metar_remove:"):
        code = data.split(":", 1)[1]
        metar_monitor.remove_station(chat_id, code)
        await query.edit_message_text(f"✅ Станцію `{code}` видалено.", parse_mode="Markdown")

    elif data.startswith("metar_info:"):
        code = data.split(":", 1)[1]
        metar_data = await metar_monitor.fetch_metar(code)
        if metar_data:
            temp_f = metar_data["temp_f"]
            temp_c = metar_data["temp_c"]
            time_str = metar_data["time"]
            await query.edit_message_text(
                f"✈️ *{code}*\n🌡 {temp_f:.1f}°F ({temp_c:.1f}°C)\n🕐 {time_str}",
                parse_mode="Markdown"
            )

    elif data.startswith("viewpos:"):
        address = data.split(":", 1)[1]
        await query.edit_message_text("⏳ Завантажую позиції...")
        positions = await monitor.get_positions_report(address)
        await send_positions_report(update.get_bot(), chat_id, address, positions,
                                     context=context, monitor=monitor)


# ============ KEYBOARD BUTTONS ============

async def handle_keyboard_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "💼 Мій портфель":
        await my_portfolio(update, context, monitor)
    elif text == "👥 Трейдери":
        await watched_traders(update, context, monitor)
    elif text == "📋 Список":
        await list_command(update, context, monitor)
    elif text == "📈 Статус":
        await status_command(update, context, monitor, metar_monitor,
                              correction_monitor, peak_monitor)
    elif text == "⚠️ Виправлення":
        await corrections_command(update, context, correction_monitor)
    elif text == "🌅 Ранній пік":
        await peak_command(update, context, peak_monitor)
    elif text == "❓ Допомога":
        await help_command(update, context)


# ============ ФОНОВІ ЦИКЛИ ============

async def run_monitor_loop(app):
    logger.info("Polymarket monitor loop started")
    last_hourly = 0
    last_daily = 0

    while True:
        try:
            new_trades = await monitor.check_new_trades()
            for chat_id, trade in new_trades:
                await send_trade_notification(app.bot, chat_id, trade, monitor)

            now = asyncio.get_event_loop().time()

            if now - last_hourly >= HOURLY_INTERVAL:
                last_hourly = now
                for chat_id, trader_list in monitor.traders.items():
                    for trader in trader_list:
                        if trader.get("is_own"):
                            positions, pnl_stats = await asyncio.gather(
                                monitor.get_positions_report(trader["address"]),
                                monitor.get_pnl_stats(trader["address"])
                            )
                            await send_positions_report(
                                app.bot, chat_id, trader["address"],
                                positions, pnl_stats=pnl_stats, monitor=monitor
                            )

            if now - last_daily >= DAILY_INTERVAL:
                last_daily = now
                for chat_id, trader_list in monitor.traders.items():
                    for trader in trader_list:
                        if not trader.get("is_own"):
                            positions = await monitor.get_positions_report(trader["address"])
                            await send_positions_report(
                                app.bot, chat_id, trader["address"],
                                positions, monitor=monitor
                            )

        except Exception as e:
            logger.error(f"Polymarket loop error: {e}")

        await asyncio.sleep(POLYMARKET_CHECK_INTERVAL)


async def run_metar_loop(app):
    logger.info("METAR monitor loop started")
    while True:
        try:
            # Оновлення станцій користувача
            metar_updates = await metar_monitor.check_updates()
            for chat_id, station, data, event_type in metar_updates:
                await send_metar_notification(app.bot, chat_id, station, data, event_type)

            # Виправлення по 44 станціях
            corrections = await correction_monitor.check_corrections(metar_monitor)
            for chat_id, station, data in corrections:
                await send_correction_alert(app.bot, chat_id, station, data)

            # Ранній пік
            peak_alerts = await peak_monitor.check_forecasts()
            for chat_id, data in peak_alerts:
                await send_peak_alert(app.bot, chat_id, data)

        except Exception as e:
            logger.error(f"METAR loop error: {e}")

        await asyncio.sleep(METAR_CHECK_INTERVAL)


async def run_web_server():
    async def health(request):
        return web.Response(text="OK")
    webapp = web.Application()
    webapp.router.add_get("/", health)
    webapp.router.add_get("/health", health)
    runner = web.AppRunner(webapp)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server started on port {port}")


# ============ MAIN ============

def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation: додавання трейдера
    trader_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_command),
            MessageHandler(filters.Regex("^➕ Додати$"), add_command),
        ],
        states={
            WAITING_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_type)],
            WAITING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_address)],
            WAITING_NICKNAME: [
                CommandHandler("skip", skip_nickname),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_nickname),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Conversation: METAR станції
    metar_conv = ConversationHandler(
        entry_points=[
            CommandHandler("stations", metar_stations_command),
            MessageHandler(filters.Regex("^✈️ Станції$"), metar_stations_command),
        ],
        states={
            WAITING_METAR: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^[⚠️🌅💼👥➕📋📈❓]"),
                    metar_receive_stations
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^[⚠️🌅💼👥➕📋📈❓]"), handle_keyboard_buttons),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", lambda u, c: list_command(u, c, monitor)))
    app.add_handler(CommandHandler("status", lambda u, c: status_command(u, c, monitor, metar_monitor, correction_monitor, peak_monitor)))
    app.add_handler(CommandHandler("corrections", lambda u, c: corrections_command(u, c, correction_monitor)))
    app.add_handler(CommandHandler("peak", lambda u, c: peak_command(u, c, peak_monitor)))
    app.add_handler(trader_conv)
    app.add_handler(metar_conv)
    app.add_handler(CallbackQueryHandler(metar_callback, pattern="^metar_"))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard_buttons))

    async def post_init(application):
        await run_web_server()
        asyncio.create_task(run_monitor_loop(application))
        asyncio.create_task(run_metar_loop(application))

    app.post_init = post_init
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
