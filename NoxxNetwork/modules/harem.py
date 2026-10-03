from html import escape
from itertools import groupby
import math
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.error import BadRequest, TelegramError

from NoxxNetwork import (
    application,
    collection,
    user_collection,
    SUPPORT_CHAT,
    UPDATE_CHAT,
)


FORCE_JOIN_TEXT = (
    "🔔 <b>ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴛʜᴇ ғᴏʟʟᴏᴡɪɴɢ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ:</b>\n\n"
    "✦ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ\n"
    "✦ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ"
)


def _chat_ref(value):
    if not value:
        return None
    value = str(value).strip()
    if value.startswith("https://t.me/"):
        return "@" + value.rstrip("/").split("/")[-1].lstrip("@")
    if value.startswith("t.me/"):
        return "@" + value.rstrip("/").split("/")[-1].lstrip("@")
    if value.startswith("@"):
        return value
    try:
        return int(value)
    except ValueError:
        return "@" + value


def _join_url(value):
    if not value:
        return "https://t.me/"
    value = str(value).strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://t.me/{value.lstrip('@')}"


async def _is_joined(context, user_id, chat_ref):
    if not chat_ref:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=chat_ref, user_id=user_id)
        return member.status in {"creator", "administrator", "member"} or (
            member.status == "restricted" and getattr(member, "is_member", False)
        )
    except (TelegramError, BadRequest):
        # If the bot cannot verify the configured chat, don't lock users out.
        return True


async def _force_join_markup(context):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ ↗", url=_join_url(UPDATE_CHAT))],
        [InlineKeyboardButton("💬 Jᴏɪɴ Sᴜᴘᴘᴏʀᴛ Gʀᴏᴜᴘ ↗", url=_join_url(SUPPORT_CHAT))],
        [InlineKeyboardButton("↻ Cʜᴇᴄᴋ Aɢᴀɪɴ", callback_data="harem_check")],
    ])


async def ensure_joined(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    joined_update = await _is_joined(context, user_id, _chat_ref(UPDATE_CHAT))
    joined_support = await _is_joined(context, user_id, _chat_ref(SUPPORT_CHAT))

    if joined_update and joined_support:
        return True

    markup = await _force_join_markup(context)
    if update.message:
        await update.message.reply_text(FORCE_JOIN_TEXT, parse_mode="HTML", reply_markup=markup)
    else:
        query = update.callback_query
        try:
            await query.edit_message_text(FORCE_JOIN_TEXT, parse_mode="HTML", reply_markup=markup)
        except BadRequest:
            await query.message.reply_text(FORCE_JOIN_TEXT, parse_mode="HTML", reply_markup=markup)
    return False


async def harem(update: Update, context: CallbackContext, page=0) -> None:
    if not await ensure_joined(update, context):
        return

    user_id = update.effective_user.id
    user = await user_collection.find_one({'id': user_id})
    if not user or not user.get('characters'):
        text = "🌸 <b>Yᴏᴜʀ Hᴀʀᴇᴍ ɪs Eᴍᴘᴛʏ</b>\n\nᴜsᴇ /ɢʀᴀʙ ɪɴ ᴀ ɢʀᴏᴜᴘ ᴛᴏ sᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴡᴀɪғᴜs."
        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            await update.callback_query.edit_message_text(text, parse_mode='HTML')
        return

    characters = sorted(user['characters'], key=lambda x: (str(x.get('anime', '')), str(x.get('id', ''))))
    character_counts = {}
    for character in characters:
        character_counts[character['id']] = character_counts.get(character['id'], 0) + 1

    unique_characters = list({character['id']: character for character in characters}.values())
    total_pages = max(1, math.ceil(len(unique_characters) / 15))
    page = max(0, min(page, total_pages - 1))
    current_characters = unique_characters[page * 15:(page + 1) * 15]

    favorite_ids = set(user.get('favorites', []))
    harem_message = (
        f"🌸 <b>{escape(update.effective_user.first_name)}'s Hᴀʀᴇᴍ</b>\n"
        f"<i>Pᴀɢᴇ {page + 1}/{total_pages} • {len(user['characters'])} Cᴏʟʟᴇᴄᴛᴇᴅ</i>\n"
    )

    for anime, anime_chars in groupby(current_characters, key=lambda x: x.get('anime', 'Unknown')):
        anime_chars = list(anime_chars)
        total_anime = await collection.count_documents({'anime': anime})
        harem_message += f"\n<b>✦ {escape(str(anime))}</b> <i>{len(anime_chars)}/{total_anime}</i>\n"
        for character in anime_chars:
            star = " ♡" if character['id'] in favorite_ids else ""
            harem_message += (
                f"<code>{escape(str(character['id']))}</code>  "
                f"{escape(str(character['name']))} ×{character_counts[character['id']]}{star}\n"
            )

    keyboard = [[
        InlineKeyboardButton(
            f"♡ Sᴇᴇ Cᴏʟʟᴇᴄᴛɪᴏɴ • {len(user['characters'])}",
            switch_inline_query_current_chat=f"collection.{user_id}"
        )
    ]]

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("‹ Pʀᴇᴠ", callback_data=f"harem:{page - 1}:{user_id}"))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data=f"harem:{page}:{user_id}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Nᴇxᴛ ›", callback_data=f"harem:{page + 1}:{user_id}"))
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton("↻ Rᴇғʀᴇsʜ", callback_data=f"harem:{page}:{user_id}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    selected = next((c for c in characters if c['id'] in favorite_ids and c.get('img_url')), None)
    if not selected:
        selected = random.choice(characters)

    image = selected.get('img_url')
    if update.message:
        if image:
            await update.message.reply_photo(photo=image, caption=harem_message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(harem_message, parse_mode='HTML', reply_markup=reply_markup)
        return

    query = update.callback_query
    try:
        if image and query.message.photo:
            await query.edit_message_caption(caption=harem_message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await query.edit_message_text(harem_message, parse_mode='HTML', reply_markup=reply_markup)
    except BadRequest:
        pass


async def harem_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "harem_check":
        if await ensure_joined(update, context):
            await harem(update, context, 0)
        return

    _, page, user_id = query.data.split(':')
    page = int(page)
    user_id = int(user_id)

    if query.from_user.id != user_id:
        await query.answer("Iᴛ's Nᴏᴛ Yᴏᴜʀ Hᴀʀᴇᴍ.", show_alert=True)
        return

    await harem(update, context, page)


application.add_handler(CommandHandler(["harem", "collection"], harem, block=False))
application.add_handler(CallbackQueryHandler(harem_callback, pattern=r'^(?:harem|harem_check)', block=False))
