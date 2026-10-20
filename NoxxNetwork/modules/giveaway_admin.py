from datetime import datetime, timezone
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, CallbackContext,
    ConversationHandler, MessageHandler, filters
)

from NoxxNetwork import application, sudo_users, OWNER_ID, LOGGER
from NoxxNetwork.modules.giveaway_db import (
    create_giveaway, get_giveaway, draw_winners, mark_paid, winners_col, giveaways_col
)
from NoxxNetwork.modules.giveaway import build_announcement_text, build_announcement_kb

# Conversation states
(G_TITLE, G_POOL, G_WINNERS, G_ALLOCATIONS, G_DURATION, G_IMAGE, G_CONFIRM) = range(7)

def _is_admin(user_id):
    return str(user_id) in (sudo_users or []) or user_id == OWNER_ID

# ─────────────────────────────────────────────────────────────
# /gcreate Flow
# ─────────────────────────────────────────────────────────────
async def gcreate_start(update: Update, context: CallbackContext):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ Only Owner/Sudo can create giveaways.")
        return ConversationHandler.END
        
    context.user_data['gw'] = {}
    await update.message.reply_text(
        "🎁 <b>Giveaway Creation Started!</b>\n\n"
        "Step 1: Send me the <b>Title</b> of the giveaway.\n"
        "Send /cancel to abort.",
        parse_mode='HTML'
    )
    return G_TITLE

async def g_title(update: Update, context: CallbackContext):
    context.user_data['gw']['title'] = update.message.text
    await update.message.reply_text("Step 2: Send the <b>Prize Pool</b> (Total eDollers, e.g., 100000).", parse_mode='HTML')
    return G_POOL

async def g_pool(update: Update, context: CallbackContext):
    try:
        context.user_data['gw']['pool'] = int(update.message.text.replace(",", ""))
    except:
        await update.message.reply_text("❌ Invalid number. Try again.")
        return G_POOL
    await update.message.reply_text("Step 3: How many <b>Winners</b>? (e.g., 3)", parse_mode='HTML')
    return G_WINNERS

async def g_winners(update: Update, context: CallbackContext):
    try:
        context.user_data['gw']['winners'] = int(update.message.text)
    except:
        await update.message.reply_text("❌ Invalid number. Try again.")
        return G_WINNERS
    await update.message.reply_text(
        f"Step 4: Send the <b>Prize Allocation</b> for each position separated by comma.\n"
        f"Example: 50000, 30000, 20000", parse_mode='HTML'
    )
    return G_ALLOCATIONS

async def g_allocations(update: Update, context: CallbackContext):
    try:
        allocs = [int(x.strip()) for x in update.message.text.split(",")]
        if len(allocs) != context.user_data['gw']['winners']:
            await update.message.reply_text("❌ Number of allocations must match number of winners.")
            return G_ALLOCATIONS
        if sum(allocs) != context.user_data['gw']['pool']:
            await update.message.reply_text(f"❌ Total sum ({sum(allocs)}) does not match Prize Pool ({context.user_data['gw']['pool']}). Try again.")
            return G_ALLOCATIONS
        
        context.user_data['gw']['allocations'] = [
            {'position': i+1, 'amount': amt} for i, amt in enumerate(allocs)
        ]
    except:
        await update.message.reply_text("❌ Invalid format. Try again.")
        return G_ALLOCATIONS
    
    await update.message.reply_text("Step 5: Send <b>Duration</b> in hours (e.g., 24).", parse_mode='HTML')
    return G_DURATION

async def g_duration(update: Update, context: CallbackContext):
    try:
        context.user_data['gw']['duration'] = float(update.message.text)
    except:
        await update.message.reply_text("❌ Invalid number. Try again.")
        return G_DURATION
    await update.message.reply_text("Step 6: Send an <b>Image URL</b> for the giveaway (or type `skip`).", parse_mode='HTML')
    return G_IMAGE

async def g_image(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    context.user_data['gw']['image'] = None if url.lower() == 'skip' else url
    
    gw = context.user_data['gw']
    summary = (
        f"🎁 <b>Giveaway Preview</b>\n\n"
        f"📝 Title: {gw['title']}\n"
        f"💰 Pool: {gw['pool']}\n"
        f"👥 Winners: {gw['winners']}\n"
        f"⏳ Duration: {gw['duration']} hours\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm & Post", callback_data="gw_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="gw_cancel")]
    ])
    await update.message.reply_text(summary, reply_markup=kb, parse_mode='HTML')
    return G_CONFIRM

