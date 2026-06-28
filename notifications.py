import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def send_trade_notification(bot, chat_id: str, trade: dict, monitor):
    market_url = trade.get("market_url", "")
    market_title = trade.get("market_title", "Невідомий ринок")
    outcome = trade.get("outcome", "")
    usd_value = trade.get("usd_value", 0)
    trader = trade.get("trader_address", "")
    timestamp = trade.get("timestamp", "")
    event_type = trade.get("event_type", "open")
    nick = monitor.get_nickname(chat_id, trader)

    is_own = any(
        t.get("is_own") and t["address"] == trader.lower()
        for t in monitor.get_traders(chat_id)
    )
    account_label = "💼 Мій акаунт" if is_own else f"👁 {nick}"

    if event_type == "close":
        avg_price = trade.get("avg_price", 0)
        size = trade.get("size", 0)
        text = (
            f"🔕 *Позицію закрито!*\n\n"
            f"{account_label}\n\n"
            f"📌 *{market_title}*\n\n"
            f"❌ Продаж — {outcome}\n"
            f"💰 Сума: *${usd_value:.2f}*\n"
            f"📊 Ціна входу: {avg_price:.3f} | Розмір: {size:.2f}\n"
            f"🕐 {timestamp}"
        )
    else:
        side = trade.get("side", "BUY")
        size = trade.get("size", 0)
        price = trade.get("price", 0)
        side_emoji = "🟢" if side == "BUY" else "🔴"
        side_text = "КУПІВЛЯ" if side == "BUY" else "ПРОДАЖ"
        text = (
            f"🔔 *Нова угода!*\n\n"
            f"{account_label}\n\n"
            f"📌 *{market_title}*\n\n"
            f"{side_emoji} *{side_text}* — {outcome}\n"
            f"💰 Сума: *${usd_value:.2f}*\n"
            f"📊 Ціна: {price:.3f} | Розмір: {size:.2f}\n"
            f"🕐 {timestamp}"
        )

    keyboard = []
    if market_url:
        keyboard.append([InlineKeyboardButton("🔗 Відкрити на Polymarket", url=market_url)])

    try:
        await bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    except Exception as e:
        logger.error(f"Failed to send trade notification: {e}")


async def send_positions_report(bot, chat_id: str, address: str, positions: list,
                                 show_all: bool = False, context=None,
                                 pnl_stats: dict = None, monitor=None):
    from datetime import datetime, timezone
    nick = monitor.get_nickname(chat_id, address) if monitor else address[:10]
    now = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    MAX_SHOW = 5

    if not positions:
        text = f"📊 *{nick}*\n🕐 {now}\n\n— Відкритих позицій немає"
        if pnl_stats:
            m_pnl = pnl_stats["pnl_month"]
            a_pnl = pnl_stats["pnl_alltime"]
            m_sign = "+" if m_pnl >= 0 else ""
            a_sign = "+" if a_pnl >= 0 else ""
            m_color = "🟢" if m_pnl >= 0 else "🔴"
            a_color = "🟢" if a_pnl >= 0 else "🔴"
            text += (
                f"\n\n📊 *Profit/Loss:*\n"
                f"{m_color} {pnl_stats['month_name']}: *{m_sign}${m_pnl:.2f}*\n"
                f"{a_color} За весь час: *{a_sign}${a_pnl:.2f}*"
            )
        try:
            await bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send positions report: {e}")
        return

    total_value = sum(p.get("current_value", 0) for p in positions)
    total_pnl = sum(p.get("pnl", 0) for p in positions)
    total_invested = sum(p.get("invested", 0) for p in positions)
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    pnl_sign = "+" if total_pnl >= 0 else ""

    lines = [
        f"📊 *{nick}*",
        f"🕐 {now}",
        f"",
        f"💼 {len(positions)} позицій  |  💰 ${total_value:.2f}",
        f"{pnl_emoji} PnL відкритих: *{pnl_sign}${total_pnl:.2f}* ({pnl_sign}{total_pnl_pct:.1f}%)",
    ]

    if pnl_stats:
        m_pnl = pnl_stats["pnl_month"]
        a_pnl = pnl_stats["pnl_alltime"]
        m_sign = "+" if m_pnl >= 0 else ""
        a_sign = "+" if a_pnl >= 0 else ""
        m_color = "🟢" if m_pnl >= 0 else "🔴"
        a_color = "🟢" if a_pnl >= 0 else "🔴"
        total_balance = pnl_stats.get("total_balance", 0)
        usdc_balance = pnl_stats.get("usdc_balance", 0)
        open_value = pnl_stats.get("open_value", 0)
        if total_balance > 0:
            lines.append(f"")
            lines.append(f"💼 Баланс: *${total_balance:.2f}*")
            lines.append(f"   💵 Вільно: ${usdc_balance:.2f}  |  📊 Позиції: ${open_value:.2f}")
        lines.append(f"")
        lines.append(f"📊 *Profit/Loss:*")
        lines.append(f"{m_color} {pnl_stats['month_name']}: *{m_sign}${m_pnl:.2f}*")
        lines.append(f"{a_color} За весь час: *{a_sign}${a_pnl:.2f}*")

    lines += ["", "─────────────────"]

    show_list = positions if show_all else positions[:MAX_SHOW]
    for i, pos in enumerate(show_list, 1):
        title = pos.get("market_title", "—")
        title = title[:45] + "..." if len(title) > 45 else title
        outcome = pos.get("outcome", "")
        cur_val = pos.get("current_value", 0)
        pnl = pos.get("pnl", 0)
        pnl_pct = pos.get("pnl_pct", 0)
        cur_price = pos.get("current_price", 0)
        avg_price = pos.get("avg_price", 0)
        p_emoji = "🟢" if pnl >= 0 else "🔴"
        p_sign = "+" if pnl >= 0 else ""
        market_url = pos.get("market_url", "")
        outcome_icon = "✅" if outcome.lower() == "yes" else "❌"
        pnl_icon = "📈" if pnl >= 0 else "📉"

        lines.append(f"\n*{i}. {title}*")
        lines.append(f"   {outcome_icon} {outcome}  {avg_price:.3f} → {cur_price:.3f}")
        lines.append(f"   💵 ${cur_val:.2f}  {p_emoji} {pnl_icon} {p_sign}${pnl:.2f} ({p_sign}{pnl_pct:.1f}%)")
        if market_url:
            lines.append(f"   [🔗 Відкрити]({market_url})")

    text = "\n".join(lines)
    keyboard = []
    remaining = len(positions) - MAX_SHOW
    if not show_all and remaining > 0:
        if context:
            context.user_data["full_positions_address"] = address
            context.user_data["full_positions_data"] = positions
        keyboard.append([InlineKeyboardButton(
            f"👁 Показати ще {remaining} позицій",
            callback_data="show_all_positions"
        )])

    try:
        await bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )
    except Exception as e:
        logger.error(f"Failed to send positions report: {e}")


