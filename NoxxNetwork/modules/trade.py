import asyncio
import time
import uuid
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler

from NoxxNetwork import user_collection, application
from NoxxNetwork.rarity import rarity_symbol

pending_trades = {}
pending_gifts = {}


def _gift_key(sender_id, receiver_id, token):
    return f"gift:{sender_id}:{receiver_id}:{token}"


# ---------------------------------------------------------------------------
# TRADE
# ---------------------------------------------------------------------------
async def trade(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    sender_id = update.effective_user.id

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("Rᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛʀᴀᴅᴇ ᴡɪᴛʜ.")
        return

    receiver_id = message.reply_to_message.from_user.id
    if sender_id == receiver_id:
        await message.reply_text("Yᴏᴜ ᴄᴀɴ'ᴛ ᴛʀᴀᴅᴇ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴡɪᴛʜ ʏᴏᴜʀsᴇʟғ!")
        return

    if len(context.args) != 2:
        await message.reply_text("U sᴀɢᴇ: /trade <your_id> <their_id>")
        return

    sender_character_id = str(context.args[0])
    receiver_character_id = str(context.args[1])

    sender = await user_collection.find_one({'id': sender_id})
    receiver = await user_collection.find_one({'id': receiver_id})

    if not sender or not receiver:
        await message.reply_text("Bᴏᴛʜ ᴜsᴇʀs ᴍᴜsᴛ ʜᴀᴠᴇ ᴀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ.")
        return

    sender_character = next(
        (c for c in sender.get('characters', []) if str(c.get('id')) == sender_character_id),
        None,
    )
    receiver_character = next(
        (c for c in receiver.get('characters', []) if str(c.get('id')) == receiver_character_id),
        None,
    )

    if not sender_character:
        await message.reply_text("Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴛʜᴀᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ.")
        return
    if not receiver_character:
        await message.reply_text("Tʜᴇ ᴏᴛʜᴇʀ ᴜsᴇʀ ᴅᴏᴇsɴ'ᴛ ʜᴀᴠᴇ ᴛʜᴀᴛ ᴄʜᴀʀᴀᴄᴛᴇʀ.")
        return

    token = uuid.uuid4().hex[:10]
    key = (sender_id, receiver_id, token)
    pending_trades[key] = {
        'sender_character_id': sender_character_id,
        'receiver_character_id': receiver_character_id,
        'expires_at': time.monotonic() + 120,
    }

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Cᴏɴғɪʀᴍ Tʀᴀᴅᴇ", callback_data=f"trade:confirm:{sender_id}:{receiver_id}:{token}")],
        [InlineKeyboardButton("❌ Cᴀɴᴄᴇʟ Tʀᴀᴅᴇ", callback_data=f"trade:cancel:{sender_id}:{receiver_id}:{token}")],
    ])

    await message.reply_text(
        f"🤝 <b>Tʀᴀᴅᴇ Rᴇǫᴜᴇsᴛ</b>\n\n"
        f"Yᴏᴜ ᴏғғᴇʀ: <b>{escape(str(sender_character.get('name', 'Unknown')))}</b>\n"
        f"Yᴏᴜ ʀᴇᴄᴇɪᴠᴇ: <b>{escape(str(receiver_character.get('name', 'Unknown')))}</b>\n\n"
        f"Tʜᴇ ᴛʀᴀᴅᴇ ᴇxᴘɪʀᴇs ɪɴ 2 ᴍɪɴᴜᴛᴇs.",
        parse_mode='HTML',
        reply_markup=markup,
    )


