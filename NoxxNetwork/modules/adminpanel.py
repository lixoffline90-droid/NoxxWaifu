"""
Admin Panel — Interactive list with Rich UI banner.

Commands:
    /adminpanel      — Open the panel (Owner/Sudo only)
    /adminhelp       — Alias
    /commands        — Alias
"""
import os
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
)

from NoxxNetwork import (
    application,
    sudo_users,
    OWNER_ID,
    BOT_USERNAME,
    SUPPORT_CHAT,
    LOGGER,
)

# ─── Rich UI (optional) ───────────────────────────────────────
RICH_UI_OK = False
_rich_send = _rich_edit = None
_rich_esc = _rich_heading = None

try:
    from NoxxNetwork.rich_ui_decoded import (
        rich_send as _rich_send,
        rich_edit as _rich_edit,
        rich_esc as _rich_esc,
        rich_heading as _rich_heading,
    )
    RICH_UI_OK = True
    LOGGER.info("[adminpanel] rich_ui loaded ✅")
except Exception as _e:
    LOGGER.warning(f"[adminpanel] rich_ui unavailable: {_e}")

try:
    from NoxxNetwork import Waifuu as _Waifuu
except Exception:
    _Waifuu = None

PYRO_OK = _Waifuu is not None

# ─── Banner ───────────────────────────────────────────────────
BANNER_URL = os.getenv(
    "ADMIN_BANNER_URL",
    "https://i.postimg.cc/4xbpV50S/file-00000000598481f5b548a8852c1a0b63.png"
)


def _is_sudo(user_id: int) -> bool:
    return str(user_id) in (sudo_users or []) or user_id == OWNER_ID


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


