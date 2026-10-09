"""
Start & Help — Rich UI
"""
import random
import html as _html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CallbackQueryHandler, CommandHandler

from NoxxNetwork import (
    application, PHOTO_URL, SUPPORT_CHAT, UPDATE_CHAT, BOT_USERNAME,
    GROUP_ID, db, LOGGER,
)
from NoxxNetwork import pm_users as collection


# ══════════════════════════════════════════════════════════════
# Rich UI imports (optional)
# ══════════════════════════════════════════════════════════════
RICH_UI_OK = False
_rich_send = _rich_edit = None
_rich_esc = _rich_heading = _rich_table = _rich_note = _rich_code = None
_rich_details = None

try:
    from NoxxNetwork.rich_ui_decoded import (
        rich_send as _rich_send,
        rich_edit as _rich_edit,
        rich_esc as _rich_esc,
        rich_heading as _rich_heading,
        rich_table as _rich_table,
        rich_note as _rich_note,
        rich_code as _rich_code,
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


def _strip_html(s: str) -> str:
    import re
    return re.sub(r'<[^>]+>', '', str(s))


def _rich_to_clean(html_text: str) -> str:
    """Convert rich HTML → plain HTML for PTB fallback.
    Collapses <details> to always-shown, keeps <b>, <code>, <blockquote>."""
    import re
    t = str(html_text)

    # Remove <img>
    t = re.sub(r'<img\b[^>]*/?>', '', t, flags=re.I)
    # Collapse <details> to inline content (show summary + body)
    t = re.sub(r'<details[^>]*>', '', t, flags=re.I)
    t = re.sub(r'</details>', '', t, flags=re.I)
    t = re.sub(r'<summary[^>]*>(.*?)</summary>', r'\n<b>\1</b>\n', t, flags=re.I | re.S)
    # Headings → bold
    t = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n<b>\1</b>\n', t, flags=re.I | re.S)
    # tg-button → text only
    t = re.sub(r'<tg-button[^>]*>(.*?)</tg-button>', r'\1', t, flags=re.I | re.S)
    # blockquote → plain
    t = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', r'\n\1\n', t, flags=re.I | re.S)
    # Tables → ASCII (very rough fallback)
    def _table_sub(m):
        inner = m.group(1)
        rows_html = re.findall(r'<tr[^>]*>(.*?)</tr>', inner, re.I | re.S)
        lines = []
        for r in rows_html:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.I | re.S)
            lines.append(" • ".join(_strip_html(c) for c in cells))
        return "\n" + "\n".join(lines) + "\n"
    t = re.sub(r'<table[^>]*>(.*?)</table>', _table_sub, t, flags=re.I | re.S)
    t = re.sub(r'</?(?:table|thead|tbody|tr|th|td)[^>]*>', '', t, flags=re.I)
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'[ \t]+\n', '\n', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# ══════════════════════════════════════════════════════════════
# RICH SEND
# ══════════════════════════════════════════════════════════════
async def _send_rich(update_or_query, html_text: str, *, kb=None, edit: bool = False):
    """Send rich message. Falls back to PTB if rich fails."""
    # Edit mode
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

        # PTB fallback (edit caption)
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

    # Send mode
    update = update_or_query
    chat_id = update.effective_chat.id

    if RICH_UI_OK and PYRO_OK and _rich_send is not None:
        try:
            result = await _rich_send(_Waifuu, chat_id, html_text, reply_markup=kb)
            if result:
                return
        except Exception as e:
            LOGGER.warning(f"[start] rich send failed: {e}")

    # PTB fallback
    plain = _rich_to_clean(html_text)
    try:
        photo_url = random.choice(PHOTO_URL)
        await update.message.reply_photo(
            photo=photo_url,
            caption=plain[:1024],
            reply_markup=kb,
            parse_mode='HTML',
        )
    except Exception:
        try:
            await update.message.reply_text(plain, reply_markup=kb, parse_mode='HTML')
        except Exception as e:
            LOGGER.error(f"[start] text fallback failed: {e}")


# ══════════════════════════════════════════════════════════════
# HTML BUILDERS
# ══════════════════════════════════════════════════════════════
def _banner_url() -> str:
    try:
        return random.choice(PHOTO_URL)
    except Exception:
        return ""


