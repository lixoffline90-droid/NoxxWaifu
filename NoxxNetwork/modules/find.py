from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from NoxxNetwork import application, user_collection, collection

USERS_PER_PAGE = 10


async def find(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("U sᴀɢᴇ: /find <character_id>")
        return

    character_id = str(context.args[0]).strip()

    # Verify character exists in main DB
    character = await collection.find_one({'id': character_id})
    if not character:
        character = await collection.find_one({'id': character_id.zfill(2)})
    if not character:
        await update.message.reply_text(
            f"❌ Cʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ID <code>{character_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ.",
            parse_mode='HTML',
        )
        return

    character_id = character['id']

    # Count total owners
    total_owners = await user_collection.count_documents({'characters.id': character_id})

    if total_owners == 0:
        await update.message.reply_text(
            f"📋 <b>Owners of Character ID: {character_id}</b>\n\n"
            f"Nᴏ ᴏɴᴇ ᴏᴡɴs ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ʏᴇᴛ!",
            parse_mode='HTML',
        )
        return

    total_pages = (total_owners + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    text = await _build_page(character_id, 0, total_owners, total_pages, character)

    keyboard = []
    if total_pages > 1:
        keyboard.append([
            InlineKeyboardButton("Next ➡️", callback_data=f"find_page:{character_id}:1")
        ])
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)


async def _build_page(character_id: str, page: int, total_owners: int, total_pages: int, character: dict) -> str:
    skip = page * USERS_PER_PAGE
    cursor = user_collection.find({'characters.id': character_id}).skip(skip).limit(USERS_PER_PAGE)
    users = await cursor.to_list(length=USERS_PER_PAGE)

    text = (
        f"📋 <b>Owners of Character ID:</b> {escape(character_id)}\n"
        f"<i>{escape(str(character.get('name', 'Unknown')))}</i>\n"
        f"<i>Total: {total_owners} owners</i>\n\n"
    )

    for i, user in enumerate(users, start=skip + 1):
        name = escape(str(user.get('first_name') or 'Unknown'))
        username = user.get('username')
        if username:
            text += f"{i}. <b>{name}</b> @{escape(username)}\n"
        else:
            text += f"{i}. <b>{name}</b>\n"

    text += f"\nPᴀɢᴇ {page + 1}/{total_pages}"
    return text


async def find_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(':')
    if len(parts) != 3:
        return

    _, character_id, page_str = parts
    page = int(page_str)

    character = await collection.find_one({'id': character_id})
    if not character:
        await query.edit_message_text("Character not found.")
        return

    total_owners = await user_collection.count_documents({'characters.id': character_id})
    total_pages = (total_owners + USERS_PER_PAGE - 1) // USERS_PER_PAGE

    text = await _build_page(character_id, page, total_owners, total_pages, character)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"find_page:{character_id}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"find_page:{character_id}:{page + 1}"))

    reply_markup = InlineKeyboardMarkup([nav])

    try:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    except Exception:
        pass


application.add_handler(CommandHandler("find", find, block=False))
application.add_handler(CallbackQueryHandler(find_callback, pattern=r'^find_page:', block=False))