async def g_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == "gw_cancel":
        await query.edit_message_text("❌ Giveaway creation cancelled.")
        return ConversationHandler.END

    gw_data = context.user_data['gw']
    chat_id = query.message.chat_id
    
    # Create in DB
    gw = await create_giveaway(
        title=gw_data['title'],
        prize_pool=gw_data['pool'],
        winner_count=gw_data['winners'],
        allocations=gw_data['allocations'],
        duration_hours=gw_data['duration'],
        created_by=query.from_user.id,
        chat_id=chat_id,
        image_url=gw_data['image']
    )
    
    await query.edit_message_text("✅ Giveaway created! Publishing...")
    
    # Send announcement
    text = build_announcement_text(gw)
    kb = build_announcement_kb(gw)
    
    if gw_data['image']:
        msg = await context.bot.send_photo(chat_id=chat_id, photo=gw_data['image'], caption=text, parse_mode='HTML', reply_markup=kb)
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', reply_markup=kb)
        
    # Save message ID
    await giveaways_col.update_one({'giveaway_id': gw['giveaway_id']}, {'$set': {'message_id': msg.message_id}})
    return ConversationHandler.END

async def g_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("❌ Giveaway creation cancelled.")
    return ConversationHandler.END

# ─────────────────────────────────────────────────────────────
# /gdraw
# ─────────────────────────────────────────────────────────────
async def gdraw(update: Update, context: CallbackContext):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ Unauthorized.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /gdraw <giveaway_id>")
        return
        
    gw_id = context.args[0].strip().upper()
    success, result = await draw_winners(gw_id)
    
    if not success:
        await update.message.reply_text(f"❌ Draw failed: {result}")
        return
        
    winners = result
    txt = "🏆 <b>GIVEAWAY RESULTS ARE OUT!</b> 🎉\n\nCongratulations to our winners! 🎊\n\n"
    
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for w in winners:
        medal = medals.get(w['position'], f"{w['position']}.")
        name = f"<a href='tg://user?id={w['user_id']}'>{escape(w['first_name'])}</a>"
        txt += f"{medal} Winner {w['position']}: {name}\n"
        txt += f"💰 Prize: {w['prize_amount']} eDollers\n\n"
        
    txt += "🎁 <b>Prize Status:</b> Pending Manual Distribution\n"
    txt += "The owner will distribute all prizes manually."
    
    await update.message.reply_text(txt, parse_mode='HTML')

# ─────────────────────────────────────────────────────────────
# /gpaid <gw_id> <user_id>
# ─────────────────────────────────────────────────────────────
async def gpaid(update: Update, context: CallbackContext):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ Unauthorized.")
        return
        
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /gpaid <giveaway_id> <user_id>")
        return
        
    gw_id = context.args[0].strip().upper()
    user_id = int(context.args[1])
    
    success = await mark_paid(gw_id, user_id, update.effective_user.id)
    if success:
        await update.message.reply_text(f"✅ Marked prize as PAID for user {user_id}.")
    else:
        await update.message.reply_text(f"❌ Winner not found or already marked as paid.")

# ─────────────────────────────────────────────────────────────
# /gpaymentstatus <gw_id>
# ─────────────────────────────────────────────────────────────
async def gpaymentstatus(update: Update, context: CallbackContext):
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("⚠️ Unauthorized.")
        return
        
    if not context.args:
        await update.message.reply_text("Usage: /gpaymentstatus <giveaway_id>")
        return
        
    gw_id = context.args[0].strip().upper()
    winners = await winners_col.find({'giveaway_id': gw_id}).to_list(length=None)
    
    if not winners:
        await update.message.reply_text("❌ No winners found for this giveaway.")
        return
        
    txt = f"💳 <b>Payment Status for {gw_id}</b>\n\n"
    for w in winners:
        status_icon = "✅ PAID" if w['payment_status'] == 'paid' else "⏳ PENDING"
        txt += f"👤 {escape(w['first_name'])} (ID: {w['user_id']}) — {status_icon} ({w['prize_amount']} eDollers)\n"
        
    await update.message.reply_text(txt, parse_mode='HTML')

# ─────────────────────────────────────────────────────────────
# Handler Registration
# ─────────────────────────────────────────────────────────────
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('gcreate', gcreate_start)],
    states={
        G_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_title)],
        G_POOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_pool)],
        G_WINNERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_winners)],
        G_ALLOCATIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_allocations)],
        G_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_duration)],
        G_IMAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, g_image)],
        G_CONFIRM: [CallbackQueryHandler(g_confirm, pattern=r'^gw_')],
    },
    fallbacks=[CommandHandler('cancel', g_cancel)],
)

application.add_handler(conv_handler)
application.add_handler(CommandHandler("gdraw", gdraw, block=False))
application.add_handler(CommandHandler("gpaid", gpaid, block=False))
application.add_handler(CommandHandler("gpaymentstatus", gpaymentstatus, block=False))
