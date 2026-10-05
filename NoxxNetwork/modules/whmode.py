from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from NoxxNetwork import application, db, user_collection, LOGGER
from NoxxNetwork.rarity import RARITIES

harem_mode_col = db['harem_modes']

BANNER_URL = "https://i.ibb.co/8gvNGSbL/26831adc4ea1.jpg"

DEFAULT_MODE = {
    'mode': 'default',
    'rarity_id': 0,
    'fav_id': '',
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def get_harem_mode(user_id: int) -> dict:
    doc = await harem_mode_col.find_one({'user_id': user_id})
    if not doc:
        return dict(DEFAULT_MODE)
    return {
        'mode': str(doc.get('mode', 'default')),
        'rarity_id': int(doc.get('rarity_id', 0)),
        'fav_id': str(doc.get('fav_id', '') or ''),
    }


async def set_harem_mode(user_id: int, mode: str, rarity_id: int = 0, fav_id: str = ''):
    await harem_mode_col.update_one(
        {'user_id': user_id},
        {'$set': {'mode': mode, 'rarity_id': int(rarity_id), 'fav_id': str(fav_id)}},
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------
def _main_menu_kb(current_mode: dict) -> InlineKeyboardMarkup:
    mode = current_mode['mode']

    def _mark(m):
        return " ✅" if mode == m else ""

    rows = [
        [
            InlineKeyboardButton(f"Dᴇғᴀᴜʟᴛ{_mark('default')}", callback_data="whmode:default"),
            InlineKeyboardButton(f"Rᴀʀɪᴛʏ{_mark('rarity')}", callback_data="whmode:rarity_menu"),
        ],
        [
            InlineKeyboardButton(f"Cʜᴀʀᴀᴄᴛᴇʀs{_mark('characters')}", callback_data="whmode:characters"),
            InlineKeyboardButton(f"Aɴɪᴍᴇ{_mark('anime')}", callback_data="whmode:anime"),
        ],
        [
            InlineKeyboardButton("Cʟᴏsᴇ", callback_data="whmode:close"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def _rarity_grid_kb() -> InlineKeyboardMarkup:
    rows = []
    items = list(RARITIES.items())
    for i in range(0, len(items), 2):
        row = []
        for rid, (emoji, name) in items[i:i + 2]:
            row.append(
                InlineKeyboardButton(
                    f"{emoji} {name}",
                    callback_data=f"whmode:set_rarity:{rid}",
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton("Cʟᴏsᴇ", callback_data="whmode:close")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# /whmode
# ---------------------------------------------------------------------------
async def whmode(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    current = await get_harem_mode(user.id)

    caption = (
        f"<b>{escape(user.first_name or 'User')}, ᴘʟᴇᴀsᴇ ᴄʜᴏᴏsᴇ ʀᴀʀɪᴛʏ\n"
        f"ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ sᴇᴛ ᴀs\n"
        f"ʜᴀʀᴇᴍ ᴍᴏᴅᴇ</b>"
    )

    try:
        await update.message.reply_photo(
            photo=BANNER_URL,
            caption=caption,
            parse_mode='HTML',
            reply_markup=_main_menu_kb(current),
        )
    except Exception:
        await update.message.reply_text(
            caption, parse_mode='HTML', reply_markup=_main_menu_kb(current)
        )


# ---------------------------------------------------------------------------
# /whfav <character_id>  — show ALL characters with the same NAME (Option B)
# ---------------------------------------------------------------------------
async def whfav(update: Update, context: CallbackContext) -> None:
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "Usᴀɢᴇ: <code>/whfav &lt;character_id&gt;</code>\n\n"
            "Exᴀᴍᴘʟᴇ: <code>/whfav 1768</code>\n\n"
            "Tᴏ ᴛᴜʀɴ ᴏғғ: <code>/whfav off</code>",
            parse_mode='HTML',
        )
        return

    raw_id = str(context.args[0]).strip()

    # Turn OFF
    if raw_id.lower() in ('off', 'reset', 'clear', 'none'):
        await set_harem_mode(user.id, 'default', 0, '')
        await update.message.reply_text(
            "✅ Hᴀʀᴇᴍ ᴍᴏᴅᴇ ʀᴇsᴇᴛ ᴛᴏ <b>Dᴇғᴀᴜʟᴛ</b>.",
            parse_mode='HTML',
        )
        return

    # Get user's collection
    user_doc = await user_collection.find_one({'id': user.id})
    owned = user_doc.get('characters', []) if user_doc else []

    # Find the reference character (exact ID match)
    matched = None
    for c in owned:
        if str(c.get('id')) == raw_id:
            matched = c
            break

    if not matched:
        await update.message.reply_text(
            f"❌ Yᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ɪᴅ <code>{raw_id}</code>.",
            parse_mode='HTML',
        )
        return

    char_id = str(matched.get('id'))
    char_name = str(matched.get('name', 'Unknown'))

    # 🔥 Save the NAME (not just ID) — so all characters with same name show
    await set_harem_mode(user.id, 'fav_name', 0, char_name)

    # Count how many variants/copies of this name
    same_name_count = sum(
        1 for c in owned if str(c.get('name', '')).lower() == char_name.lower()
    )
    same_name_unique = len({
        str(c.get('id')) for c in owned
        if str(c.get('name', '')).lower() == char_name.lower()
    })

    await update.message.reply_text(
        f"🌸 <b>Hᴀʀᴇᴍ Mᴏᴅᴇ Sᴇᴛ</b>\n\n"
        f"🎴 Cʜᴀʀᴀᴄᴛᴇʀ: <b>{escape(char_name)}</b>\n"
        f"🆔 Rᴇғ ID: <code>{char_id}</code>\n\n"
        f"📊 Yᴏᴜ ᴏᴡɴ <b>{same_name_unique}</b> ᴜɴɪǫᴜᴇ ᴠᴀʀɪᴀɴᴛs ({same_name_count} ᴛᴏᴛᴀʟ ᴄᴏᴘɪᴇs)\n\n"
        f"Nᴏᴡ /harem ᴡɪʟʟ sʜᴏᴡ ᴀʟʟ <b>{escape(char_name)}</b> ᴄʜᴀʀᴀᴄᴛᴇʀs.\n"
        f"Tᴏ ᴛᴜʀɴ ᴏғғ: <code>/whfav off</code>",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# Callback handler
# ---------------------------------------------------------------------------
async def whmode_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    parts = data.split(':')
    action = parts[1] if len(parts) > 1 else ''
    user = query.from_user

    if action == 'close':
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_caption("❌ Cʟᴏsᴇᴅ.")
            except Exception:
                pass
        return

    if action == 'rarity_menu':
        caption = (
            f"<b>{escape(user.first_name or 'User')}, ᴘʟᴇᴀsᴇ ᴄʜᴏᴏsᴇ ʀᴀʀɪᴛʏ\n"
            f"ᴛʜᴀᴛ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ sᴇᴛ ᴀs\n"
            f"ʜᴀʀᴇᴍ ᴍᴏᴅᴇ</b>"
        )
        try:
            await query.edit_message_caption(
                caption=caption,
                parse_mode='HTML',
                reply_markup=_rarity_grid_kb(),
            )
        except Exception:
            try:
                await query.edit_message_text(
                    caption, parse_mode='HTML', reply_markup=_rarity_grid_kb()
                )
            except Exception:
                pass
        return

    if action == 'set_rarity':
        try:
            rarity_id = int(parts[2])
        except (IndexError, ValueError):
            return

        if rarity_id not in RARITIES:
            await query.answer("Invalid rarity.", show_alert=True)
            return

        await set_harem_mode(user.id, 'rarity', rarity_id, '')

        emoji, name = RARITIES[rarity_id]
        caption = (
            f"<b>ʏᴏᴜ sᴜᴄᴄᴇssғᴜʟʟʏ sᴇᴛ ʏᴏᴜʀ ʜᴀʀᴇᴍ\n"
            f"ᴍᴏᴅᴇ ʀᴀʀɪᴛʏ ᴀs {emoji} {escape(name)}</b>"
        )
        try:
            await query.edit_message_caption(caption=caption, parse_mode='HTML')
        except Exception:
            try:
                await query.edit_message_text(caption, parse_mode='HTML')
            except Exception:
                pass
        return

    if action in ('default', 'characters', 'anime'):
        await set_harem_mode(user.id, action, 0, '')

        label_map = {
            'default': "Dᴇғᴀᴜʟᴛ",
            'characters': "Cʜᴀʀᴀᴄᴛᴇʀs",
            'anime': "Aɴɪᴍᴇ",
        }
        caption = (
            f"<b>ʏᴏᴜ sᴜᴄᴄᴇssғᴜʟʟʏ sᴇᴛ ʏᴏᴜʀ ʜᴀʀᴇᴍ\n"
            f"ᴍᴏᴅᴇ ᴀs {label_map[action]}</b>"
        )
        try:
            await query.edit_message_caption(caption=caption, parse_mode='HTML')
        except Exception:
            try:
                await query.edit_message_text(caption, parse_mode='HTML')
            except Exception:
                pass
        return


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
application.add_handler(CommandHandler(["whmode", "harem_mode", "hmode"], whmode, block=False))
application.add_handler(CommandHandler(["whfav", "haremfav"], whfav, block=False))
application.add_handler(CallbackQueryHandler(whmode_callback, pattern=r'^whmode:', block=False))
