"""
Start & Help — Rich UI with category-based help
"""
import random
import html as _html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from NoxxNetwork import (
    application,
    PHOTO_URL,
    SUPPORT_CHAT,
    UPDATE_CHAT,
    BOT_USERNAME,
    GROUP_ID,
    db,
    LOGGER,
)
from NoxxNetwork import pm_users as collection


# ══════════════════════════════════════════════════════════════
# Rich UI imports
# ══════════════════════════════════════════════════════════════
RICH_UI_OK = False
_rich_send = _rich_edit = None
_rich_esc = _rich_heading = _rich_table = _rich_note = None
_rich_details = None

try:
    from NoxxNetwork.rich_ui_decoded import (
        rich_send as _rich_send,
        rich_edit as _rich_edit,
        rich_esc as _rich_esc,
        rich_heading as _rich_heading,
        rich_table as _rich_table,
        rich_note as _rich_note,
        rich_details as _rich_details,
    )
    RICH_UI_OK = True
    LOGGER.info("[start] rich_ui loaded ✅")
except Exception as _e:
    LOGGER.warning(f"[start] rich_ui unavailable: {_e}")

try:
    from NoxxNetwork import Waifuu as _Waifuu
except Exception:
    _Waifuu = None

PYRO_OK = _Waifuu is not None


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════
def _esc(v) -> str:
    if v is None:
        return ""
    return _html.escape(str(v), quote=False)


def _rich_to_clean(html_text: str) -> str:
    """Convert rich HTML → plain HTML for PTB fallback."""
    import re
    t = str(html_text)
    t = re.sub(r'<img\b[^>]*/?>', '', t, flags=re.I)
    t = re.sub(r'<details[^>]*>', '\n', t, flags=re.I)
    t = re.sub(r'</details>', '', t, flags=re.I)
    t = re.sub(r'<summary[^>]*>(.*?)</summary>', r'\n<b>\1</b>\n', t, flags=re.I | re.S)
    t = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n<b>\1</b>\n', t, flags=re.I | re.S)
    t = re.sub(r'<tg-button[^>]*>(.*?)</tg-button>', r'\1', t, flags=re.I | re.S)
    t = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'\n\1\n', t, flags=re.I | re.S)

    def _table_sub(m):
        inner = m.group(1)
        rows_html = re.findall(r'<tr[^>]*>(.*?)</tr>', inner, re.I | re.S)
        lines = []
        for r in rows_html:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.I | re.S)
            header_check = [re.sub(r'<[^>]+>', '', c).lower().strip() for c in cells]
            if header_check and all(h in ('command', 'what it does', 'feature', 'details') for h in header_check):
                continue
            if len(cells) == 2:
                lines.append(f"  {cells[0].strip()}  →  {cells[1].strip()}")
            else:
                lines.append("  " + "  •  ".join(cells))
        return "\n" + "\n".join(lines) + "\n"

    t = re.sub(r'<table[^>]*>(.*?)</table>', _table_sub, t, flags=re.I | re.S)
    t = re.sub(r'</?(?:table|thead|tbody|tr|th|td)[^>]*>', '', t, flags=re.I)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'[ \t]+\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# ══════════════════════════════════════════════════════════════
# RICH SEND / EDIT
# ══════════════════════════════════════════════════════════════
async def _send_rich(update_or_query, html_text: str, *, kb=None, edit: bool = False):
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
                LOGGER.warning(f"[start] rich edit failed: {e}")

        plain = _rich_to_clean(html_text)
        try:
            if q.message.photo:
                await q.edit_message_caption(
                    caption=plain[:1024], reply_markup=kb, parse_mode='HTML',
                )
            else:
                await q.edit_message_text(plain, reply_markup=kb, parse_mode='HTML')
            return
        except Exception as e:
            LOGGER.warning(f"[start] edit fallback failed: {e}")
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
            LOGGER.warning(f"[start] rich send failed: {e}")

    plain = _rich_to_clean(html_text)
    try:
        photo_url = random.choice(PHOTO_URL)
        if len(plain) <= 1024:
            await update.message.reply_photo(
                photo=photo_url, caption=plain, reply_markup=kb, parse_mode='HTML',
            )
        else:
            try:
                await update.message.reply_photo(photo=photo_url)
            except Exception:
                pass
            await update.message.reply_text(plain, reply_markup=kb, parse_mode='HTML')
    except Exception:
        try:
            await update.message.reply_text(plain, reply_markup=kb, parse_mode='HTML')
        except Exception as e:
            LOGGER.error(f"[start] text fallback failed: {e}")


