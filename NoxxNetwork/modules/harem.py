from html import escape
from itertools import groupby
import math
import random
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
)
from telegram.error import BadRequest, TelegramError

from NoxxNetwork import (
    application,
    collection,
    user_collection,
    SUPPORT_CHAT,
    UPDATE_CHAT,
    db,
    LOGGER,
)
from NoxxNetwork.rarity import rarity_symbol, rarity_name, rarity_id_from_value, RARITIES

harem_mode_col = db['harem_modes']
join_requests_col = db['join_requests']

# 🔥 Private group config
PRIVATE_GROUP_ID = -1004450386900
HAREM_SUPPORT_CHAT = "https://t.me/+A3bmzLTMu5sxMWVh"

FORCE_JOIN_TEXT = (
    "🔔 <b>ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴛʜᴇ ғᴏʟʟᴏᴡɪɴɢ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ:</b>\n\n"
    "✦ ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ\n"
    "✦ sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ\n\n"
)


def _join_url(value):
    if not value:
        return "https://t.me/"
    value = str(value).strip()
    if value.startswith(("http://", "https://")):
        return value
    return f"https://t.me/{value.lstrip('@')}"


def _chat_ref(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if value.startswith(("https://t.me/", "http://t.me/")):
        value = value.rstrip("/").split("/")[-1]
    elif value.startswith("t.me/"):
        value = value.rstrip("/").split("/")[-1]
    if value.startswith("@"):
        return value
    try:
        return int(value)
    except ValueError:
        return "@" + value


async def _check_private_group(context, user_id) -> bool:
    """Check if user is member OR has sent a join request."""
    # 1️⃣ Member check
    try:
        member = await context.bot.get_chat_member(
            chat_id=PRIVATE_GROUP_ID,
            user_id=user_id,
        )
        status = str(getattr(member, "status", "")).lower()
        if status in {"creator", "administrator", "member"}:
            return True
        if status == "restricted" and getattr(member, "is_member", False):
            return True
    except TelegramError as exc:
        LOGGER.warning(
            "Private group membership check failed: user=%s error=%s", user_id, exc
        )

    # 2️⃣ Join request check
    try:
        req = await join_requests_col.find_one({
            'user_id': user_id,
            'chat_id': PRIVATE_GROUP_ID,
        })
        if req:
            return True
    except Exception as exc:
        LOGGER.warning(f"Join request lookup failed: {exc}")

    return False


async def _check_public_chat(context, user_id, chat_value) -> bool:
    """Check membership in a public chat/channel."""
    ref = _chat_ref(chat_value)
    if not ref:
        return True
    try:
        chat = await context.bot.get_chat(ref)
        member = await context.bot.get_chat_member(chat_id=chat.id, user_id=user_id)
        status = str(getattr(member, "status", "")).lower()
        if status in {"creator", "administrator", "member"}:
            return True
        if status == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except TelegramError as exc:
        LOGGER.warning(
            "Public chat check failed: chat=%r user=%s error=%s", ref, user_id, exc
        )
        # Fail-open for public chats (can't verify due to bot not being admin etc.)
        return True


def _force_join_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ ↗", url=_join_url(UPDATE_CHAT))],
        [InlineKeyboardButton("💬 Jᴏɪɴ Sᴜᴘᴘᴏʀᴛ Gʀᴏᴜᴘ ↗", url=_join_url(HAREM_SUPPORT_CHAT))],
        [InlineKeyboardButton("↻ Cʜᴇᴄᴋ Aɢᴀɪɴ", callback_data="harem_check")],
    ])


async def _show_force_join(update, context, verification_error=False):
    text = FORCE_JOIN_TEXT
    if verification_error:
        text += (
            "\n\n⚠️ <b>ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ</b>\n"
            "Mᴀᴋᴇ sᴜʀᴇ ᴛʜᴇ ʙᴏᴛ ɪs ᴀᴅᴍɪɴ ɪɴ ʙᴏᴛʜ ᴄʜᴀᴛs."
        )
    markup = _force_join_markup()
    if update.message:
        return await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    query = update.callback_query
    try:
        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=markup)
        else:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except BadRequest:
        pass


async def ensure_joined(update, context):
    """Returns True if user is member OR has sent join request."""
    user_id = update.effective_user.id

    # Update channel check (public)
    u_ok = await _check_public_chat(context, user_id, UPDATE_CHAT)

    # Private group check (member OR join request)
    g_ok = await _check_private_group(context, user_id)

    if u_ok and g_ok:
        return True

    await _show_force_join(update, context, verification_error=False)
    return False