def build_start_html(first_name: str) -> str:
    banner = _banner_url()
    name = _esc(first_name or 'User')

    # Key features table
    features = [
        ["🎴 Catch", "Spawn & grab waifus in groups"],
        ["🏪 Marketplace", "Buy & sell characters for Edollers"],
        ["🎁 Trade", "Trade / gift waifus with friends"],
        ["🎳 /ball", "Earn Edollers daily"],
        ["🎨 Harem Mode", "Filter & customize your harem"],
    ]
    table = _rich_table(["Feature", "Details"], features, border=1) if RICH_UI_OK and _rich_table else ""

    why_choose = (
        "⭐ Simple slash commands, no setup needed.\n"
        "🎯 Auto-catching, trade, marketplace & coin economy.\n"
        "🎨 Fully customizable harem modes & styles.\n"
        "🌐 Click <b>HELP</b> below for all commands."
    )

    html_text = (
        (f'<img src="{banner}" />' if banner else '')
        + f"<h2>HEY {name}, WELCOME ABOARD! 🎵</h2>"
        + "<blockquote>"
        + "I AM <b>WAIFU CATCHER</b> — A POWERFUL TELEGRAM BOT "
        + "THAT BRINGS ANIME WAIFUS TO YOUR GROUP. 🎴"
        + "</blockquote>"
        + (
            f"<details open><summary>✨ KEY FEATURES ✨</summary>{table}</details>"
            if (_rich_details and table) else
            f"<b>✨ KEY FEATURES ✨</b>\n{table}"
        )
        + (
            f"<details><summary>⚡ WHY CHOOSE IT? ⚡</summary>{why_choose}</details>"
            if _rich_details else
            f"\n<b>⚡ WHY CHOOSE IT? ⚡</b>\n{why_choose}"
        )
        + f"<blockquote>POWERED BY » <b>WAIFU CATCHER</b></blockquote>"
    )
    return html_text


