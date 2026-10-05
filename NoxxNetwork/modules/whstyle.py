from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from NoxxNetwork import application, db, LOGGER

style_col = db['harem_styles']

TOTAL_STYLES = 6   # 0 = default, 1-5 = custom


# ---------------------------------------------------------------------------
# Style format functions
# ---------------------------------------------------------------------------
def format_anime_header(style: int, anime: str, count: int, total: int) -> str:
    """Returns formatted anime header line (with leading newline)."""
    a = escape(str(anime))
    if style == 1:
        return f"\n➤ {a} [🎮] ﴾{count}/{total}﴿"
    if style == 2:
        return f"\n⧉ {a} [🎮] ⦋{count}/{total}⦌"
    if style == 3:
        return f"\n⎋ {a} 「{count}/{total}」"
    if style == 4:
        return f"\n🈴 {a} [🎮] 「{count}/{total}」"
    if style == 5:
        return f"\n⌬ {a} 〔{count}/{total}〕"
    # style 0 — default
    return f"\n<b>✦ {a}</b> <i>{count}/{total}</i>"


def format_char_line(
    style: int,
    char_id: str,
    name: str,
    rarity_symbol_str: str,
    count: int,
    is_fav: bool = False,
) -> str:
    """Returns formatted character line (with trailing newline)."""
    cid = escape(str(char_id))
    n = escape(str(name))
    s = escape(str(rarity_symbol_str))
    star = " ♡" if is_fav else ""

    if style == 1:
        return f"⤷〔{s}〕 {cid} {n} ×{count}{star}\n"
    if style == 2:
        return f"⤷〔{s}〕 {cid} {n} ×{count}{star}\n"
    if style == 3:
        return f"⊰ 〔{s}〕 {cid} {n} ×{count}{star}\n"
    if style == 4:
        return f"ID: {cid} 〔{s}〕 {n} ×{count}{star}\n"
    if style == 5:
        return f"◈⌠{s}⌡ {cid} {n} ×{count}{star}\n"
    # style 0 — default
    return f"↪ <b>[{s}]</b> {cid} {n} ×{count}{star}\n"


def post_anime_block(style: int) -> str:
    """Extra text after the character list for a specific style."""
    if style == 4:
        return "------------------------\n"
    return ""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def get_user_style(user_id: int) -> int:
    doc = await style_col.find_one({'user_id': user_id})
    if not doc:
        return 0
    try:
        s = int(doc.get('style', 0))
        return s if 0 <= s < TOTAL_STYLES else 0
    except (TypeError, ValueError):
        return 0


async def set_user_style(user_id: int, style: int):
    await style_col.update_one(
        {'user_id': user_id},
        {'$set': {'style': int(style)}},
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Preview builder
# ---------------------------------------------------------------------------
def build_preview(style: int) -> str:
    """Builds a fake preview matching the given style."""
    fake_anime = "Honkai Star Rail"
    fake_total = 86
    fake_count = 1

    text = f"<b>ʏᴏᴜʀ sᴇʟᴇᴄᴛᴇᴅ sᴛʏʟᴇ ɴᴜᴍʙᴇʀ: {style}</b>\n"

    # Style 0 — original default header
    if style == 0:
        text += format_anime_header(0, fake_anime, fake_count, fake_total) + "\n"
        text += format_char_line(0, "3547", "Stelle", "🟡", 1)
        return text

    text += format_anime_header(style, fake_anime, fake_count, fake_total) + "\n"
    text += format_char_line(style, "3547", "Stelle", "🟡", 1)
    text += post_anime_block(style)
    return text


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------
def _style_kb(style: int) -> InlineKeyboardMarkup:
    rows = []

    # Navigation row
    nav = []
    if style > 0:
        nav.append(InlineKeyboardButton("⬅️ PREVIOUS", callback_data=f"whstyle:show:{style - 1}"))
    if style < TOTAL_STYLES - 1:
        nav.append(InlineKeyboardButton("NEXT ➡️", callback_data=f"whstyle:show:{style + 1}"))
    if nav:
        rows.append(nav)

    # SET button
    rows.append([InlineKeyboardButton("SET", callback_data=f"whstyle:set:{style}")])

    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# /whstyle
# ---------------------------------------------------------------------------
async def whstyle(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    current = await get_user_style(user.id)

    text = build_preview(current)
    await update.message.reply_text(
        text,
        parse_mode='HTML',
        reply_markup=_style_kb(current),
    )


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------
async def whstyle_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(':')
    if len(parts) < 3:
        return

    action = parts[1]
    try:
        style = int(parts[2])
    except (ValueError, IndexError):
        return

    if style < 0 or style >= TOTAL_STYLES:
        return

    user = query.from_user

    if action == 'show':
        text = build_preview(style)
        try:
            await query.edit_message_text(
                text,
                parse_mode='HTML',
                reply_markup=_style_kb(style),
            )
        except Exception:
            pass
        return

    if action == 'set':
        await set_user_style(user.id, style)
        text = build_preview(style)
        # Overwrite the top line with "SET" confirmation
        text = (
            f"<b>✅ Yᴏᴜ sᴇᴛ ʏᴏᴜʀ Hᴀʀᴇᴍ sᴛʏʟᴇ ᴛᴏ {style}</b>\n\n"
            + text
        )
        try:
            await query.edit_message_text(
                text,
                parse_mode='HTML',
                reply_markup=_style_kb(style),
            )
        except Exception:
            pass
        return


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
application.add_handler(CommandHandler(["whstyle", "hstyle", "style"], whstyle, block=False))
application.add_handler(CallbackQueryHandler(whstyle_callback, pattern=r'^whstyle:', block=False))