# ══════════════════════════════════════════════════════════════
# CATEGORY DATA
# ══════════════════════════════════════════════════════════════
CATEGORIES = {
    "char": {
        "emoji": "🎴",
        "title": "CHARACTER MANAGEMENT",
        "access": "sudo",
        "items": [
            {"cmd": "/upload", "alias": None, "args": "<url> <name> <anime> <rarity>",
             "desc": "Add a new character"},
            {"cmd": "/update", "alias": None, "args": "<id> <field> <value>",
             "desc": "Edit a character's field"},
            {"cmd": "/delete", "alias": None, "args": "<id>",
             "desc": "Delete a character (DB + users + channel)"},
            {"cmd": "/resync", "alias": None, "args": "—",
             "desc": "Re-upload all chars to current channel"},
            {"cmd": "/setrarity", "alias": "setrarityprob", "args": "<id> <prob>",
             "desc": "Change a rarity's probability"},
            {"cmd": "/rarities", "alias": None, "args": "—",
             "desc": "Show all rarity probabilities"},
            {"cmd": "/charkill", "alias": None, "args": "<id> (reply)",
             "desc": "Remove a char from a user's harem"},
        ],
    },
    "spawn": {
        "emoji": "🎯",
        "title": "SPAWN CONTROL",
        "access": "sudo",
        "items": [
            {"cmd": "/spawn", "alias": None, "args": "<id> <freq> <Main/global>",
             "desc": "Set rarity spawn rate + scope"},
            {"cmd": "/changetime", "alias": "setchangetime", "args": "<num>",
             "desc": "Set group spawn frequency"},
        ],
    },
    "ban": {
        "emoji": "🚫",
        "title": "BAN SYSTEM",
        "access": "sudo",
        "items": [
            {"cmd": "/banuser", "alias": None, "args": "<id> or reply",
             "desc": "Ban a user"},
            {"cmd": "/unbanuser", "alias": None, "args": "<id> or reply",
             "desc": "Unban a user"},
            {"cmd": "/bangroup", "alias": None, "args": "<group_id>",
             "desc": "Ban a group"},
            {"cmd": "/unbangroup", "alias": None, "args": "<group_id>",
             "desc": "Unban a group"},
            {"cmd": "/bannedlist", "alias": None, "args": "—",
             "desc": "List all banned users/groups"},
        ],
    },
    "coins": {
        "emoji": "💰",
        "title": "COIN MANAGEMENT",
        "access": "sudo",
        "items": [
            {"cmd": "/wadd", "alias": "addcoins", "args": "<amount> (reply)",
             "desc": "Add coins to a user"},
            {"cmd": "/wremove", "alias": "removecoins", "args": "<amount> (reply)",
             "desc": "Remove coins from a user"},
        ],
    },
    "market": {
        "emoji": "🏪",
        "title": "MARKETPLACE MODERATION",
        "access": "sudo",
        "items": [
            {"cmd": "/marketstats", "alias": None, "args": "—",
             "desc": "View active, sold, cancelled, tax pot"},
            {"cmd": "/TransferHarem", "alias": "transferharem, tharem",
             "args": "<from_id> <to_id>", "desc": "Transfer full harem"},
        ],
    },
    "redeem": {
        "emoji": "🎁",
        "title": "REDEEM CODES",
        "access": "sudo",
        "items": [
            {"cmd": "/create_code", "alias": "createcode", "args": "<char_id> [max_uses]",
             "desc": "Create a redeem code"},
            {"cmd": "/codes", "alias": "codelist", "args": "—",
             "desc": "List active redeem codes"},
            {"cmd": "/delcode", "alias": None, "args": "<code>",
             "desc": "Delete a redeem code"},
        ],
    },
    "approval": {
        "emoji": "✅",
        "title": "APPROVAL SYSTEM",
        "access": "sudo",
        "items": [
            {"cmd": "/wallow", "alias": None, "args": "<id> or reply",
             "desc": "Give upload/update access"},
            {"cmd": "/wdeny", "alias": None, "args": "<id> or reply",
             "desc": "Revoke upload/update access"},
            {"cmd": "/approvedlist", "alias": None, "args": "—",
             "desc": "List all approved uploaders"},
        ],
    },
    "gift": {
        "emoji": "🎀",
        "title": "GIFT (SPECIAL POWERS)",
        "access": "sudo",
        "items": [
            {"cmd": "/gift", "alias": None, "args": "<id> (reply to self)",
             "desc": "Self-gift: add copy to your harem"},
            {"cmd": "/gift", "alias": None, "args": "<id> (reply to any)",
             "desc": "Gift any char (even if not owned)"},
        ],
    },
    "misc": {
        "emoji": "🛠",
        "title": "MISC / UTILITIES",
        "access": "sudo",
        "items": [
            {"cmd": "/ping", "alias": None, "args": "—",
             "desc": "Bot latency check"},
            {"cmd": "/list", "alias": None, "args": "—",
             "desc": "Download users list"},
            {"cmd": "/groups", "alias": None, "args": "—",
             "desc": "Download groups list"},
        ],
    },
    "owner": {
        "emoji": "👑",
        "title": "OWNER-ONLY",
        "access": "owner",
        "items": [
            {"cmd": "/broadcast", "alias": None, "args": "(reply)",
             "desc": "Broadcast to all groups/users"},
            {"cmd": "/stats", "alias": None, "args": "—",
             "desc": "Bot statistics"},
            {"cmd": "/e /ev /eva /eval", "alias": None, "args": "<code>",
             "desc": "Python eval (dev only)"},
            {"cmd": "/x /ex /exe /exec /py", "alias": None, "args": "<code>",
             "desc": "Python exec (dev only)"},
            {"cmd": "/clearlocals", "alias": None, "args": "—",
             "desc": "Clear eval namespaces"},
        ],
    },
}


# ══════════════════════════════════════════════════════════════
# BUILDERS
# ══════════════════════════════════════════════════════════════
def _esc(v) -> str:
    if v is None:
        return ""
    return escape(str(v))


