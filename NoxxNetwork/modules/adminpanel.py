"""
Admin Panel — Interactive list with Rich UI (Fixed Fallback)
"""
import os
import re
import html as _html

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

# ─── Rich UI ──────────────────────────────────────────────────
RICH_UI_OK = False
_rich_send = _rich_edit = None

try:
    from NoxxNetwork.rich_ui_decoded import (
        rich_send as _rich_send,
        rich_edit as _rich_edit,
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

BANNER_URL = os.getenv(
    "ADMIN_BANNER_URL",
    "https://i.ibb.co/tFnrhjh/843803f5a80f.jpg"
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
            {"cmd": "/upload", "args": "<url> <name> <anime> <rarity>", "desc": "Add a new character"},
            {"cmd": "/update", "args": "<id> <field> <value>", "desc": "Edit a character's field"},
            {"cmd": "/delete", "args": "<id>", "desc": "Delete a character"},
            {"cmd": "/resync", "args": "", "desc": "Re-upload all chars to channel"},
            {"cmd": "/setrarity", "args": "<id> <prob>", "desc": "Change a rarity's probability"},
            {"cmd": "/rarities", "args": "", "desc": "Show all rarity probabilities"},
            {"cmd": "/charkill", "args": "<id> (reply)", "desc": "Remove char from user's harem"},
        ],
    },
    "spawn": {
        "emoji": "🎯",
        "title": "SPAWN CONTROL",
        "access": "sudo",
        "items": [
            {"cmd": "/spawn", "args": "<id> <freq> <Main/global>", "desc": "Set rarity spawn rate"},
            {"cmd": "/changetime", "args": "<num>", "desc": "Set group spawn frequency"},
        ],
    },
    "ban": {
        "emoji": "🚫",
        "title": "BAN SYSTEM",
        "access": "sudo",
        "items": [
            {"cmd": "/banuser", "args": "<id> or reply", "desc": "Ban a user"},
            {"cmd": "/unbanuser", "args": "<id> or reply", "desc": "Unban a user"},
            {"cmd": "/bangroup", "args": "<group_id>", "desc": "Ban a group"},
            {"cmd": "/unbangroup", "args": "<group_id>", "desc": "Unban a group"},
            {"cmd": "/bannedlist", "args": "", "desc": "List all banned users/groups"},
        ],
    },
    "coins": {
        "emoji": "💰",
        "title": "COIN MANAGEMENT",
        "access": "sudo",
        "items": [
            {"cmd": "/wadd", "args": "<amount> (reply)", "desc": "Add coins to user"},
            {"cmd": "/wremove", "args": "<amount> (reply)", "desc": "Remove coins from user"},
        ],
    },
    "market": {
        "emoji": "🏪",
        "title": "MARKETPLACE MODERATION",
        "access": "sudo",
        "items": [
            {"cmd": "/marketstats", "args": "", "desc": "View market stats"},
            {"cmd": "/TransferHarem", "args": "<from_id> <to_id>", "desc": "Transfer full harem"},
        ],
    },
    "redeem": {
        "emoji": "🎁",
        "title": "REDEEM CODES",
        "access": "sudo",
        "items": [
            {"cmd": "/create_code", "args": "<char_id> [max_uses]", "desc": "Create a redeem code"},
            {"cmd": "/codes", "args": "", "desc": "List active redeem codes"},
            {"cmd": "/delcode", "args": "<code>", "desc": "Delete a redeem code"},
        ],
    },
    "approval": {
        "emoji": "✅",
        "title": "APPROVAL SYSTEM",
        "access": "sudo",
        "items": [
            {"cmd": "/wallow", "args": "<id> or reply", "desc": "Give upload access"},
            {"cmd": "/wdeny", "args": "<id> or reply", "desc": "Revoke upload access"},
            {"cmd": "/approvedlist", "args": "", "desc": "List approved uploaders"},
        ],
    },
    "gift": {
        "emoji": "🎀",
        "title": "GIFT (SPECIAL POWERS)",
        "access": "sudo",
        "items": [
            {"cmd": "/gift", "args": "<id> (reply to self)", "desc": "Self-gift: add copy to harem"},
            {"cmd": "/gift", "args": "<id> (reply to any)", "desc": "Gift any char"},
        ],
    },
    "misc": {
        "emoji": "🛠",
        "title": "MISC / UTILITIES",
        "access": "sudo",
        "items": [
            {"cmd": "/ping", "args": "", "desc": "Bot latency check"},
            {"cmd": "/list", "args": "", "desc": "Download users list"},
            {"cmd": "/groups", "args": "", "desc": "Download groups list"},
        ],
    },
    "owner": {
        "emoji": "👑",
        "title": "OWNER-ONLY",
        "access": "owner",
        "items": [
            {"cmd": "/broadcast", "args": "(reply)", "desc": "Broadcast to all"},
            {"cmd": "/stats", "args": "", "desc": "Bot statistics"},
            {"cmd": "/e /ev /eval", "args": "<code>", "desc": "Python eval"},
            {"cmd": "/x /ex /exec", "args": "<code>", "desc": "Python exec"},
            {"cmd": "/clearlocals", "args": "", "desc": "Clear eval namespaces"},
        ],
    },
}


