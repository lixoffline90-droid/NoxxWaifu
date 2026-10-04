import importlib
import time
import random
import re
import asyncio
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import (
    CommandHandler,
    CallbackContext,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from NoxxNetwork import (
    collection,
    top_global_groups_collection,
    group_user_totals_collection,
    user_collection,
    user_totals_collection,
    Waifuu,
)
from NoxxNetwork import application, SUPPORT_CHAT, UPDATE_CHAT, db, LOGGER
from NoxxNetwork.modules import ALL_MODULES
from NoxxNetwork.rarity import RARITIES, rarity_symbol, rarity_name, get_probability_table


locks = {}
message_counters = {}
spam_counters = {}
last_characters = {}
sent_characters = {}
first_correct_guesses = {}
message_counts = {}
# Counts messages after the current character appears. Expiry is message-based, never time-based.
character_message_counts = {}


for module_name in ALL_MODULES:
    imported_module = importlib.import_module("NoxxNetwork.modules." + module_name)


last_user = {}
warned_users = {}


def escape_markdown(text):
    escape_chars = r'\*_`\\~>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)


async def message_counter(update: Update, context: CallbackContext) -> None:
    """Count group messages and handle normal character spawning/12-message expiry."""
    chat = update.effective_chat
    if not chat or chat.type not in {"group", "supergroup"}:
        return

    chat_id = str(chat.id)
    user_id = update.effective_user.id if update.effective_user else 0

    if chat_id not in locks:
        locks[chat_id] = asyncio.Lock()

    async with locks[chat_id]:
        # Every incoming group message counts toward an active character's
        # 12-message lifetime, regardless of its content.
        if chat.id in last_characters:
            character_message_counts[chat.id] = character_message_counts.get(chat.id, 0) + 1
            if character_message_counts[chat.id] >= 12:
                expired = last_characters.pop(chat.id, None)
                first_correct_guesses.pop(chat.id, None)
                character_message_counts.pop(chat.id, None)
                if expired:
                    await send_expiry_notice(update, context, expired)
                # Start a fresh normal-spawn counter after an expiry.
                message_counts[chat_id] = 0
                return

        chat_frequency = await user_totals_collection.find_one({'chat_id': chat_id})
        message_frequency = int(chat_frequency.get('message_frequency', 100)) if chat_frequency else 100
        message_frequency = max(100, message_frequency)

        # Keep the existing anti-spam behavior, but the active character was
        # already counted above as requested (any group message counts).
        if chat_id in last_user and last_user[chat_id]['user_id'] == user_id:
            last_user[chat_id]['count'] += 1
            if last_user[chat_id]['count'] >= 10:
                if user_id in warned_users and time.time() - warned_users[user_id] < 600:
                    return
                warned_users[user_id] = time.time()
                if update.message:
                    await update.message.reply_text(
                        f"⚠️ Don't Spam {update.effective_user.first_name}...\n"
                        "Your Messages Will be ignored for 10 Minutes..."
                    )
                return
        else:
            last_user[chat_id] = {'user_id': user_id, 'count': 1}

        message_counts[chat_id] = message_counts.get(chat_id, 0) + 1
        if message_counts[chat_id] >= message_frequency and chat.id not in last_characters:
            await send_image(update, context)
            message_counts[chat_id] = 0


async def choose_character_by_rarity(all_characters):
    """Choose a character using the globally configured rarity weights."""
    if not all_characters:
        return None
    probabilities = await get_probability_table()
    grouped = {}
    for character in all_characters:
        grouped.setdefault(rarity_name(character.get('rarity')), []).append(character)

    weighted_groups = []
    for number, (_emoji, name) in RARITIES.items():
        chars = grouped.get(name, [])
        weight = float(probabilities.get(number, 0))
        if chars and weight > 0:
            weighted_groups.append((name, weight, chars))

    if not weighted_groups:
        return random.choice(all_characters)

    chosen_name = random.choices(
        [item[0] for item in weighted_groups],
        weights=[item[1] for item in weighted_groups],
        k=1,
    )[0]
    pool = next(item[2] for item in weighted_groups if item[0] == chosen_name)
    return random.choice(pool)


async def send_image(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    all_characters = list(await collection.find({}).to_list(length=None))
    if not all_characters:
        return

    if chat_id not in sent_characters:
        sent_characters[chat_id] = []

    available = [c for c in all_characters if c.get('id') not in sent_characters[chat_id]]
    if not available:
        sent_characters[chat_id] = []
        available = all_characters

    character = await choose_character_by_rarity(available)
    if not character:
        return

    sent_characters[chat_id].append(character['id'])
    last_characters[chat_id] = character
    character_message_counts[chat_id] = 0
    first_correct_guesses.pop(chat_id, None)

    symbol = rarity_symbol(character.get('rarity'))
    await context.bot.send_photo(
        chat_id=chat_id,
        photo=character['img_url'],
        caption=f"{symbol} Gʀᴇᴀᴛ! ᴀ ɴᴇᴡ ᴡᴀɪғᴜ ʜᴀs ᴊᴜsᴛ ᴀᴘᴘᴇᴀʀᴇᴅ\n\nᴜsᴇ /ɢᴜᴇss ɴᴀᴍᴇ",
        parse_mode='HTML',
    )


async def send_expiry_notice(update: Update, context: CallbackContext, character: dict) -> None:
    keyboard = [[InlineKeyboardButton("Iɴғᴏ", callback_data=f"charinfo:{character.get('id')}")]]
    name = escape(str(character.get('name', 'Unknown')))
    text = f"❄️ <b>Cʜᴀʀᴀᴄᴛᴇʀ Hᴀs Dɪsᴀᴘᴘᴇᴀʀᴇᴅ:</b>\n{name}\n\n<b>Gᴇᴛ Iɴғᴏ:</b>"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def guess(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if chat_id not in last_characters:
        return

    if chat_id in first_correct_guesses:
        await update.message.reply_text('❌️ Already Guessed By Someone.. Try Next Time Bruhh ')
        return

    guess = ' '.join(context.args).lower() if context.args else ''

    if "()" in guess or "&" in guess.lower():
        await update.message.reply_text("Nahh You Can't use This Types of words in your guess..❌️")
        return

    name_parts = last_characters[chat_id]['name'].lower().split()

    if sorted(name_parts) == sorted(guess.split()) or any(part == guess for part in name_parts):

        first_correct_guesses[chat_id] = user_id

        user = await user_collection.find_one({'id': user_id})
        if user:
            update_fields = {}
            if hasattr(update.effective_user, 'username') and update.effective_user.username != user.get('username'):
                update_fields['username'] = update.effective_user.username
            if update.effective_user.first_name != user.get('first_name'):
                update_fields['first_name'] = update.effective_user.first_name
            if update_fields:
                await user_collection.update_one({'id': user_id}, {'$set': update_fields})

            await user_collection.update_one({'id': user_id}, {'$push': {'characters': last_characters[chat_id]}})

        elif hasattr(update.effective_user, 'username'):
            await user_collection.insert_one({
                'id': user_id,
                'username': update.effective_user.username,
                'first_name': update.effective_user.first_name,
                'characters': [last_characters[chat_id]],
            })

        group_user_total = await group_user_totals_collection.find_one({'user_id': user_id, 'group_id': chat_id})
        if group_user_total:
            update_fields = {}
            if hasattr(update.effective_user, 'username') and update.effective_user.username != group_user_total.get('username'):
                update_fields['username'] = update.effective_user.username
            if update.effective_user.first_name != group_user_total.get('first_name'):
                update_fields['first_name'] = update.effective_user.first_name
            if update_fields:
                await group_user_totals_collection.update_one({'user_id': user_id, 'group_id': chat_id}, {'$set': update_fields})

            await group_user_totals_collection.update_one({'user_id': user_id, 'group_id': chat_id}, {'$inc': {'count': 1}})

        else:
            await group_user_totals_collection.insert_one({
                'user_id': user_id,
                'group_id': chat_id,
                'username': update.effective_user.username,
                'first_name': update.effective_user.first_name,
                'count': 1,
            })

        group_info = await top_global_groups_collection.find_one({'group_id': chat_id})
        if group_info:
            update_fields = {}
            if update.effective_chat.title != group_info.get('group_name'):
                update_fields['group_name'] = update.effective_chat.title
            if update_fields:
                await top_global_groups_collection.update_one({'group_id': chat_id}, {'$set': update_fields})

            await top_global_groups_collection.update_one({'group_id': chat_id}, {'$inc': {'count': 1}})

        else:
            await top_global_groups_collection.insert_one({
                'group_id': chat_id,
                'group_name': update.effective_chat.title,
                'count': 1,
            })

        keyboard = [[InlineKeyboardButton("♡ Sᴇᴇ Hᴀʀᴇᴍ", switch_inline_query_current_chat=f"collection.{user_id}")]]
        character = last_characters[chat_id]
        rarity = escape(str(character.get("rarity", "")))
        await update.message.reply_text(
            f'<b><a href="tg://user?id={user_id}">{escape(update.effective_user.first_name)}</a></b> Yᴏᴜ Gᴏᴛ Nᴇᴡ Cʜᴀʀᴀᴄᴛᴇʀ ✅️\n\n'
            f'Cʜᴀʀᴀᴄᴛᴇʀ Nᴀᴍᴇ: {escape(str(character.get("name", "Unknown")))}\n'
            f'Aɴɪᴍᴇ: {escape(str(character.get("anime", "Unknown")))}\n'
            f'Rᴀʀɪᴛʏ: {rarity}\n\n'
            'Tʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ʙᴇᴇɴ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ /ʜᴀʀᴇᴍ.',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        character_message_counts.pop(chat_id, None)
        last_characters.pop(chat_id, None)
        first_correct_guesses.pop(chat_id, None)

    else:
        await update.message.reply_text('Incorrect Name.. ❌️')


async def fav(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text('Please provide Character id...')
        return

    character_id = context.args[0]

    user = await user_collection.find_one({'id': user_id})
    if not user:
        await update.message.reply_text('You have not Guessed any characters yet....')
        return

    character = next((c for c in user['characters'] if c['id'] == character_id), None)
    if not character:
        await update.message.reply_text('This Character is Not In your collection')
        return

    user['favorites'] = [character_id]

    await user_collection.update_one({'id': user_id}, {'$set': {'favorites': user['favorites']}})

    await update.message.reply_text(f'Character {character["name"]} has been added to your favorite...')


async def character_info_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    character_id = query.data.split(":", 1)[1]
    character = await collection.find_one({'id': character_id})
    if not character:
        await query.answer("Character not found.", show_alert=True)
        return
    emoji = str(character.get('emoji') or '').strip()
    name = escape(str(character.get('name', 'Unknown')))
    if emoji:
        name = f"{name} ({escape(emoji)})"
    caption = (
        "[ Character Details ]\n"
        f"• Name: {name}\n"
        f"• Anime: {escape(str(character.get('anime', 'Unknown')))}\n"
        f"• Rarity: {escape(str(character.get('rarity', '⚪ Common')))}\n"
        f"• ID: {escape(str(character.get('id', character_id)))}\n\n"
        f"Requested By: <a href=\"tg://user?id={query.from_user.id}\">{escape(query.from_user.first_name or 'User')}</a>"
    )
    await context.bot.send_photo(
        chat_id=query.message.chat.id,
        photo=character.get('img_url'),
        caption=caption,
        parse_mode='HTML',
    )


async def character_info_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /w <character_id>")
        return
    character = await collection.find_one({'id': str(context.args[0])})
    if not character:
        await update.message.reply_text("Character not found.. ❌️")
        return
    emoji = str(character.get('emoji') or '').strip()
    name = escape(str(character.get('name', 'Unknown')))
    if emoji:
        name = f"{name} ({escape(emoji)})"
    caption = (
        "[ Character Details ]\n"
        f"• Name: {name}\n"
        f"• Anime: {escape(str(character.get('anime', 'Unknown')))}\n"
        f"• Rarity: {escape(str(character.get('rarity', '⚪ Common')))}\n"
        f"• ID: {escape(str(character.get('id', context.args[0])))}\n\n"
        f"Requested By: <a href=\"tg://user?id={update.effective_user.id}\">{escape(update.effective_user.first_name or 'User')}</a>"
    )
    await update.message.reply_photo(photo=character.get('img_url'), caption=caption, parse_mode='HTML')


def register_handlers() -> None:
    """Register all PTB handlers. Must be called before the app starts."""
    application.add_handler(CommandHandler(["guess", "protecc", "collect", "grab", "hunt"], guess, block=False))
    application.add_handler(CommandHandler("fav", fav, block=False))
    application.add_handler(CommandHandler(["w", "info"], character_info_command, block=False))
    application.add_handler(CallbackQueryHandler(character_info_callback, pattern=r"^charinfo:", block=False))
    application.add_handler(MessageHandler(filters.ALL, message_counter, block=False), group=1)


async def _ensure_indexes() -> None:
    """Best-effort index creation for the inline query to stay fast."""
    try:
        from NoxxNetwork.modules.inlinequery import ensure_indexes
        await ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Index creation skipped: %s", exc)


async def runner() -> None:
    """Start Pyrogram and PTB on the SAME event loop and keep them alive."""
    register_handlers()

    await _ensure_indexes()

    await Waifuu.start()
    LOGGER.info("Pyrogram client started")

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    LOGGER.info("Bot started")

    # Block forever — both clients now share this loop.
    await asyncio.Event().wait()


def main() -> None:
    try:
        asyncio.run(runner())
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Shutdown requested")
    finally:
        LOGGER.info("Bot stopped")


if __name__ == "__main__":
    main()