# ══════════════════════════════════════════════════════════════
# CATEGORY DATA
# ══════════════════════════════════════════════════════════════
CATEGORIES = {
    "catch": {
        "emoji": "🌸",
        "title": "CATCH & COLLECT",
        "rows": [
            ["/guess", "Catch the waifu in a group"],
            ["/grab /hunt /collect", "Aliases for /guess"],
            ["/fav &lt;id&gt;", "Mark a character as favorite"],
            ["/harem", "View your collection"],
            ["/profile", "View your profile card"],
            ["/w &lt;id&gt;", "Look up a character"],
            ["/find &lt;id&gt;", "See who owns a character"],
            ["/wrarity", "Collection breakdown by rarity"],
        ],
    },
    "market": {
        "emoji": "🏪",
        "title": "MARKETPLACE",
        "rows": [
            ["/market [search]", "Browse listings (search by name/id)"],
            ["/sellwaifu &lt;id&gt; &lt;price&gt;", "List a waifu for sale"],
            ["/wbuy &lt;listing_id&gt;", "Buy a listed waifu"],
            ["/cancelsell &lt;listing_id&gt;", "Cancel your listing"],
            ["/mylistings", "See your active listings"],
        ],
    },
    "trade": {
        "emoji": "💌",
        "title": "TRADE & GIFT",
        "rows": [
            ["/trade &lt;yours&gt; &lt;theirs&gt;", "Trade waifus (reply to user)"],
            ["/gift &lt;id&gt;", "Gift a waifu (reply to user)"],
        ],
    },
    "economy": {
        "emoji": "🪙",
        "title": "ECONOMY & COINS",
        "rows": [
            ["/ball 🎳", "Play bowling, win Edollers"],
            ["/wpocket", "Check balance & balls left"],
            ["/wsend &lt;amount&gt;", "Send Edollers to a user"],
            ["/wtop", "Top Edollers holders"],
        ],
    },
    "style": {
        "emoji": "🎨",
        "title": "CUSTOMIZATION",
        "rows": [
            ["/whmode", "Set harem mode (Default/Rarity/Char/Anime)"],
            ["/whfav &lt;id&gt;", "Show only one character in harem"],
            ["/whstyle", "Change harem display style"],
        ],
    },
    "top": {
        "emoji": "🏆",
        "title": "LEADERBOARDS & STATS",
        "rows": [
            ["/top", "Top waifu collectors"],
            ["/ctop", "Chat leaderboard"],
            ["/topgroups", "Top groups"],
            ["/stats", "Bot statistics"],
        ],
    },
    "admin": {
        "emoji": "⚙️",
        "title": "GROUP TOOLS",
        "rows": [
            ["/changetime &lt;num&gt;", "Set spawn frequency (admin)"],
            ["/spawn &lt;id&gt; &lt;freq&gt; &lt;scope&gt;", "Control rarity spawn (sudo)"],
            ["/broadcast", "Broadcast to all users (owner)"],
            ["/banuser /unbanuser", "Ban/unban user (sudo)"],
            ["/bangroup /unbangroup", "Ban/unban group (sudo)"],
            ["/bannedlist", "List banned users/groups (sudo)"],
        ],
    },
    "redeem": {
        "emoji": "🎁",
        "title": "REDEEM CODES",
        "rows": [
            ["/redeem &lt;code&gt;", "Redeem a code to get a character"],
        ],
    },
}


# ══════════════════════════════════════════════════════════════
# BUILDERS
# ══════════════════════════════════════════════════════════════
def _banner_url() -> str:
    try:
        return random.choice(PHOTO_URL)
    except Exception:
        return ""