# ══════════════════════════════════════════════════════════════
# BUILDERS
# ══════════════════════════════════════════════════════════════
def _esc(v) -> str:
    if v is None:
        return ""
    return _html.escape(str(v), quote=False)


def _mk_table(headers, rows):
    parts = ['<table border="1">']
    parts.append("<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
    for r in rows:
        parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    parts.append("</table>")
    return "".join(parts)


def build_panel_home(user_id: int) -> str:
    is_owner = _is_owner(user_id)
    role = "👑 Oᴡɴᴇʀ" if is_owner else "🛡️ Sᴜᴅᴏ"

    cat_table_rows = []
    for key, cat in CATEGORIES.items():
        if cat["access"] == "owner" and not is_owner:
            continue
        cat_table_rows.append([
            f"{cat['emoji']} {_esc(cat['title'])}",
            f"<b>{len(cat['items'])}</b>",
        ])
    
    table = _mk_table(["Category", "Cmds"], cat_table_rows)

    body = ""
    body += f"<h1>🔐 ADMIN PANEL</h1>"
    if BANNER_URL:
        body += f'<img src="{_esc(BANNER_URL)}" />'
    
    body += (
        f"<blockquote>"
        f"👤 <b>Yᴏᴜʀ Rᴏʟᴇ:</b> {role}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>"
        f"</blockquote>"
    )
    body += f"<h3>📋 CATEGORIES</h3>"
    body += table
    body += "<blockquote>💡 Click a button below to view commands</blockquote>"
    return body


def build_category_view(cat_key: str, user_id: int) -> str:
    cat = CATEGORIES.get(cat_key)
    if not cat:
        return "<h2>❌ Category not found</h2>"

    is_owner = _is_owner(user_id)
    if cat["access"] == "owner" and not is_owner:
        return "<h2>⛔ OWNER-ONLY</h2><blockquote>This section is restricted.</blockquote>"

    rows = []
    for item in cat["items"]:
        cmd = item["cmd"]
        args = item.get("args") or ""
        desc = item.get("desc") or ""

        cmd_str = f"{_esc(cmd)} {_esc(args)}".strip()
        rows.append([cmd_str, _esc(desc)])

    table = _mk_table(["Command", "Description"], rows)

    body = ""
    body += f"<h1>{cat['emoji']} {cat['title']}</h1>"
    if BANNER_URL:
        body += f'<img src="{_esc(BANNER_URL)}" />'
    body += f"<blockquote>Total commands: <b>{len(cat['items'])}</b></blockquote>"
    body += table
    body += "<blockquote>🔙 Use the button below to go back.</blockquote>"
    return body


# ══════════════════════════════════════════════════════════════
# PLAIN FALLBACK (Fixes the <table> crash)
# ══════════════════════════════════════════════════════════════
def _plain_fallback(html_text: str) -> str:
    t = str(html_text)
    t = re.sub(r'<img\b[^>]*/?>', '', t, flags=re.I)
    t = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n<b>\1</b>\n', t, flags=re.I|re.S)
    t = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'\n\1\n', t, flags=re.I|re.S)
    
    # Convert table to pipes
    t = re.sub(r'</t[dh]>', ' | ', t, flags=re.I)
    t = re.sub(r'</tr>', '\n', t, flags=re.I)
    t = re.sub(r'</?(?:table|thead|tbody|tr|th|td)[^>]*>', '', t, flags=re.I)
    
    t = re.sub(r'\s*\|\s*\n', '\n', t)
    t = re.sub(r'\|\s*$', '', t, flags=re.M)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# ══════════════════════════════════════════════════════════════
