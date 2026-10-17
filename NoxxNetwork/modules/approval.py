"""
Approval system — lets owner/sudo grant limited upload access.

Commands:
    /wallow <user_id>       — Approve a user (reply to their message, or pass ID)
    /wdeny <user_id>        — Revoke approval
    /approvedlist           — List all approved uploaders

Only Owner / Sudo can use these commands.
Approved users can use ONLY:
    /upload
    /update
"""
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    db,
    sudo_users,
    OWNER_ID,
    LOGGER,
)


approved_uploaders_col = db['approved_uploaders']


def _is_sudo(user_id: int) -> bool:
    return str(user_id) in (sudo_users or []) or user_id == OWNER_ID


# ──────────────────────────────────────────────────────────────
# /wallow <user_id>  |  reply to user
# ──────────────────────────────────────────────────────────────
async def wallow(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text(
            "⚠️ Oɴʟʏ Oᴡɴᴇʀ / Sᴜᴅᴏ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ."
        )
        return

    target = None

    # Reply mode
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    # ID mode
    elif context.args:
        try:
            tid = int(context.args[0])
            try:
                member = await context.bot.get_chat_member(update.effective_chat.id, tid)
                target = member.user
            except Exception:
                class _U:
                    pass
                target = _U()
                target.id = tid
                target.first_name = None
                target.username = None
        except ValueError:
            await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴜsᴇʀ ID.")
            return

    if not target:
        await update.message.reply_text(
            "U sᴀɢᴇ:\n"
            "• Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ <code>/wallow</code>\n"
            "• Oʀ <code>/wallow &lt;user_id&gt;</code>",
            parse_mode='HTML',
        )
        return

    if target.id == OWNER_ID or str(target.id) in (sudo_users or []):
        await update.message.reply_text(
            "ℹ️ Tʜɪs ᴜsᴇʀ ɪs ᴀʟʀᴇᴀᴅʏ Oᴡɴᴇʀ / Sᴜᴅᴏ."
        )
        return

    # Check if already approved
    existing = await approved_uploaders_col.find_one({'user_id': target.id})
    if existing:
        await update.message.reply_text(
            f"ℹ️ Usᴇʀ <a href=\"tg://user?id={target.id}\">"
            f"{escape(target.first_name or 'User')}</a> ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴘᴘʀᴏᴠᴇᴅ.",
            parse_mode='HTML',
        )
        return

    await approved_uploaders_col.update_one(
        {'user_id': target.id},
        {'$set': {
            'user_id': target.id,
            'first_name': target.first_name,
            'username': target.username,
            'approved_by': caller_id,
            'approved_at': int(__import__('time').time()),
        }},
        upsert=True,
    )

    await update.message.reply_text(
        f"✅ <b>Usᴇʀ Aᴘᴘʀᴏᴠᴇᴅ</b>\n\n"
        f"👤 <a href=\"tg://user?id={target.id}\">{escape(target.first_name or 'User')}</a>\n"
        f"🆔 <code>{target.id}</code>\n\n"
        f"🔓 Tʜᴇʏ ᴄᴀɴ ɴᴏᴡ ᴜsᴇ:\n"
        f"• <code>/upload</code>\n"
        f"• <code>/update</code>",
        parse_mode='HTML',
    )
    LOGGER.info(f"[approval] {caller_id} approved {target.id} for upload/update")


# ──────────────────────────────────────────────────────────────
# /wdeny <user_id>  |  reply
# ──────────────────────────────────────────────────────────────
async def wdeny(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text(
            "⚠️ Oɴʟʏ Oᴡɴᴇʀ / Sᴜᴅᴏ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ."
        )
        return

    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            tid = int(context.args[0])
            class _U:
                pass
            target = _U()
            target.id = tid
            target.first_name = None
        except ValueError:
            await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴜsᴇʀ ID.")
            return

    if not target:
        await update.message.reply_text(
            "U sᴀɢᴇ:\n"
            "• Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ <code>/wdeny</code>\n"
            "• Oʀ <code>/wdeny &lt;user_id&gt;</code>",
            parse_mode='HTML',
        )
        return

    result = await approved_uploaders_col.delete_one({'user_id': target.id})
    if result.deleted_count == 0:
        await update.message.reply_text("ℹ️ Usᴇʀ ᴡᴀs ɴᴏᴛ ᴀᴘᴘʀᴏᴠᴇᴅ.")
        return

    await update.message.reply_text(
        f"✅ <b>Aᴘᴘʀᴏᴠᴀʟ Rᴇᴠᴏᴋᴇᴅ</b>\n\n"
        f"👤 <a href=\"tg://user?id={target.id}\">{escape(target.first_name or 'User')}</a>\n"
        f"🆔 <code>{target.id}</code>",
        parse_mode='HTML',
    )


# ──────────────────────────────────────────────────────────────
# /approvedlist
# ──────────────────────────────────────────────────────────────
async def approvedlist(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text(
            "⚠️ Oɴʟʏ Oᴡɴᴇʀ / Sᴜᴅᴏ ᴄᴀɴ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ."
        )
        return

    docs = await approved_uploaders_col.find({}).to_list(length=None)

    if not docs:
        await update.message.reply_text("📋 Nᴏ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜsᴇʀs ʏᴇᴛ.")
        return

    lines = [f"📋 <b>Aᴘᴘʀᴏᴠᴇᴅ Uᴘʟᴏᴀᴅᴇʀs</b> ({len(docs)})\n"]
    for i, d in enumerate(docs, 1):
        name = escape(str(d.get('first_name') or 'Unknown'))
        uname = f" @{escape(d.get('username'))}" if d.get('username') else ""
        lines.append(f"{i}. {name}{uname} — <code>{d.get('user_id')}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


# ══════════════════════════════════════════════════════════════
# Handler registration
# ══════════════════════════════════════════════════════════════
application.add_handler(CommandHandler("wallow", wallow, block=False))
application.add_handler(CommandHandler("wdeny", wdeny, block=False))
application.add_handler(CommandHandler("approvedlist", approvedlist, block=False))