def _mk_table(rows, headers=None):
    """Build a table for commands (rich if available, else HTML)."""
    headers = headers or ["Command", "What it does"]
    if RICH_UI_OK and _rich_table:
        try:
            return _rich_table(headers, rows, border=1)
        except Exception:
            pass
    parts = ['<table border="1">']
    parts.append("<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
    for r in rows:
        parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    parts.append("</table>")
    return "".join(parts)


def build_start_html(first_name: str) -> str:
    banner = _banner_url()
    name = _esc(first_name or 'User')

    features = [
        ["🎴 Catch",        "Spawn & grab waifus in groups"],
        ["🏪 Marketplace",  "Buy & sell characters for Edollers"],
        ["🎁 Trade",        "Trade / gift waifus with friends"],
        ["🎳 /ball",        "Earn Edollers daily"],
        ["🎨 Harem Mode",   "Filter & customize your harem"],
    ]
    table = _mk_table(features, headers=["Feature", "Details"])

    why_choose = (
        "⭐ Simple slash commands, no setup needed.\n"
        "🎯 Auto-catching, trade, marketplace & coin economy.\n"
        "🎨 Fully customizable harem modes & styles.\n"
        "🌐 Click <b>HELP</b> below for all commands."
    )

    body = ""
    if banner:
        body += f'<img src="{_esc(banner)}" />'
    body += f"<h2>HEY {name}, WELCOME ABOARD! 🎵</h2>"
    body += (
        "<blockquote>"
        "I AM <b>WAIFU CATCHER</b> — A POWERFUL TELEGRAM BOT "
        "THAT BRINGS ANIME WAIFUS TO YOUR GROUP. 🎴"
        "</blockquote>"
    )

    if _rich_details:
        body += f"<details open><summary>✨ KEY FEATURES ✨</summary>{table}</details>"
        body += f"<details><summary>⚡ WHY CHOOSE IT? ⚡</summary>{why_choose}</details>"
    else:
        body += f"\n<b>✨ KEY FEATURES ✨</b>\n{table}"
        body += f"\n<b>⚡ WHY CHOOSE IT? ⚡</b>\n{why_choose}"

    body += "<blockquote>POWERED BY » <b>WAIFU CATCHER</b></blockquote>"
    return body


def build_help_menu_html(first_name: str) -> str:
    """Help home page — pick a category."""
    banner = _banner_url()
    name = _esc(first_name or 'User')

    info_rows = [
        ["📋 Help Menu", "All commands can be used with: /"],
        ["🎴 Categories", "Pick a category below"],
    ]
    info_table = _mk_table(info_rows, headers=["Feature", "Details"])

    body = ""
    if banner:
        body += f'<img src="{_esc(banner)}" />'
    body += f"<h3>📜 CHOOSE A CATEGORY</h3>"
    body += (
        f"<blockquote>Hey {name}, pick a category below to see its commands.</blockquote>"
    )

    if _rich_details:
        body += f"<details open><summary>✨ HELP FEATURES ✨</summary>{info_table}</details>"
    else:
        body += f"\n<b>✨ HELP FEATURES ✨</b>\n{info_table}"

    body += "<blockquote>POWERED BY » <b>WAIFU CATCHER</b></blockquote>"
    return body


def build_category_html(cat_key: str, first_name: str) -> str:
    """Category page — commands table."""
    cat = CATEGORIES.get(cat_key)
    if not cat:
        return build_help_menu_html(first_name)

    name = _esc(first_name or 'User')
    emoji = cat["emoji"]
    title = cat["title"]
    rows = cat["rows"]
    table = _mk_table(rows)

    body = (
        f"<h3>{emoji} {title}</h3>"
        f"<blockquote>Hey {name}, here are all commands in this category.</blockquote>"
    )

    if _rich_details:
        body += f"<details open><summary>📋 COMMANDS</summary>{table}</details>"
    else:
        body += f"\n<b>📋 COMMANDS</b>\n{table}"

    body += "<blockquote>🔙 Use the buttons below to navigate.</blockquote>"
    return body


# ══════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════
def _start_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛩ Aᴅᴅ Mᴇ ⛩", url=f"https://t.me/{BOT_USERNAME}?startgroup=new")],
        [
            InlineKeyboardButton("✦ Sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}"),
            InlineKeyboardButton("✧ Uᴘᴅᴀᴛᴇs", url=f"https://t.me/{UPDATE_CHAT}"),
        ],
        [InlineKeyboardButton("❖ Hᴇʟᴘ & Cᴏᴍᴍᴀɴᴅs", callback_data="help")],
    ])