def _mk_table(rows, headers=None):
    headers = headers or []
    parts = ['<table border="1">']
    if headers:
        parts.append("<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
    for r in rows:
        parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    parts.append("</table>")
    return "".join(parts)


# ─── PANEL HOME (HEADING FIRST → IMAGE SECOND) ────────────────
def build_panel_home(user_id: int) -> str:
    is_owner = _is_owner(user_id)
    role = "👑 Oᴡɴᴇʀ" if is_owner else "🛡️ Sᴜᴅᴏ"

    # Category table
    cat_table_rows = []
    for key, cat in CATEGORIES.items():
        if cat["access"] == "owner" and not is_owner:
            continue
        cat_table_rows.append([
            f"{cat['emoji']} {_esc(cat['title'])}",
            f"<b>{len(cat['items'])}</b>",
        ])
    cat_table = _mk_table(cat_table_rows, ["Category", "Cmds"])

    body = ""
    # 1. Heading FIRST
    body += f"<h1>🔐 ADMIN PANEL</h1>"
    # 2. Image SECOND
    if BANNER_URL:
        body += f'<img src="{_esc(BANNER_URL)}" />'
    # 3. Welcome blockquote
    body += (
        f"<blockquote>"
        f"👤 <b>Yᴏᴜʀ Rᴏʟᴇ:</b> {role}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
        f"Pick a category below to view its commands + aliases."
        f"</blockquote>"
    )
    # 4. Categories table
    body += f"<h3>📋 CATEGORIES</h3>"
    body += cat_table
    body += "<blockquote>💡 Click a button below to view commands</blockquote>"
    return body


# ─── CATEGORY VIEW (HEADING FIRST → IMAGE SECOND) ─────────────
def build_category_view(cat_key: str, user_id: int) -> str:
    cat = CATEGORIES.get(cat_key)
    if not cat:
        return "<h2>❌ Category not found</h2>"

    is_owner = _is_owner(user_id)
    if cat["access"] == "owner" and not is_owner:
        return "<h2>⛔ OWNER-ONLY</h2><blockquote>This section is restricted.</blockquote>"

    # Command table
    rows = []
    for item in cat["items"]:
        cmd = item["cmd"]
        alias = item.get("alias")
        args = item.get("args") or "—"
        desc = item.get("desc") or ""

        cmd_cell = f"<code>{_esc(cmd)}</code>"
        if args and args != "—":
            cmd_cell += f"\n<i>{_esc(args)}</i>"
        if alias:
            cmd_cell += f"\n🔀 <code>{_esc(alias)}</code>"
        rows.append([cmd_cell, _esc(desc)])

    table = _mk_table(rows, ["Command", "Description"])

    body = ""
    # 1. Heading FIRST
    body += f"<h1>{cat['emoji']} {cat['title']}</h1>"
    # 2. Image SECOND
    if BANNER_URL:
        body += f'<img src="{_esc(BANNER_URL)}" />'
    # 3. Info + table
    body += f"<blockquote>Total commands: <b>{len(cat['items'])}</b></blockquote>"
    body += table
    body += "<blockquote>🔙 Use the button below to go back.</blockquote>"
    return body


# ══════════════════════════════════════════════════════════════
# RICH SEND / EDIT
# ══════════════════════════════════════════════════════════════
def _plain(html_text: str) -> str:
    import re
    t = str(html_text)
    t = re.sub(r'<img\b[^>]*/?>', '', t, flags=re.I)
    t = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n<b>\1</b>\n', t, flags=re.I | re.S)
    t = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'\n\1\n', t, flags=re.I | re.S)
    t = re.sub(r'</t[dh]>', ' | ', t, flags=re.I)
    t = re.sub(r'</tr>', '\n', t, flags=re.I)
    t = re.sub(r'</?(?:table|thead|tbody|tr|th|td)[^>]*>', '', t, flags=re.I)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


async def _send_panel(update_or_query, html_text: str, *, kb=None, edit: bool = False):
    # ── Edit mode ──
    if edit and hasattr(update_or_query, 'message'):
        q = update_or_query
        chat_id = q.message.chat.id
        msg_id = q.message.message_id

        if RICH_UI_OK and PYRO_OK and _rich_edit is not None:
            try:
                result = await _rich_edit(
                    _Waifuu, html_text,
                    chat_id=chat_id, message_id=msg_id, reply_markup=kb,
                )
                if result:
                    return
            except Exception as e:
                LOGGER.warning(f"[adminpanel] rich edit failed: {e}")

        plain = _plain(html_text)
        try:
            if q.message.photo:
                await q.edit_message_caption(
                    caption=plain[:1024], reply_markup=kb, parse_mode='HTML',
                )
            else:
                await q.edit_message_text(plain, reply_markup=kb, parse_mode='HTML')
            return
        except Exception as e:
            LOGGER.warning(f"[adminpanel] edit fallback failed: {e}")
        return

    # ── Send mode ──
    update = update_or_query
    chat_id = update.effective_chat.id

    if RICH_UI_OK and PYRO_OK and _rich_send is not None:
        try:
            result = await _rich_send(_Waifuu, chat_id, html_text, reply_markup=kb)
            if result:
                return
        except Exception as e:
            LOGGER.warning(f"[adminpanel] rich send failed: {e}")

    plain = _plain(html_text)
    try:
        if len(plain) <= 1024:
            await update.message.reply_photo(
                photo=BANNER_URL, caption=plain, reply_markup=kb, parse_mode='HTML',
            )
        else:
            try:
                await update.message.reply_photo(photo=BANNER_URL)
            except Exception:
                pass
            await update.message.reply_text(plain, reply_markup=kb, parse_mode='HTML')
    except Exception:
        try:
            await update.message.reply_text(plain, reply_markup=kb, parse_mode='HTML')
        except Exception as e:
            LOGGER.error(f"[adminpanel] text fallback failed: {e}")