async def trade_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    parts = query.data.split(':')

    if len(parts) != 5:
        await query.answer("Invalid trade.", show_alert=True)
        return

    # trade:ACTION:SENDER:RECEIVER:TOKEN
    _, action, sender_id_s, receiver_id_s, token = parts
    sender_id, receiver_id = int(sender_id_s), int(receiver_id_s)

    if query.from_user.id != receiver_id:
        await query.answer("Only the receiving user can accept this trade.", show_alert=True)
        return

    key = (sender_id, receiver_id, token)
    trade_data = pending_trades.get(key)

    if not trade_data:
        await query.answer("This trade has expired or was cancelled.", show_alert=True)
        return

    if time.monotonic() >= trade_data['expires_at']:
        pending_trades.pop(key, None)
        await query.answer("This trade has expired.", show_alert=True)
        try:
            await query.message.edit_text("❌ Tʀᴀᴅᴇ Exᴘɪʀᴇᴅ")
        except Exception:
            pass
        return

    if action == 'cancel':
        pending_trades.pop(key, None)
        await query.answer("Trade cancelled.")
        try:
            await query.message.edit_text("❌ Tʀᴀᴅᴇ Cᴀɴᴄᴇʟʟᴇᴅ")
        except Exception:
            pass
        return

    sender = await user_collection.find_one({'id': sender_id})
    receiver = await user_collection.find_one({'id': receiver_id})

    if not sender or not receiver:
        pending_trades.pop(key, None)
        await query.answer("User collection not found.", show_alert=True)
        return

    sid, rid = trade_data['sender_character_id'], trade_data['receiver_character_id']

    sender_chars = list(sender.get('characters', []))
    receiver_chars = list(receiver.get('characters', []))

    s_idx = next((i for i, c in enumerate(sender_chars) if str(c.get('id')) == sid), None)
    r_idx = next((i for i, c in enumerate(receiver_chars) if str(c.get('id')) == rid), None)

    if s_idx is None or r_idx is None:
        pending_trades.pop(key, None)
        await query.answer("One of the characters is no longer available.", show_alert=True)
        return

    sender_character = sender_chars.pop(s_idx)
    receiver_character = receiver_chars.pop(r_idx)

    sender_chars.append(receiver_character)
    receiver_chars.append(sender_character)

    await user_collection.update_one({'id': sender_id}, {'$set': {'characters': sender_chars}})
    await user_collection.update_one({'id': receiver_id}, {'$set': {'characters': receiver_chars}})

    pending_trades.pop(key, None)

    await query.answer("Trade completed!")
    try:
        await query.message.edit_text("🤝 Tʀᴀᴅᴇ Cᴏᴍᴘʟᴇᴛᴇᴅ Sᴜᴄᴄᴇssғᴜʟʟʏ! ✅")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GIFT
# ---------------------------------------------------------------------------
async def gift(update: Update, context: CallbackContext) -> None:
    message = update.effective_message
    sender_id = update.effective_user.id

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("Rᴇᴘʟʏ ᴛᴏ ᴛʜᴇ ᴜsᴇʀ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ɢɪғᴛ ᴛᴏ.")
        return

    receiver = message.reply_to_message.from_user
    receiver_id = receiver.id

    if sender_id == receiver_id:
        await message.reply_text("Yᴏᴜ ᴄᴀɴ'ᴛ ɢɪғᴛ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴛᴏ ʏᴏᴜʀsᴇʟғ!")
        return

    if len(context.args) != 1:
        await message.reply_text("U sᴀɢᴇ: /gift <character_id>")
        return

    character_id = str(context.args[0])

    sender = await user_collection.find_one({'id': sender_id})
    if not sender or not sender.get('characters'):
        await message.reply_text("Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴄʜᴀʀᴀᴄᴛᴇʀs.")
        return

    character = next(
        (c for c in sender['characters'] if str(c.get('id')) == character_id),
        None,
    )
    if not character:
        await message.reply_text("Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ.")
        return

    token = uuid.uuid4().hex[:10]
    key = (sender_id, receiver_id, token)

    gift_data = {
        'character': character,
        'receiver_username': receiver.username,
        'receiver_first_name': receiver.first_name or 'User',
        'expires_at': time.monotonic() + 120,
    }
    pending_gifts[key] = gift_data

    name = escape(str(character.get('name', 'Unknown')))
    emoji = str(character.get('emoji') or '').strip()
    if emoji:
        name += f" ({escape(emoji)})"

    symbol = escape(rarity_symbol(character.get('rarity')))
    rarity = escape(str(character.get('rarity', 'Unknown')))

    caption = (
        f"<b>{name}</b>\n"
        f"Rᴀʀɪᴛʏ: {symbol} {rarity}\n"
        f"Aɴɪᴍᴇ: {escape(str(character.get('anime', 'Unknown')))}\n"
        f"ID: {escape(str(character.get('id', character_id)))}"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Cᴏɴғɪʀᴍ Gɪғᴛ",
            callback_data=_gift_key(sender_id, receiver_id, token) + ':confirm',
        )],
        [InlineKeyboardButton(
            "❌ Cᴀɴᴄᴇʟ Gɪғᴛ",
            callback_data=_gift_key(sender_id, receiver_id, token) + ':cancel',
        )],
    ])

    image_url = character.get('img_url') or character.get('image') or character.get('img')

    if image_url:
        sent = await message.reply_photo(
            photo=image_url,
            caption=caption,
            parse_mode='HTML',
            reply_markup=markup,
        )
    else:
        sent = await message.reply_text(caption, parse_mode='HTML', reply_markup=markup)

    gift_data['message_id'] = sent.message_id
    gift_data['chat_id'] = message.chat.id

    asyncio.create_task(_expire_gift(context, key, gift_data))