def build_help_html(first_name: str) -> str:
    name = _esc(first_name or 'User')

    # ─── Catch & Collect ────────────────────────────────────────
    catch_rows = [
        ["/guess", "Catch the waifu in a group"],
        ["/grab /hunt /collect", "Aliases for /guess"],
        ["/fav &lt;id&gt;", "Mark a character as favorite"],
        ["/harem", "View your collection"],
        ["/profile", "View your profile card"],
        ["/w &lt;id&gt;", "Look up a character"],
        ["/find &lt;id&gt;", "See who owns a character"],
    ]
    catch_tbl = _rich_table(["Command", "What it does"], catch_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Marketplace ────────────────────────────────────────────
    market_rows = [
        ["/market [search]", "Browse listings (search by name/id)"],
        ["/sellwaifu &lt;id&gt; &lt;price&gt;", "List a waifu for sale"],
        ["/wbuy &lt;listing_id&gt;", "Buy a listed waifu"],
        ["/cancelsell &lt;listing_id&gt;", "Cancel your listing"],
        ["/mylistings", "See your active listings"],
    ]
    market_tbl = _rich_table(["Command", "What it does"], market_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Trade & Gift ───────────────────────────────────────────
    trade_rows = [
        ["/trade &lt;yours&gt; &lt;theirs&gt;", "Trade waifus (reply to user)"],
        ["/gift &lt;id&gt;", "Gift a waifu (reply to user)"],
    ]
    trade_tbl = _rich_table(["Command", "What it does"], trade_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Economy ────────────────────────────────────────────────
    econ_rows = [
        ["/ball 🎳", "Play bowling, win Edollers"],
        ["/wpocket", "Check balance & balls left"],
        ["/wsend &lt;amount&gt;", "Send Edollers to a user"],
        ["/wtop", "Top Edollers holders"],
        ["/wrarity", "Collection breakdown by rarity"],
    ]
    econ_tbl = _rich_table(["Command", "What it does"], econ_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Customization ──────────────────────────────────────────
    cust_rows = [
        ["/whmode", "Set harem mode (Default/Rarity/Char/Anime)"],
        ["/whfav &lt;id&gt;", "Show only one character in harem"],
        ["/whstyle", "Change harem display style"],
    ]
    cust_tbl = _rich_table(["Command", "What it does"], cust_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Leaderboards & Stats ───────────────────────────────────
    stats_rows = [
        ["/top", "Top waifu collectors"],
        ["/ctop", "Chat leaderboard"],
        ["/topgroups", "Top groups"],
        ["/stats", "Bot statistics"],
    ]
    stats_tbl = _rich_table(["Command", "What it does"], stats_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Group Tools ────────────────────────────────────────────
    group_rows = [
        ["/changetime &lt;num&gt;", "Set spawn frequency (admin)"],
        ["/spawn &lt;id&gt; &lt;freq&gt; &lt;scope&gt;", "Control rarity spawn (sudo)"],
    ]
    group_tbl = _rich_table(["Command", "What it does"], group_rows, border=1) if RICH_UI_OK and _rich_table else ""

    # ─── Redeem ─────────────────────────────────────────────────
    redeem_rows = [
        ["/redeem &lt;code&gt;", "Redeem a code to get a character"],
    ]
    redeem_tbl = _rich_table(["Command", "What it does"], redeem_rows, border=1) if RICH_UI_OK and _rich_table else ""

    def _section(title: str, table: str, open: bool = False) -> str:
        if _rich_details and RICH_UI_OK:
            return f"<details{' open' if open else ''}><summary>{title}</summary>{table}</details>"
        return f"\n<b>{title}</b>\n{table}"

    html_text = (
        f"<h2>🎐 WAIFU CATCHER — HELP CENTER ♡</h2>"
        f"<blockquote>Hey {name}, here are all commands you can use.</blockquote>"
        + _section("🌸 CATCH & COLLECT", catch_tbl, open=True)
        + _section("🏪 MARKETPLACE", market_tbl)
        + _section("💌 TRADE & GIFT", trade_tbl)
        + _section("🪙 ECONOMY & COINS", econ_tbl)
        + _section("🎨 CUSTOMIZATION", cust_tbl)
        + _section("🏆 LEADERBOARDS & STATS", stats_tbl)
        + _section("⚙️ GROUP TOOLS", group_tbl)
        + _section("🎁 REDEEM", redeem_tbl)
        + f"<blockquote>✨ Click <b>ADD ME</b> below and let the catching begin!</blockquote>"
    )
    return html_text


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


def _help_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛩ Aᴅᴅ Mᴇ ⛩", url=f"https://t.me/{BOT_USERNAME}?startgroup=new")],
        [
            InlineKeyboardButton("✦ Sᴜᴘᴘᴏʀᴛ", url=f"https://t.me/{SUPPORT_CHAT}"),
            InlineKeyboardButton("✧ Uᴘᴅᴀᴛᴇs", url=f"https://t.me/{UPDATE_CHAT}"),
        ],
        [InlineKeyboardButton("⤾ Bᴀᴄᴋ Tᴏ Mᴇɴᴜ", callback_data="back")],
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

    # Private chat → full rich start
    if update.effective_chat.type == "private":
        html_text = build_start_html(first_name)
        await _send_rich(update, html_text, kb=_start_kb())
        return

    # Group chat → short message
    html_text = (
        f"<h3>🎴 WAIFU CATCHER</h3>"
        f"<blockquote>Alive! Connect to me in PM for more information.</blockquote>"
    )
    await _send_rich(update, html_text, kb=_start_kb())


# ══════════════════════════════════════════════════════════════
# HELP / BACK
# ══════════════════════════════════════════════════════════════
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    try:
        if query.data == 'help':
            html_text = build_help_html(query.from_user.first_name or 'User')
            await _send_rich(query, html_text, kb=_help_kb(), edit=True)

        elif query.data == 'back':
            html_text = build_start_html(query.from_user.first_name or 'User')
            await _send_rich(query, html_text, kb=_start_kb(), edit=True)
    except Exception as e:
        LOGGER.exception(f"[start.button] error: {e}")


# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════
application.add_handler(
    CallbackQueryHandler(button, pattern='^help$|^back$', block=False)
)
application.add_handler(CommandHandler('start', start, block=False))
