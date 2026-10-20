import time
from datetime import datetime, timezone
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext

from NoxxNetwork import application, LOGGER
from NoxxNetwork.modules.giveaway_db import (
    get_active_giveaway, get_giveaway, join_giveaway, entries_col, winners_col
)

def _format_time_left(ends_at_ts):
    remaining = int(ends_at_ts - datetime.now(timezone.utc).timestamp())
    if remaining <= 0:
        return "Ended"
    h = remaining // 3600
    m = (remaining % 3600) // 60
    return f"{h}h {m}m"

def build_announcement_text(gw):
    time_left = _format_time_left(gw['ends_at'])
    
    # Generate prize breakdown
    prizes = []
    for alloc in gw.get('prize_allocations', []):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        icon = medals.get(alloc['position'], f"{alloc['position']}.")
        prizes.append(f"{icon} Winner {alloc['position']} — {alloc['amount']} eDollers")
    
    text = (
        f"🎉 <b>{escape(gw['title']).upper()}</b> 🎁\n\n"
        f"🏆 <b>PRIZE POOL:</b> {gw['prize_pool']} eDollers\n\n"
        + "\n".join(prizes) + "\n\n"
        f"📜 <b>RULES</b>\n"
        f"➤ Tap the button below to enter.\n"
        f"➤ Only one entry per account.\n"
        f"➤ Prizes are distributed manually.\n\n"
        f"⏳ <b>Ends:</b> {time_left}\n"
        f"👥 <b>Participants:</b> {gw['participant_count']}\n\n"
        f"<i>Hosted by Lix</i>"
    )
    return text

def build_announcement_kb(gw):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎉 Join Giveaway", callback_data=f"join_gw:{gw['giveaway_id']}")]
    ])

async def cmd_giveaway(update: Update, context: CallbackContext):
    gw = await get_active_giveaway()
    if not gw:
        await update.message.reply_text("❌ No active giveaways right now. Check back later!")
        return
    
    text = build_announcement_text(gw)
    kb = build_announcement_kb(gw)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=kb)

async def cmd_myentry(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    gw = await get_active_giveaway()
    if not gw:
        await update.message.reply_text("❌ No active giveaway.")
        return
    
    entry = await entries_col.find_one({'giveaway_id': gw['giveaway_id'], 'user_id': user_id})
    if entry:
        await update.message.reply_text(f"✅ You are entered in <b>{gw['title']}</b>!", parse_mode='HTML')
    else:
        await update.message.reply_text("⚠️ You have not joined the active giveaway yet. Use /giveaway to join.")

async def cmd_history(update: Update, context: CallbackContext):
    from NoxxNetwork.modules.giveaway_db import giveaways_col
    history = await giveaways_col.find({'status': 'drawn'}).sort('drawn_at', -1).limit(5).to_list(length=5)
    if not history:
        await update.message.reply_text("No past giveaways found.")
        return
        
    txt = "📜 <b>Recent Giveaway History</b>\n\n"
    for g in history:
        txt += f"🎁 <b>{g['title']}</b> (Pool: {g['prize_pool']})\n"
        txt += f"🆔 ID: <code>{g['giveaway_id']}</code>\n"
        txt += f"📅 Date: {g['drawn_at'].strftime('%d-%b-%Y')}\n\n"
    await update.message.reply_text(txt, parse_mode='HTML')

async def join_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data.split(':')
    if len(data) != 2:
        await query.answer("Invalid data.", show_alert=True)
        return
        
    gw_id = data[1]
    user = query.from_user
    
    success, result = await join_giveaway(gw_id, user.id, user.username, user.first_name)
    
    if not success:
        await query.answer(result, show_alert=True)
        return
        
    await query.answer("✅ Successfully joined the giveaway!", show_alert=False)
    
    # Update the message with new participant count
    try:
        gw = await get_giveaway(gw_id)
        if gw and gw.get('message_id'):
            await context.bot.edit_message_text(
                chat_id=gw['chat_id'],
                message_id=gw['message_id'],
                text=build_announcement_text(gw),
                parse_mode='HTML',
                reply_markup=build_announcement_kb(gw)
            )
    except Exception as e:
        LOGGER.warning(f"Failed to update participant count: {e}")

# Register Handlers
application.add_handler(CommandHandler("giveaway", cmd_giveaway, block=False))
application.add_handler(CommandHandler("myentry", cmd_myentry, block=False))
application.add_handler(CommandHandler("giveaway_history", cmd_history, block=False))
application.add_handler(CallbackQueryHandler(join_callback, pattern=r'^join_gw:', block=False))