async def _expire_gift(context: CallbackContext, key, gift_data):
    await asyncio.sleep(max(0, gift_data['expires_at'] - time.monotonic()))
    if pending_gifts.get(key) is not gift_data:
        return
    pending_gifts.pop(key, None)

    text = "❌ <b>Gɪғᴛ Exᴘɪʀᴇᴅ</b>\n\nTʜᴇ 2-ᴍɪɴᴜᴛᴇ ᴛɪᴍᴇʟɪᴍɪᴛ ʜᴀs ᴘᴀssᴇᴅ."
    try:
        await context.bot.edit_message_caption(
            chat_id=gift_data['chat_id'],
            message_id=gift_data['message_id'],
            caption=text,
            parse_mode='HTML',
            reply_markup=None,
        )
    except Exception:
        try:
            await context.bot.edit_message_text(
                chat_id=gift_data['chat_id'],
                message_id=gift_data['message_id'],
                text=text,
                parse_mode='HTML',
                reply_markup=None,
            )
        except Exception:
            pass


async def gift_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    parts = query.data.split(':')

    if len(parts) != 5:
        await query.answer("Invalid gift request.", show_alert=True)
        return

    # 🔥 FIX: gift:SENDER:RECEIVER:TOKEN:ACTION (action LAST me hai)
    _, sender_id_s, receiver_id_s, token, action = parts
    sender_id, receiver_id = int(sender_id_s), int(receiver_id_s)

    if query.from_user.id != receiver_id:
        await query.answer("Only the receiver can accept this gift.", show_alert=True)
        return

    key = (sender_id, receiver_id, token)
    gift_data = pending_gifts.get(key)

    if not gift_data:
        await query.answer("This gift has expired or was cancelled.", show_alert=True)
        return

    if time.monotonic() >= gift_data['expires_at']:
        pending_gifts.pop(key, None)
        await query.answer("This gift has expired.", show_alert=True)
        return

    if action == 'cancel':
        pending_gifts.pop(key, None)
        await query.answer("Gift cancelled.")
        try:
            await query.message.edit_caption(
                "❌ <b>Gɪғᴛ Cᴀɴᴄᴇʟʟᴇᴅ</b>\n\nTʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ɴᴏᴛ ʙᴇᴇɴ sᴇɴᴛ.",
                parse_mode='HTML',
                reply_markup=None,
            )
        except Exception:
            try:
                await query.message.edit_text("❌ Gɪғᴛ Cᴀɴᴄᴇʟʟᴇᴅ", reply_markup=None)
            except Exception:
                pass
        return

    sender = await user_collection.find_one({'id': sender_id})
    if not sender:
        pending_gifts.pop(key, None)
        await query.answer("Sender collection not found.", show_alert=True)
        return

    character = gift_data['character']
    sender_chars = list(sender.get('characters', []))
    idx = next(
        (i for i, c in enumerate(sender_chars) if str(c.get('id')) == str(character.get('id'))),
        None,
    )

    if idx is None:
        pending_gifts.pop(key, None)
        await query.answer("The sender no longer has this character.", show_alert=True)
        return

    sender_chars.pop(idx)
    await user_collection.update_one({'id': sender_id}, {'$set': {'characters': sender_chars}})

    receiver = await user_collection.find_one({'id': receiver_id})
    if receiver:
        await user_collection.update_one(
            {'id': receiver_id}, {'$push': {'characters': character}}
        )
    else:
        await user_collection.insert_one({
            'id': receiver_id,
            'username': gift_data['receiver_username'],
            'first_name': gift_data['receiver_first_name'],
            'characters': [character],
        })

    pending_gifts.pop(key, None)

    await query.answer("Gift accepted successfully!")

    receiver_mention = (
        f'<a href="tg://user?id={receiver_id}">'
        f'{escape(gift_data["receiver_first_name"])}</a>'
    )
    success = f"🎁 <b>Gɪғᴛ sᴜᴄᴄᴇssғᴜʟʟʏ sᴇɴᴛ ᴛᴏ</b>\n{receiver_mention}"

    try:
        await query.message.edit_caption(success, parse_mode='HTML', reply_markup=None)
    except Exception:
        try:
            await query.message.edit_text(success, parse_mode='HTML', reply_markup=None)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HANDLER REGISTRATION
# ---------------------------------------------------------------------------
application.add_handler(CommandHandler("trade", trade, block=False))
application.add_handler(CallbackQueryHandler(trade_callback, pattern=r'^trade:', block=False))

application.add_handler(CommandHandler("gift", gift, block=False))
application.add_handler(CallbackQueryHandler(gift_callback, pattern=r'^gift:', block=False))
