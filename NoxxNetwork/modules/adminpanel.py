"""
Admin Panel — Interactive list with Rich UI banner.
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

# ─── Rich UI ──────────────────────────────────────────────────
RICH_UI_OK = False
_rich_send = _rich_edit = None
_rich_heading = _rich_note = _rich_table = _rich_code = None

try:
    from NoxxNetwork.rich_ui_decoded import (
        rich_send as _rich_send,
        rich_edit as _rich_edit,
        rich_heading as _rich_heading,
        rich_note as _rich_note,
        rich_table as _rich_table,
        rich_code as _rich_code,
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
# BUILDERS (Using rich_ui functions directly)
# ══════════════════════════════════════════════════════════════
def _esc(v) -> str:
    if v is None:
        return ""
    return escape(str(v))


def build_panel_home(user_id: int) -> str:
    is_owner = _is_owner(user_id)
    role = "👑 Oᴡɴᴇʀ" if is_owner else "🛡️ Sᴜᴅᴏ"

    cat_table_rows = []
    for key, cat in CATEGORIES.items():
        if cat["access"] == "owner" and not is_owner:
            continue
        cat_table_rows.append([
            f"{cat['emoji']} {cat['title']}",
            f"{len(cat['items'])}",
        ])
    
    # Use rich_table directly
    table = _rich_table(["Category", "Cmds"], cat_table_rows, border=1) if RICH_UI_OK else ""

    body = []
    # 1. Heading
    body.append(_rich_heading("🔐 ADMIN PANEL", 1) if RICH_UI_OK else "<h1>🔐 ADMIN PANEL</h1>")
    # 2. Image
    if BANNER_URL:
        body.append(f'<img src="{_esc(BANNER_URL)}" />')
    
    # 3. Info
    body.append(_rich_note(
        f"👤 <b>Yᴏᴜʀ Rᴏʟᴇ:</b> {role} | 🆔 <b>ID:</b> {_rich_code(user_id) if RICH_UI_OK else user_id}"
    ) if RICH_UI_OK else f"<blockquote>👤 <b>Yᴏᴜʀ Rᴏʟᴇ:</b> {role} | 🆔 <b>ID:</b> <code>{user_id}</code></blockquote>")
    
    # 4. Table
    body.append(_rich_heading("📋 CATEGORIES", 3) if RICH_UI_OK else "<h3>📋 CATEGORIES</h3>")
    body.append(table)
    
    # 5. Tip
    body.append(_rich_note("💡 Click a button below to view commands") if RICH_UI_OK else "<blockquote>💡 Click a button below to view commands</blockquote>")
    
    return "".join(body)


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
        
        cmd_str = f"{cmd} {args}".strip()
        rows.append([cmd_str, desc])

    table = _rich_table(["Command", "Description"], rows, border=1) if RICH_UI_OK else ""

    body = []
    # 1. Heading
    body.append(_rich_heading(f"{cat['emoji']} {cat['title']}", 1) if RICH_UI_OK else f"<h1>{cat['emoji']} {cat['title']}</h1>")
    # 2. Image
    if BANNER_URL:
        body.append(f'<img src="{_esc(BANNER_URL)}" />')
    # 3. Table
    body.append(_rich_note(f"Total commands: <b>{len(cat['items'])}</b>") if RICH_UI_OK else f"<blockquote>Total commands: <b>{len(cat['items'])}</b></blockquote>")
    body.append(table)
    body.append(_rich_note("🔙 Use the button below to go back.") if RICH_UI_OK else "<blockquote>🔙 Use the button below to go back.</blockquote>")

    return "".join(body)


# ══════════════════════════════════════════════════════════════
# SEND LOGIC
# ══════════════════════════════════════════════════════════════
async def _send(update_or_query, html_text: str, *, kb=None, edit: bool = False):
    if not (RICH_UI_OK and PYRO_OK):
        LOGGER.error("[adminpanel] Rich UI not available.")
        return

    if edit:
        q = update_or_query
        try:
            res = await _rich_edit(
                _Waifuu, html_text,
                chat_id=q.message.chat.id, message_id=q.message.message_id, 
                reply_markup=kb,
            )
            if res: return
        except Exception as e:
            LOGGER.error(f"[adminpanel] rich edit failed: {e}")
        return

    update = update_or_query
    try:
        res = await _rich_send(
            _Waifuu, update.effective_chat.id, html_text, reply_markup=kb
        )
        if res: return
    except Exception as e:
        LOGGER.error(f"[adminpanel] rich send failed: {e}")


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