# ──────────────────────────────────────────────────────────────
# 🔥 JOIN REQUEST HANDLER — records user when they send request
# ──────────────────────────────────────────────────────────────
async def handle_join_request(update: Update, context: CallbackContext) -> None:
    """Fires when a user sends a join request to the private group.

    Records user so they can use /harem even before admin approves.
    Admin will approve later (bot doesn't auto-approve).
    """
    try:
        request = update.chat_join_request
        if not request:
            return

        chat_id = request.chat.id
        user = request.from_user

        # Only care about our private group
        if chat_id != PRIVATE_GROUP_ID:
            return

        # Save to DB
        await join_requests_col.update_one(
            {'user_id': user.id, 'chat_id': chat_id},
            {
                '$set': {
                    'user_id': user.id,
                    'chat_id': chat_id,
                    'first_name': user.first_name,
                    'username': user.username,
                    'requested_at': int(time.time()),
                }
            },
            upsert=True,
        )

        LOGGER.info(
            f"Join request received: user={user.id} ({user.first_name}) chat={chat_id}"
        )

        # Notify user they're verified
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    "✅ <b>Vᴇʀɪғɪᴇᴅ!</b>\n\n"
                    "Yᴏᴜʀ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ ʀᴇᴄᴏʀᴅᴇᴅ.\n"
                    "Yᴏᴜ ᴄᴀɴ ɴᴏᴡ ᴜsᴇ <code>/harem</code> ɪɴ ᴛʜᴇ ʙᴏᴛ.\n\n"
                    "<i>Yᴏᴜʀ ᴊᴏɪɴ ʀᴇǫᴜᴇsᴛ ᴡɪʟʟ ʙᴇ ᴀᴘᴘʀᴏᴠᴇᴅ ʙʏ ᴀɴ ᴀᴅᴍɪɴ sᴏᴏɴ.</i>"
                ),
                parse_mode='HTML',
            )
        except Exception as exc:
            LOGGER.warning(f"Could not DM user {user.id}: {exc}")

    except Exception as exc:
        LOGGER.exception(f"handle_join_request error: {exc}")


# ──────────────────────────────────────────────────────────────
# HAREM MODE
# ──────────────────────────────────────────────────────────────
async def _get_harem_mode(user_id: int) -> dict:
    doc = await harem_mode_col.find_one({'user_id': user_id})
    if not doc:
        return {'mode': 'default', 'rarity_id': 0, 'fav_id': ''}
    return {
        'mode': str(doc.get('mode', 'default')),
        'rarity_id': int(doc.get('rarity_id', 0)),
        'fav_id': str(doc.get('fav_id', '') or ''),
    }


