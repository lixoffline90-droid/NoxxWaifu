"""
Bot Added Notification — sends alert when the bot is added to a new group.

Uses PTB's ChatMemberHandler (my_chat_member updates) so it fires the moment
the bot's own membership status changes to "member" or "administrator" in
a new chat.
"""
from datetime import datetime, timezone, timedelta

from telegram import Update
from telegram.ext import (
    ChatMemberHandler,
    CommandHandler,
    CallbackContext,
)

from NoxxNetwork import (
    application,
    GROUP_ID,
    BOT_USERNAME,
    LOGGER,
)


# ─── IST timezone ─────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))


def _fmt_ist(ts: datetime | None = None) -> str:
    """Return 'DD-MM-YYYY HH:MM:SS AM/PM IST' for the given UTC datetime."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ist = ts.astimezone(IST)
    return ist.strftime("%d-%m-%Y %I:%M:%S %p IST")


def _escape(v) -> str:
    import html as _html
    if v is None:
        return ""
    return _html.escape(str(v), quote=False)


async def _get_group_link(context: CallbackContext, chat_id: int) -> str:
    """Best-effort public link for the group."""
    try:
        chat = await context.bot.get_chat(chat_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
        if chat.invite_link:
            return chat.invite_link
    except Exception:
        pass
    return "Private group — no public link available"


async def _get_member_count(context: CallbackContext, chat_id: int) -> str:
    try:
        count = await context.bot.get_chat_member_count(chat_id)
        return f"{count:,}"
    except Exception:
        return "Unknown"


async def _get_group_owner(context: CallbackContext, chat_id: int) -> str:
    """Best-effort group owner mention."""
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            status = str(getattr(admin, "status", "")).lower()
            if status == "creator":
                u = admin.user
                name = _escape(u.first_name or "Unknown")
                uname = f" (@{_escape(u.username)})" if u.username else ""
                return f"{name}{uname}"
    except Exception:
        pass
    return "Unknown"


# ─── Main handler ─────────────────────────────────────────────
async def bot_added_handler(update: Update, context: CallbackContext) -> None:
    """Fires when the bot's own chat member status changes."""
    try:
        mcm = update.my_chat_member
        if not mcm:
            return

        chat = mcm.chat
        # Only care about groups/supergroups
        if chat.type not in ("group", "supergroup"):
            return

        old_status = str(getattr(mcm.old_chat_member, "status", "")).lower()
        new_status = str(getattr(mcm.new_chat_member, "status", "")).lower()

        # We only care when bot becomes a member/admin for the first time
        was_absent = old_status in ("left", "kicked")
        is_present = new_status in ("member", "administrator", "creator")

        if not (was_absent and is_present):
            return

        # Who added the bot?
        added_by = mcm.from_user
        adder_name = _escape(added_by.first_name or "Unknown") if added_by else "Unknown"
        adder_id = added_by.id if added_by else 0
        adder_uname = f"@{_escape(added_by.username)}" if added_by and added_by.username else "—"

        # Gather group info
        group_name = _escape(chat.title or "Unknown Group")
        group_id = chat.id
        group_link = await _get_group_link(context, chat.id)
        members = await _get_member_count(context, chat.id)
        owner_str = await _get_group_owner(context, chat.id)
        time_str = _fmt_ist(mcm.date)

        # Build message
        text = (
            "🚨 <b>Bᴏᴛ Aᴅᴅᴇᴅ Tᴏ Nᴇᴡ Gʀᴏᴜᴘ</b>\n\n"
            f"🏠 <b>Gʀᴏᴜᴘ:</b> {group_name}\n"
            f"🆔 <b>Gʀᴏᴜᴘ Iᴅ:</b> <code>{group_id}</code>\n"
            f"🔗 <b>Gʀᴏᴜᴘ Lɪɴᴋ:</b> {_escape(group_link)}\n"
            f"👥 <b>Mᴇᴍʙᴇʀs:</b> {members}\n\n"
            f"➕ <b>Aᴅᴅᴇᴅ Bʏ:</b> {adder_name}\n"
            f"🆔 <b>Aᴅᴅᴇʀ Iᴅ:</b> <code>{adder_id}</code>\n"
            f"🔗 <b>Aᴅᴅᴇʀ:</b> {_escape(adder_uname)}\n\n"
            f"👑 <b>Gʀᴏᴜᴘ Oᴡɴᴇʀ:</b> {owner_str}\n"
            f"🕐 <b>Tɪᴍᴇ:</b> {time_str}"
        )

        # Send to main group (or OWNER_ID if GROUP_ID not set)
        target_chat = GROUP_ID
        if not target_chat:
            LOGGER.warning("[botadded] GROUP_ID not set — skipping notification")
            return

        try:
            await context.bot.send_message(
                chat_id=target_chat,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
            )
            LOGGER.info(f"[botadded] notified GROUP_ID about add to {group_id}")
        except Exception as e:
            LOGGER.warning(f"[botadded] failed to notify GROUP_ID: {e}")

        # Optional: Also try to send a welcome in the new group
        try:
            welcome = (
                f"🎉 <b>Tʜᴀɴᴋs ꜰᴏʀ ᴀᴅᴅɪɴɢ ᴍᴇ!</b>\n\n"
                f"Usᴇ <code>/help</code> ᴛᴏ sᴇᴇ ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅs.\n"
                f"Usᴇ <code>/start</code> ꜰᴏʀ ᴛʜᴇ ᴍᴀɪɴ ᴍᴇɴᴜ."
            )
            await context.bot.send_message(
                chat_id=chat.id,
                text=welcome,
                parse_mode='HTML',
            )
        except Exception as e:
            LOGGER.warning(f"[botadded] welcome to {chat.id} failed: {e}")

    except Exception as e:
        LOGGER.exception(f"[botadded] handler error: {e}")


# ─── Handler registration ─────────────────────────────────────
application.add_handler(
    ChatMemberHandler(bot_added_handler, ChatMemberHandler.MY_CHAT_MEMBER, block=False)
)