# ══════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════
def _panel_home_kb(user_id: int) -> InlineKeyboardMarkup:
    is_owner = _is_owner(user_id)

    keys = [
        ("char", "🎴 Cʜᴀʀᴀᴄᴛᴇʀ"),
        ("spawn", "🎯 Sᴘᴀᴡɴ"),
        ("ban", "🚫 Bᴀɴ"),
        ("coins", "💰 Cᴏɪɴs"),
        ("market", "🏪 Mᴀʀᴋᴇᴛ"),
        ("redeem", "🎁 Rᴇᴅᴇᴇᴍ"),
        ("approval", "✅ Aᴘᴘʀᴏᴠᴀʟ"),
        ("gift", "🎀 Gɪғᴛ"),
        ("misc", "🛠 Mɪsᴄ"),
    ]
    if is_owner:
        keys.append(("owner", "👑 Oᴡɴᴇʀ"))

    rows = []
    for i in range(0, len(keys), 2):
        pair = keys[i:i + 2]
        row = [
            InlineKeyboardButton(label, callback_data=f"apanel:cat:{key}")
            for key, label in pair
        ]
        rows.append(row)

    rows.append([
        InlineKeyboardButton("🌐 Sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}")
        if SUPPORT_CHAT else InlineKeyboardButton("❌ Cʟᴏsᴇ", callback_data="apanel:close")
    ])

    return InlineKeyboardMarkup(rows)


def _panel_cat_kb(cat_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀ Bᴀᴄᴋ ᴛᴏ Pᴀɴᴇʟ", callback_data="apanel:home")],
    ])


# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════
async def adminpanel(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not _is_sudo(user.id):
        await update.message.reply_text("⚠️ Aꜱᴋ Mʏ Oᴡɴᴇʀ...")
        return

    text = build_panel_home(user.id)
    kb = _panel_home_kb(user.id)
    await _send_panel(update, text, kb=kb)


async def adminpanel_callback(update: Update, context: CallbackContext) -> None:
    q = update.callback_query
    data = q.data or ""
    user_id = q.from_user.id

    if not _is_sudo(user_id):
        await q.answer("⚠️ You're not authorized.", show_alert=True)
        return

    await q.answer()

    try:
        if data == "apanel:close":
            try:
                await q.message.delete()
            except Exception:
                pass
            return

        if data == "apanel:home":
            text = build_panel_home(user_id)
            kb = _panel_home_kb(user_id)
            await _send_panel(q, text, kb=kb, edit=True)
            return

        if data.startswith("apanel:cat:"):
            cat_key = data.split(":", 2)[2]
            text = build_category_view(cat_key, user_id)
            kb = _panel_cat_kb(cat_key)
            await _send_panel(q, text, kb=kb, edit=True)
            return

    except Exception as e:
        LOGGER.exception(f"[adminpanel_callback] error: {e}")
        await q.answer("Something went wrong.", show_alert=True)


# ══════════════════════════════════════════════════════════════
# HANDLER REGISTRATION
# ══════════════════════════════════════════════════════════════
application.add_handler(
    CommandHandler(["adminpanel", "adminhelp", "commands"], adminpanel, block=False)
)
application.add_handler(
    CallbackQueryHandler(adminpanel_callback, pattern=r'^apanel:', block=False)
)
