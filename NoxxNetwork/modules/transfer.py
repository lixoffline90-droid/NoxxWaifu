"""
Harem Transfer — Move entire collection from one user to another.

Command:
    /TransferHarem <from_user_id> <to_user_id>
    Aliases: /transferharem, /tharem

Access:
    Sudo / Owner only.
"""
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    user_collection,
    sudo_users,
    OWNER_ID,
    LOGGER,
)


def _is_sudo(user_id: int) -> bool:
    return str(user_id) in (sudo_users or []) or user_id == OWNER_ID


async def transfer_harem(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id

    # ─── Sudo/Owner only ────────────────────────────────────────
    if not _is_sudo(caller_id):
        await update.message.reply_text(
            "⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ."
        )
        return

    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(
            "❌ U sᴀɢᴇ: <code>/TransferHarem &lt;from_user_id&gt; &lt;to_user_id&gt;</code>\n\n"
            "Exᴀᴍᴘʟᴇ: <code>/TransferHarem 123456789 987654321</code>",
            parse_mode='HTML',
        )
        return

    try:
        from_id = int(args[0])
        to_id = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴜsᴇʀ ID.")
        return

    if from_id == to_id:
        await update.message.reply_text("❌ Sᴀᴍᴇ ᴜsᴇʀ ID — ᴄᴀɴ'ᴛ ᴛʀᴀɴsғᴇʀ ᴛᴏ sᴇʟғ.")
        return

    # ─── Fetch both users ───────────────────────────────────────
    from_user = await user_collection.find_one({'id': from_id})
    if not from_user:
        await update.message.reply_text(
            f"❌ Usᴇʀ <code>{from_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴅᴀᴛᴀʙᴀsᴇ.",
            parse_mode='HTML',
        )
        return

    source_chars = list(from_user.get('characters', []))
    if not source_chars:
        await update.message.reply_text(
            f"❌ Usᴇʀ <code>{from_id}</code> ʜᴀs ᴀɴ ᴇᴍᴘᴛʏ ʜᴀʀᴇᴍ.",
            parse_mode='HTML',
        )
        return

    from_name = escape(str(from_user.get('first_name') or f"User {from_id}"))
    from_username = from_user.get('username')

    # ─── Verify destination user (create if not exists) ─────────
    to_user = await user_collection.find_one({'id': to_id})
    if not to_user:
        # Create new user doc for receiver
        to_user = {
            'id': to_id,
            'username': None,
            'first_name': None,
            'characters': [],
        }
        await user_collection.insert_one(dict(to_user))

    to_name = escape(str(to_user.get('first_name') or f"User {to_id}"))
    to_username = to_user.get('username')

    # ─── Do the transfer ────────────────────────────────────────
    # 1. Push all chars to receiver
    await user_collection.update_one(
        {'id': to_id},
        {'$push': {'characters': {'$each': source_chars}}},
    )

    # 2. Clear source's characters
    await user_collection.update_one(
        {'id': from_id},
        {'$set': {'characters': []}},
    )

    # 3. Clear source's favorites (they belonged to old chars)
    try:
        await user_collection.update_one(
            {'id': from_id},
            {'$set': {'favorites': []}},
        )
    except Exception:
        pass

    count = len(source_chars)

    # ─── Build response ─────────────────────────────────────────
    from_mention = f'<a href="tg://user?id={from_id}">{from_name}</a>'
    to_mention = f'<a href="tg://user?id={to_id}">{to_name}</a>'

    from_uname_line = f" • @{escape(from_username)}" if from_username else ""
    to_uname_line = f" • @{escape(to_username)}" if to_username else ""

    text = (
        f"✅ <b>Hᴀʀᴇᴍ Tʀᴀɴsғᴇʀ Cᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
        f"📤 <b>Fʀᴏᴍ:</b> {from_mention}{from_uname_line}\n"
        f"    🆔 <code>{from_id}</code>\n\n"
        f"📥 <b>Tᴏ:</b> {to_mention}{to_uname_line}\n"
        f"    🆔 <code>{to_id}</code>\n\n"
        f"📊 <b>Tᴏᴛᴀʟ ᴛʀᴀɴsғᴇʀʀᴇᴅ:</b> <b>{count}</b> ᴄʜᴀʀᴀᴄᴛᴇʀ(s)\n"
        f"🎴 Sᴏᴜʀᴄᴇ ʜᴀʀᴇᴍ ɪs ɴᴏᴡ ᴇᴍᴘᴛʏ."
    )

    try:
        await update.message.reply_text(text, parse_mode='HTML')
    except Exception:
        # Fallback without HTML
        await update.message.reply_text(
            f"✅ Harem transfer complete\n"
            f"From: {from_id}\n"
            f"To: {to_id}\n"
            f"Total: {count} characters"
        )

    LOGGER.info(f"[transfer_harem] {caller_id} moved {count} chars from {from_id} to {to_id}")


# ══════════════════════════════════════════════════════════════
# Handler registration
# ══════════════════════════════════════════════════════════════
application.add_handler(
    CommandHandler(
        ["TransferHarem", "transferharem", "tharem"],
        transfer_harem,
        block=False,
    )
)