async def harem(update: Update, context: CallbackContext, page=0, checked=False) -> None:
    if not checked and not await ensure_joined(update, context):
        return

    user_id = update.effective_user.id
    user = await user_collection.find_one({'id': user_id})
    if not user or not user.get('characters'):
        text = (
            "🌸 <b>Yᴏᴜʀ Hᴀʀᴇᴍ ɪs Eᴍᴘᴛʏ</b>\n\n"
            "ᴜsᴇ /ɢʀᴀʙ ɪɴ ᴀ ɢʀᴏᴜᴘ ᴛᴏ sᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴡᴀɪғᴜs."
        )
        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            try:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            except BadRequest:
                pass
        return

    mode_pref = await _get_harem_mode(user_id)
    mode = mode_pref['mode']
    rarity_filter_id = mode_pref['rarity_id']
    fav_id_filter = mode_pref['fav_id']

    characters = list(user['characters'])

    if mode == 'fav_id' and fav_id_filter:
        candidates = [fav_id_filter, fav_id_filter.zfill(2), fav_id_filter.lstrip('0') or '0']
        characters = [c for c in characters if str(c.get('id')) in candidates]
    elif mode == 'rarity' and rarity_filter_id:
        characters = [
            c for c in characters
            if rarity_id_from_value(c.get('rarity')) == rarity_filter_id
        ]

    if mode == 'characters':
        characters = sorted(
            characters,
            key=lambda x: (str(x.get('name', '')).lower(), str(x.get('id', ''))),
        )
    elif mode == 'rarity':
        characters = sorted(
            characters,
            key=lambda x: (
                -rarity_id_from_value(x.get('rarity')),
                str(x.get('name', '')).lower(),
            ),
        )
    elif mode == 'anime':
        characters = sorted(
            characters,
            key=lambda x: (str(x.get('anime', '')).lower(), str(x.get('id', ''))),
        )
    else:
        characters = sorted(
            characters,
            key=lambda x: (str(x.get('anime', '')), str(x.get('id', ''))),
        )

    if not characters:
        if mode == 'rarity' and rarity_filter_id:
            emoji, name = RARITIES.get(rarity_filter_id, ("⚪", "Common"))
            text = (
                f"🌸 <b>Yᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴀɴʏ {emoji} {escape(name)} ᴄʜᴀʀᴀᴄᴛᴇʀs</b>\n\n"
                f"Usᴇ <code>/whmode</code> ᴛᴏ ᴄʜᴀɴɢᴇ ᴛʜᴇ ʜᴀʀᴇᴍ ᴍᴏᴅᴇ."
            )
        elif mode == 'fav_id':
            text = (
                f"🌸 <b>Nᴏ ᴄʜᴀʀᴀᴄᴛᴇʀ ғᴏᴜɴᴅ ᴡɪᴛʜ ɪᴅ {escape(fav_id_filter)}</b>\n\n"
                f"Usᴇ <code>/whfav off</code> ᴛᴏ ʀᴇsᴇᴛ."
            )
        else:
            text = "🌸 <b>Nᴏ ᴄʜᴀʀᴀᴄᴛᴇʀs ᴛᴏ sʜᴏᴡ.</b>"

        if update.message:
            await update.message.reply_text(text, parse_mode='HTML')
        else:
            try:
                await update.callback_query.edit_message_text(text, parse_mode='HTML')
            except BadRequest:
                pass
        return

    character_counts = {}
    for character in characters:
        cid = str(character['id'])
        character_counts[cid] = character_counts.get(cid, 0) + 1

    unique_characters = list({str(c['id']): c for c in characters}.values())

    total_pages = max(1, math.ceil(len(unique_characters) / 15))
    page = max(0, min(page, total_pages - 1))
    current_characters = unique_characters[page * 15:(page + 1) * 15]
    favorite_ids = {str(x) for x in user.get('favorites', [])}

    mode_badge = ""
    if mode == 'fav_id' and fav_id_filter:
        mode_badge = f"\n<i>Mᴏᴅᴇ: ғᴀᴠ ID <code>{escape(fav_id_filter)}</code></i>"
    elif mode == 'rarity' and rarity_filter_id:
        emoji, name = RARITIES.get(rarity_filter_id, ("⚪", "Common"))
        mode_badge = f"\n<i>Mᴏᴅᴇ: {emoji} {escape(name)}</i>"
    elif mode == 'characters':
        mode_badge = "\n<i>Mᴏᴅᴇ: Cʜᴀʀᴀᴄᴛᴇʀs (A-Z)</i>"
    elif mode == 'anime':
        mode_badge = "\n<i>Mᴏᴅᴇ: Aɴɪᴍᴇ (A-Z)</i>"

    harem_message = (
        f"🌸 <b>{escape(update.effective_user.first_name or 'User')}'s Hᴀʀᴇᴍ</b>\n"
        f"<i>Pᴀɢᴇ {page + 1}/{total_pages} • {len(user['characters'])} Cᴏʟʟᴇᴄᴛᴇᴅ</i>"
        f"{mode_badge}\n"
    )

    if mode in ('rarity', 'characters', 'fav_id'):
        for character in current_characters:
            cid = str(character['id'])
            star = " ♡" if cid in favorite_ids else ""
            symbol = escape(rarity_symbol(character.get('rarity')))
            harem_message += (
                f"↪ <b>[{symbol}]</b> {escape(cid)} "
                f"{escape(str(character['name']))} ×{character_counts[cid]}{star}\n"
            )
    else:
        for anime, anime_chars in groupby(current_characters, key=lambda x: x.get('anime', 'Unknown')):
            anime_chars = list(anime_chars)
            total_anime = await collection.count_documents({'anime': anime})
            harem_message += f"\n<b>✦ {escape(str(anime))}</b> <i>{len(anime_chars)}/{total_anime}</i>\n"
            for character in anime_chars:
                cid = str(character['id'])
                star = " ♡" if cid in favorite_ids else ""
                symbol = escape(rarity_symbol(character.get('rarity')))
                harem_message += (
                    f"↪ <b>[{symbol}]</b> {escape(cid)} "
                    f"{escape(str(character['name']))} ×{character_counts[cid]}{star}\n"
                )

    keyboard = [[
        InlineKeyboardButton(
            f"♡ Sᴇᴇ Cᴏʟʟᴇᴄᴛɪᴏɴ • {len(user['characters'])}",
            switch_inline_query_current_chat=f"collection.{user_id}",
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

    all_user_chars = list(user['characters'])
    selected = next(
        (c for c in all_user_chars if str(c['id']) in favorite_ids and c.get('img_url')),
        None,
    ) or random.choice(all_user_chars)
    image = selected.get('img_url')

    if update.message:
        if image:
            await update.message.reply_photo(
                photo=image,
                caption=harem_message,
                parse_mode='HTML',
                reply_markup=reply_markup,
            )
        else:
            await update.message.reply_text(
                harem_message,
                parse_mode='HTML',
                reply_markup=reply_markup,
            )
        return

    query = update.callback_query
    try:
        if image and query.message.photo:
            await query.edit_message_caption(
                caption=harem_message,
                parse_mode='HTML',
                reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(
                harem_message,
                parse_mode='HTML',
                reply_markup=reply_markup,
            )
    except BadRequest:
        pass


async def harem_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'harem_check':
        if await ensure_joined(update, context):
            await harem(update, context, 0, checked=True)
        return

    try:
        _, page, owner_id = query.data.split(':')
        page, owner_id = int(page), int(owner_id)
    except (ValueError, AttributeError):
        return

    if query.from_user.id != owner_id:
        await query.answer("Iᴛ's Nᴏᴛ Yᴏᴜʀ Hᴀʀᴇᴍ.", show_alert=True)
        return

    await harem(update, context, page, checked=True)


# ──────────────────────────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────────────────────────
application.add_handler(CommandHandler(["harem", "collection"], harem, block=False))
application.add_handler(
    CallbackQueryHandler(harem_callback, pattern=r'^harem(?:_|:)', block=False)
)
application.add_handler(ChatJoinRequestHandler(handle_join_request, block=False))
