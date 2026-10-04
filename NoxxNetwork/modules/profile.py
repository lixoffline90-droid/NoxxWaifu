from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    user_collection,
    collection,
    db,
    PHOTO_URL,
)

banned_users_col = db['banned_users']
coins_collection = db['user_coins']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt(number: int) -> str:
    return f"{int(number):,}"


def _progress_bar(percent: float, length: int = 20) -> str:
    """Return a unicode progress bar like: ██████░░░░░░░░░░░░░░ 30%"""
    filled = int(round(length * percent / 100))
    filled = max(0, min(length, filled))
    bar = "█" * filled + "░" * (length - filled)
    return bar


async def _get_ban_status(user_id: int) -> str:
    doc = await banned_users_col.find_one({'user_id': user_id})
    if doc:
        return "🚫 Banned"
    return "✅ Not Banned"


async def _get_coins(user_id: int) -> int:
    doc = await coins_collection.find_one({'user_id': user_id})
    return int(doc.get('coins', 0)) if doc else 0


# ---------------------------------------------------------------------------
# /profile [user_id]  —  shows your profile or someone else's
# ---------------------------------------------------------------------------
async def profile(update: Update, context: CallbackContext) -> None:
    message = update.effective_message

    # ─── Determine target user ─────────────────────────────────────
    target = None

    if message.reply_to_message and message.reply_to_message.from_user:
        # Reply → show that user's profile
        target = message.reply_to_message.from_user
    elif context.args:
        # /profile 123456789
        try:
            target_id = int(context.args[0])
            try:
                member = await context.bot.get_chat_member(
                    update.effective_chat.id, target_id
                )
                target = member.user
            except Exception:
                # Minimal fallback
                class _U:
                    pass
                target = _U()
                target.id = target_id
                target.first_name = f"User {target_id}"
                target.username = None
        except ValueError:
            await message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴜsᴇʀ ID.")
            return
    else:
        # Own profile
        target = update.effective_user

    if not target:
        await message.reply_text("❌ Cᴏᴜʟᴅ ɴᴏᴛ ʀᴇsᴏʟᴠᴇ ᴛʜᴇ ᴜsᴇʀ.")
        return

    user_id = target.id
    first_name = escape(target.first_name or "User")
    username_display = f"@{target.username}" if target.username else "—"

    # ─── Fetch data ────────────────────────────────────────────────
    user_doc = await user_collection.find_one({'id': user_id})
    owned_chars = user_doc.get('characters', []) if user_doc else []
    owned_count = len(owned_chars)

    total_chars = await collection.count_documents({})

    if total_chars > 0:
        percent = (owned_count / total_chars) * 100
    else:
        percent = 0.0

    ban_status = await _get_ban_status(user_id)
    coins = await _get_coins(user_id)

    progress_bar = _progress_bar(percent)

    # ─── Caption ───────────────────────────────────────────────────
    caption = (
        f"🌌✨ <b>{first_name}'s Profile</b> ✨🌌\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📜 <b>Name:</b> {first_name}\n"
        f"📛 <b>Username:</b> {escape(username_display)}\n"
        f"🔒 <b>Status:</b> {ban_status}\n"
        f"💵 <b>ED:</b> {_fmt(coins)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚔️ <b>Collection:</b> {owned_count}/{total_chars}\n"
        f"[{percent:.2f}%]\n"
        f"📊 <b>Progress:</b>\n"
        f"<code>{progress_bar}</code>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📚 Sᴇᴇ Cᴏʟʟᴇᴄᴛɪᴏɴ",
            switch_inline_query_current_chat=f"collection.{user_id}",
        )]
    ])

    # ─── Image (use first photo from PHOTO_URL if available) ───────
    image_url = None
    try:
        if PHOTO_URL:
            import random as _r
            image_url = _r.choice(PHOTO_URL)
    except Exception:
        image_url = None

    if image_url:
        try:
            await message.reply_photo(
                photo=image_url,
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass

    await message.reply_text(
        caption,
        parse_mode='HTML',
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
application.add_handler(
    CommandHandler(["profile", "me", "myprofile"], profile, block=False)
)
