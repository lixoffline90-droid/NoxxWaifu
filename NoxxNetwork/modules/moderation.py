from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import application, db, sudo_users, OWNER_ID, LOGGER

banned_users_col = db['banned_users']
banned_groups_col = db['banned_groups']


def _is_sudo(user_id: int) -> bool:
    return str(user_id) in sudo_users or user_id == OWNER_ID


async def is_user_banned(user_id: int) -> bool:
    doc = await banned_users_col.find_one({'user_id': user_id})
    return doc is not None


async def is_group_banned(chat_id: int) -> bool:
    doc = await banned_groups_col.find_one({'chat_id': chat_id})
    return doc is not None


# ---------------------------------------------------------------------------
# /banuser (reply) or /banuser <user_id>
# ---------------------------------------------------------------------------
async def banuser(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target_id = int(context.args[0])
            try:
                member = await context.bot.get_chat_member(update.effective_chat.id, target_id)
                target = member.user
            except Exception:
                # Can't resolve — create minimal record
                class _User:
                    pass
                target = _User()
                target.id = target_id
                target.first_name = None
                target.username = None
        except ValueError:
            await update.message.reply_text("Iɴᴠᴀʟɪᴅ ᴜsᴇʀ ID.")
            return

    if not target:
        await update.message.reply_text(
            "Usᴀɢᴇ:\n"
            "• Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /banuser\n"
            "• Oʀ /banuser <user_id>"
        )
        return

    if target.id == OWNER_ID:
        await update.message.reply_text("⚠️ Cᴀɴ'ᴛ ʙᴀɴ ᴛʜᴇ ᴏᴡɴᴇʀ!")
        return
    if str(target.id) in sudo_users:
        await update.message.reply_text("⚠️ Cᴀɴ'ᴛ ʙᴀɴ ᴀ sᴜᴅᴏ ᴜsᴇʀ!")
        return

    await banned_users_col.update_one(
        {'user_id': target.id},
        {'$set': {
            'user_id': target.id,
            'first_name': target.first_name,
            'username': target.username,
            'banned_by': caller_id,
        }},
        upsert=True,
    )

    await update.message.reply_text(
        f"🚫 <b>Usᴇʀ Bᴀɴɴᴇᴅ</b>\n\n"
        f"👤 <a href=\"tg://user?id={target.id}\">{escape(target.first_name or 'User')}</a>\n"
        f"🆔 <code>{target.id}</code>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# /unbanuser (reply) or /unbanuser <user_id>
# ---------------------------------------------------------------------------
async def unbanuser(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    elif context.args:
        try:
            target_id = int(context.args[0])
            class _User:
                pass
            target = _User()
            target.id = target_id
            target.first_name = None
            target.username = None
        except ValueError:
            await update.message.reply_text("Iɴᴠᴀʟɪᴅ ᴜsᴇʀ ID.")
            return

    if not target:
        await update.message.reply_text(
            "Usᴀɢᴇ:\n"
            "• Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /unbanuser\n"
            "• Oʀ /unbanuser <user_id>"
        )
        return

    result = await banned_users_col.delete_one({'user_id': target.id})
    if result.deleted_count == 0:
        await update.message.reply_text("ℹ️ Usᴇʀ ᴡᴀs ɴᴏᴛ ʙᴀɴɴᴇᴅ.")
        return

    name = escape(target.first_name or 'User')
    await update.message.reply_text(
        f"✅ <b>Usᴇʀ Uɴʙᴀɴɴᴇᴅ</b>\n\n"
        f"👤 <a href=\"tg://user?id={target.id}\">{name}</a>\n"
        f"🆔 <code>{target.id}</code>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# /bangroup <group_id>   — ID se ban karo (kahin se bhi)
# ---------------------------------------------------------------------------
async def bangroup(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usᴀɢᴇ: /bangroup <group_id>\n"
            "Exᴀᴍᴘʟᴇ: /bangroup -1001234567890"
        )
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Iɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ID. Mᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ.")
        return

    # Try to fetch group name (best-effort)
    group_name = "Unknown Group"
    try:
        chat = await context.bot.get_chat(group_id)
        group_name = chat.title or group_name
    except Exception as e:
        LOGGER.warning(f"Could not fetch group {group_id}: {e}")

    await banned_groups_col.update_one(
        {'chat_id': group_id},
        {'$set': {
            'chat_id': group_id,
            'group_name': group_name,
            'banned_by': caller_id,
        }},
        upsert=True,
    )

    await update.message.reply_text(
        f"🚫 <b>Gʀᴏᴜᴘ Bᴀɴɴᴇᴅ</b>\n\n"
        f"📛 {escape(group_name)}\n"
        f"🆔 <code>{group_id}</code>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# /unbangroup <group_id>   — ID se unban karo
# ---------------------------------------------------------------------------
async def unbangroup(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usᴀɢᴇ: /unbangroup <group_id>\n"
            "Exᴀᴍᴘʟᴇ: /unbangroup -1001234567890"
        )
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Iɴᴠᴀʟɪᴅ ɢʀᴏᴜᴘ ID. Mᴜsᴛ ʙᴇ ᴀ ɴᴜᴍʙᴇʀ.")
        return

    # Lookup existing record for the name
    doc = await banned_groups_col.find_one({'chat_id': group_id})
    if not doc:
        await update.message.reply_text(
            f"ℹ️ Gʀᴏᴜᴘ <code>{group_id}</code> ᴡᴀs ɴᴏᴛ ʙᴀɴɴᴇᴅ.",
            parse_mode='HTML',
        )
        return

    group_name = doc.get('group_name', 'Unknown Group')
    await banned_groups_col.delete_one({'chat_id': group_id})

    await update.message.reply_text(
        f"✅ <b>Gʀᴏᴜᴘ Uɴʙᴀɴɴᴇᴅ</b>\n\n"
        f"📛 {escape(group_name)}\n"
        f"🆔 <code>{group_id}</code>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# /bannedlist — show all banned users/groups
# ---------------------------------------------------------------------------
async def bannedlist(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Oɴʟʏ Sᴜᴅᴏ Usᴇʀs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.")
        return

    users = await banned_users_col.find({}).to_list(length=None)
    groups = await banned_groups_col.find({}).to_list(length=None)

    lines = ["🚫 <b>Bᴀɴ Lɪsᴛ</b>", ""]

    lines.append(f"👤 <b>Bᴀɴɴᴇᴅ Usᴇʀs ({len(users)}):</b>")
    if users:
        for u in users[:20]:
            lines.append(f"• <code>{u['user_id']}</code> — {escape(str(u.get('first_name') or 'Unknown'))}")
        if len(users) > 20:
            lines.append(f"<i>...and {len(users) - 20} more</i>")
    else:
        lines.append("<i>None</i>")

    lines.append("")
    lines.append(f"👥 <b>Bᴀɴɴᴇᴅ Gʀᴏᴜᴘs ({len(groups)}):</b>")
    if groups:
        for g in groups[:20]:
            lines.append(f"• <code>{g['chat_id']}</code> — {escape(str(g.get('group_name') or 'Unknown'))}")
        if len(groups) > 20:
            lines.append(f"<i>...and {len(groups) - 20} more</i>")
    else:
        lines.append("<i>None</i>")

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


application.add_handler(CommandHandler("banuser", banuser, block=False))
application.add_handler(CommandHandler("unbanuser", unbanuser, block=False))
application.add_handler(CommandHandler("bangroup", bangroup, block=False))
application.add_handler(CommandHandler("unbangroup", unbangroup, block=False))
application.add_handler(CommandHandler("bannedlist", bannedlist, block=False))