# SEND LOGIC
# ══════════════════════════════════════════════════════════════
async def _send(update_or_query, html_text: str, *, kb=None, edit: bool = False):
    if edit:
        q = update_or_query
        # Try rich edit
        if RICH_UI_OK and PYRO_OK and _rich_edit:
            try:
                res = await _rich_edit(_Waifuu, html_text, chat_id=q.message.chat.id, message_id=q.message.message_id, reply_markup=kb)
                if res: return
            except Exception as e:
                LOGGER.warning(f"[adminpanel] rich edit failed: {e}")
                
        # Fallback
        try:
            await q.edit_message_text(_plain_fallback(html_text), reply_markup=kb, parse_mode='HTML')
        except Exception as e:
            LOGGER.error(f"[adminpanel] fallback edit failed: {e}")
        return

    update = update_or_query
    chat_id = update.effective_chat.id

    # Try rich send
    if RICH_UI_OK and PYRO_OK and _rich_send:
        try:
            res = await _rich_send(_Waifuu, chat_id, html_text, reply_markup=kb)
            if res: return
        except Exception as e:
            LOGGER.warning(f"[adminpanel] rich send failed: {e}")

    # Fallback (PTB)
    try:
        await update.message.reply_text(_plain_fallback(html_text), reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        LOGGER.error(f"[adminpanel] fallback send failed: {e}")
        # Ultimate fallback without HTML tags
        try:
            clean_text = re.sub(r'<[^>]+>', '', html_text)
            await update.message.reply_text(clean_text, reply_markup=kb)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# KEYBOARDS & HANDLERS
# ══════════════════════════════════════════════════════════════
def _panel_home_kb(user_id: int) -> InlineKeyboardMarkup:
    is_owner = _is_owner(user_id)
    keys = [
        ("char", "🎴 Cʜᴀʀᴀᴄᴛᴇʀ"), ("spawn", "🎯 Sᴘᴀᴡɴ"),
        ("ban", "🚫 Bᴀɴ"), ("coins", "💰 Cᴏɪɴs"),
        ("market", "🏪 Mᴀʀᴋᴇᴛ"), ("redeem", "🎁 Rᴇᴅᴇᴇᴍ"),
        ("approval", "✅ Aᴘᴘʀᴏᴠᴀʟ"), ("gift", "🎀 Gɪғᴛ"),
        ("misc", "🛠 Mɪsᴄ"),
    ]
    if is_owner:
        keys.append(("owner", "👑 Oᴡɴᴇʀ"))

    rows = []
    for i in range(0, len(keys), 2):
        pair = keys[i:i + 2]
        rows.append([InlineKeyboardButton(label, callback_data=f"apanel:cat:{key}") for key, label in pair])

    rows.append([
        InlineKeyboardButton("🌐 Sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}") if SUPPORT_CHAT else InlineKeyboardButton("❌ Cʟᴏsᴇ", callback_data="apanel:close")
    ])
    return InlineKeyboardMarkup(rows)

def _panel_cat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀ Bᴀᴄᴋ ᴛᴏ Pᴀɴᴇʟ", callback_data="apanel:home")]])


async def adminpanel(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not _is_sudo(user.id):
        await update.message.reply_text("⚠️ Aꜱᴋ Mʏ Oᴡɴᴇʀ...")
        return
    await _send(update, build_panel_home(user.id), kb=_panel_home_kb(user.id))


async def adminpanel_callback(update: Update, context: CallbackContext) -> None:
    q = update.callback_query
    await q.answer()
    
    if not _is_sudo(q.from_user.id):
        await q.answer("⚠️ You're not authorized.", show_alert=True)
        return

    data = q.data or ""
    if data == "apanel:close":
        try: await q.message.delete()
        except: pass
        return

    if data == "apanel:home":
        await _send(q, build_panel_home(q.from_user.id), kb=_panel_home_kb(q.from_user.id), edit=True)
        return

    if data.startswith("apanel:cat:"):
        cat_key = data.split(":", 2)[2]
        await _send(q, build_category_view(cat_key, q.from_user.id), kb=_panel_cat_kb(), edit=True)
        return


application.add_handler(CommandHandler(["adminpanel", "adminhelp", "commands"], adminpanel, block=False))
application.add_handler(CallbackQueryHandler(adminpanel_callback, pattern=r'^apanel:', block=False))