def _help_menu_kb() -> InlineKeyboardMarkup:
    """Help menu — grid of category buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌸 CATCH", callback_data="help:cat:catch"),
            InlineKeyboardButton("🏪 MARKET", callback_data="help:cat:market"),
            InlineKeyboardButton("💌 TRADE", callback_data="help:cat:trade"),
        ],
        [
            InlineKeyboardButton("🪙 ECONOMY", callback_data="help:cat:economy"),
            InlineKeyboardButton("🎨 STYLE", callback_data="help:cat:style"),
            InlineKeyboardButton("🏆 TOP", callback_data="help:cat:top"),
        ],
        [
            InlineKeyboardButton("⚙️ ADMIN", callback_data="help:cat:admin"),
            InlineKeyboardButton("🎁 REDEEM", callback_data="help:cat:redeem"),
        ],
        [InlineKeyboardButton("⤾ Bᴀᴄᴋ Tᴏ Hᴏᴍᴇ", callback_data="back")],
    ])


def _category_kb(cat_key: str) -> InlineKeyboardMarkup:
    """Back button within category view."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀ Bᴀᴄᴋ Tᴏ Cᴀᴛᴇɢᴏʀɪᴇs", callback_data="help:home")],
    ])


# ══════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════
async def start(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or 'User'
    username = update.effective_user.username

    try:
        user_data = await collection.find_one({"_id": user_id})
        if user_data is None:
            await collection.insert_one(
                {"_id": user_id, "first_name": first_name, "username": username}
            )
            try:
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=(
                        f"New user Started The Bot..\n"
                        f"User: <a href='tg://user?id={user_id}'>{_esc(first_name)}</a>"
                    ),
                    parse_mode='HTML',
                )
            except Exception as e:
                LOGGER.warning(f"[start] group notify failed: {e}")
        else:
            if user_data.get('first_name') != first_name or user_data.get('username') != username:
                await collection.update_one(
                    {"_id": user_id},
                    {"$set": {"first_name": first_name, "username": username}},
                )
    except Exception as e:
        LOGGER.warning(f"[start] user tracking failed: {e}")

    if update.effective_chat.type == "private":
        await _send_rich(update, build_start_html(first_name), kb=_start_kb())
        return

    html_text = (
        f"<h3>🎴 WAIFU CATCHER</h3>"
        f"<blockquote>Alive! Connect to me in PM for more information.</blockquote>"
    )
    await _send_rich(update, html_text, kb=_start_kb())


# ══════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    first_name = query.from_user.first_name or 'User'

    try:
        # ── Main help menu ──
        if data in ('help', 'help:home'):
            await _send_rich(
                query,
                build_help_menu_html(first_name),
                kb=_help_menu_kb(),
                edit=True,
            )
            return

        # ── Category view ──
        if data.startswith("help:cat:"):
            cat_key = data.split(":", 2)[2]
            if cat_key not in CATEGORIES:
                await query.answer("Unknown category.", show_alert=True)
                return
            await _send_rich(
                query,
                build_category_html(cat_key, first_name),
                kb=_category_kb(cat_key),
                edit=True,
            )
            return

        # ── Back to start ──
        if data == 'back':
            await _send_rich(
                query,
                build_start_html(first_name),
                kb=_start_kb(),
                edit=True,
            )
            return

    except Exception as e:
        LOGGER.exception(f"[start.button] error: {e}")


# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════
application.add_handler(
    CallbackQueryHandler(button, pattern=r'^(help$|help:|back$)', block=False)
)
application.add_handler(CommandHandler('start', start, block=False))