async def send_metar_notification(bot, chat_id: str, station: str, data: dict, event_type: str = "new"):
    temp_f = data["temp_f"]
    temp_c = data["temp_c"]
    time_str = data["time"]
    raw = data.get("raw", "")

    if event_type == "correction":
        old_temp_c = data.get("old_temp_c", 0)
        old_temp_f = data.get("old_temp_f", 0)
        diff = temp_c - old_temp_c
        sign = "+" if diff > 0 else ""
        text = (
            f"⚠️ *{station} — METAR виправлено!*\n\n"
            f"🕐 Час: {time_str} (той самий)\n"
            f"📉 Було: *{old_temp_f:.1f}°F* ({old_temp_c:.1f}°C)\n"
            f"📈 Стало: *{temp_f:.1f}°F* ({temp_c:.1f}°C)\n"
            f"Δ {sign}{diff:.1f}°C\n\n"
            f"💡 Перевір ціни на ринку!\n"
            f"`{raw[:80]}`"
        )
    else:
        text = (
            f"✈️ *{station}* — нове METAR оновлення\n\n"
            f"🌡 *{temp_f:.1f}°F* ({temp_c:.1f}°C)\n"
            f"🕐 {time_str}\n\n"
            f"`{raw[:80]}`"
        )

    try:
        await bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send METAR notification: {e}")


async def send_correction_alert(bot, chat_id: str, station: str, data: dict):
    old_temp_c = data.get("old_temp_c", 0)
    old_temp_f = data.get("old_temp_f", 0)
    new_temp_c = data["temp_c"]
    new_temp_f = data["temp_f"]
    time_str = data["time"]
    raw = data.get("raw", "")
    diff = new_temp_c - old_temp_c
    sign = "+" if diff > 0 else ""

    text = (
        f"⚠️ *{station} — METAR виправлено!*\n\n"
        f"🕐 Час: {time_str} (той самий)\n"
        f"📉 Було: *{old_temp_f:.1f}°F* ({old_temp_c:.1f}°C)\n"
        f"📈 Стало: *{new_temp_f:.1f}°F* ({new_temp_c:.1f}°C)\n"
        f"Δ {sign}{diff:.1f}°C\n\n"
        f"💡 Перевір ціни на ринку!\n"
        f"`{raw[:80]}`"
    )
    try:
        await bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send correction alert: {e}")


async def send_peak_alert(bot, chat_id: str, data: dict):
    station = data["station"]
    city = data["city"]
    date = data["date"]
    max_temp = data["max_temp"]
    max_time = data["max_time"]
    day_max = data["day_max"]
    max_f = max_temp * 9/5 + 32

    text = (
        f"🌅 *{station} ({city}) — пік температури на початку доби!*\n\n"
        f"📅 Дата: {date}\n"
        f"🌡 Макс: *{max_temp}°C ({max_f:.1f}°F)* о {max_time} місцевого\n"
        f"📉 Вдень буде: {day_max}°C\n\n"
        f"💡 Ринки на температуру вище {max_temp}°C виглядають переоціненими!"
    )
    try:
        await bot.send_message(chat_id=int(chat_id), text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send peak alert: {e}")
