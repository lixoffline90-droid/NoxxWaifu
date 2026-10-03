from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from html import escape
import asyncio
import time

from NoxxNetwork import user_collection, Waifuu

pending_trades = {}


@Waifuu.on_message(filters.command("trade"))
async def trade(client, message):
    sender_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("You need to reply to a user's message to trade a character!")
        return

    receiver_id = message.reply_to_message.from_user.id

    if sender_id == receiver_id:
        await message.reply_text("You can't trade a character with yourself!")
        return

    if len(message.command) != 3:
        await message.reply_text("You need to provide two character IDs!")
        return

    sender_character_id, receiver_character_id = message.command[1], message.command[2]

    sender = await user_collection.find_one({'id': sender_id})
    receiver = await user_collection.find_one({'id': receiver_id})

    sender_character = next((character for character in sender['characters'] if character['id'] == sender_character_id), None)
    receiver_character = next((character for character in receiver['characters'] if character['id'] == receiver_character_id), None)

    if not sender_character:
        await message.reply_text("You don't have the character you're trying to trade!")
        return

    if not receiver_character:
        await message.reply_text("The other user doesn't have the character they're trying to trade!")
        return






    if len(message.command) != 3:
        await message.reply_text("/trade [Your Character ID] [Other User Character ID]!")
        return

    sender_character_id, receiver_character_id = message.command[1], message.command[2]

    
    pending_trades[(sender_id, receiver_id)] = (sender_character_id, receiver_character_id)

    
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Confirm Trade", callback_data="confirm_trade")],
            [InlineKeyboardButton("Cancel Trade", callback_data="cancel_trade")]
        ]
    )

    await message.reply_text(f"{message.reply_to_message.from_user.mention}, do you accept this trade?", reply_markup=keyboard)


@Waifuu.on_callback_query(filters.create(lambda _, __, query: query.data in ["confirm_trade", "cancel_trade"]))
async def on_callback_query(client, callback_query):
    receiver_id = callback_query.from_user.id

    
    for (sender_id, _receiver_id), (sender_character_id, receiver_character_id) in pending_trades.items():
        if _receiver_id == receiver_id:
            break
    else:
        await callback_query.answer("This is not for you!", show_alert=True)
        return

    if callback_query.data == "confirm_trade":
        
        sender = await user_collection.find_one({'id': sender_id})
        receiver = await user_collection.find_one({'id': receiver_id})

        sender_character = next((character for character in sender['characters'] if character['id'] == sender_character_id), None)
        receiver_character = next((character for character in receiver['characters'] if character['id'] == receiver_character_id), None)

        
        
        sender['characters'].remove(sender_character)
        receiver['characters'].remove(receiver_character)

        
        await user_collection.update_one({'id': sender_id}, {'$set': {'characters': sender['characters']}})
        await user_collection.update_one({'id': receiver_id}, {'$set': {'characters': receiver['characters']}})

        
        sender['characters'].append(receiver_character)
        receiver['characters'].append(sender_character)

        
        await user_collection.update_one({'id': sender_id}, {'$set': {'characters': sender['characters']}})
        await user_collection.update_one({'id': receiver_id}, {'$set': {'characters': receiver['characters']}})

        
        del pending_trades[(sender_id, receiver_id)]

        await callback_query.message.edit_text(f"You have successfully traded your character with {callback_query.message.reply_to_message.from_user.mention}!")

    elif callback_query.data == "cancel_trade":
        
        del pending_trades[(sender_id, receiver_id)]

        await callback_query.message.edit_text("❌️ Sad Cancelled....")




pending_gifts = {}


@Waifuu.on_message(filters.command("gift"))
async def gift(client, message):
    sender_id = message.from_user.id

    if not message.reply_to_message:
        await message.reply_text("You need to reply to a user's message to gift a character!")
        return

    receiver_id = message.reply_to_message.from_user.id
    receiver_username = message.reply_to_message.from_user.username
    receiver_first_name = message.reply_to_message.from_user.first_name or "User"

    if sender_id == receiver_id:
        await message.reply_text("You can't gift a character to yourself!")
        return

    if len(message.command) != 2:
        await message.reply_text("Usage: /gift <character_id>")
        return

    character_id = message.command[1]
    sender = await user_collection.find_one({'id': sender_id})

    if not sender or not sender.get('characters'):
        await message.reply_text("You don't have any characters in your collection!")
        return

    character = next(
        (character for character in sender['characters'] if str(character.get('id')) == str(character_id)),
        None
    )

    if not character:
        await message.reply_text("You don't have this character in your collection!")
        return

    pending_gifts[(sender_id, receiver_id)] = {
        'character': character,
        'receiver_username': receiver_username,
        'receiver_first_name': receiver_first_name,
        'expires_at': time.monotonic() + 120,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Cᴏɴғɪʀᴍ Gɪғᴛ", callback_data="confirm_gift")],
            [InlineKeyboardButton("❌ Cᴀɴᴄᴇʟ Gɪғᴛ", callback_data="cancel_gift")],
        ]
    )

    caption = (
        f"<b>{escape(str(character.get('name', 'Unknown')))} (🌸)</b>\n"
        f"Rarity: {escape(str(character.get('rarity', 'Unknown')))}\n"
        f"Anime: {escape(str(character.get('anime', 'Unknown')))}\n"
        f"ID: <code>{escape(str(character.get('id', character_id)))}</code>"
    )

    caption += "\n\n⏳ <b>Cᴏɴғɪʀᴍ ᴡɪᴛʜɪɴ 2 ᴍɪɴᴜᴛᴇs</b>"

    image_url = character.get('img_url') or character.get('image') or character.get('img')
    if image_url:
        sent_message = await message.reply_photo(
            photo=image_url,
            caption=caption,
            parse_mode='HTML',
            reply_markup=keyboard,
        )
    else:
        sent_message = await message.reply_text(
            caption,
            parse_mode='HTML',
            reply_markup=keyboard,
        )

    asyncio.create_task(_expire_gift((sender_id, receiver_id), pending_gifts[(sender_id, receiver_id)], sent_message))


async def _expire_gift(key, gift, sent_message):
    """Automatically cancel a pending gift after 2 minutes."""
    await asyncio.sleep(120)

    # Do not let an old timer cancel a newer gift from the same sender/receiver.
    if pending_gifts.get(key) is not gift:
        return

    pending_gifts.pop(key, None)
    caption = "❌ <b>Gɪғᴛ Exᴘɪʀᴇᴅ</b>\n\nTʜᴇ 2-ᴍɪɴᴜᴛᴇ ᴛɪᴍᴇʟɪᴍɪᴛ ʜᴀs ᴘᴀssᴇᴅ. Tʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ɴᴏᴛ ʙᴇᴇɴ sᴇɴᴛ."
    try:
        if sent_message.photo:
            await sent_message.edit_caption(caption=caption, parse_mode='HTML', reply_markup=None)
        else:
            await sent_message.edit_text(caption, parse_mode='HTML', reply_markup=None)
    except Exception:
        pass


@Waifuu.on_callback_query(filters.create(lambda _, __, query: query.data in ["confirm_gift", "cancel_gift"]))
async def on_callback_query(client, callback_query):
    sender_id = callback_query.from_user.id

    pending_key = next(
        ((sender_id, receiver_id), gift)
        for (gift_sender_id, receiver_id), gift in pending_gifts.items()
        if gift_sender_id == sender_id
    ) if any(gift_sender_id == sender_id for gift_sender_id, _ in pending_gifts) else None

    if not pending_key:
        await callback_query.answer("This gift request is no longer available.", show_alert=True)
        return

    (sender_id, receiver_id), gift = pending_key

    if time.monotonic() >= gift.get('expires_at', 0):
        pending_gifts.pop((sender_id, receiver_id), None)
        await callback_query.answer("This gift has expired.", show_alert=True)
        try:
            expired_caption = "❌ <b>Gɪғᴛ Exᴘɪʀᴇᴅ</b>\n\nTʜᴇ 2-ᴍɪɴᴜᴛᴇ ᴛɪᴍᴇʟɪᴍɪᴛ ʜᴀs ᴘᴀssᴇᴅ. Tʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ɴᴏᴛ ʙᴇᴇɴ sᴇɴᴛ."
            if callback_query.message.photo:
                await callback_query.message.edit_caption(caption=expired_caption, parse_mode='HTML', reply_markup=None)
            else:
                await callback_query.message.edit_text(expired_caption, parse_mode='HTML', reply_markup=None)
        except Exception:
            pass
        return

    if callback_query.data == "confirm_gift":
        sender = await user_collection.find_one({'id': sender_id})
        receiver = await user_collection.find_one({'id': receiver_id})

        if not sender or not any(
            str(character.get('id')) == str(gift['character'].get('id'))
            for character in sender.get('characters', [])
        ):
            del pending_gifts[(sender_id, receiver_id)]
            await callback_query.answer("You no longer have this character.", show_alert=True)
            return

        sender['characters'].remove(gift['character'])
        await user_collection.update_one(
            {'id': sender_id},
            {'$set': {'characters': sender['characters']}}
        )

        if receiver:
            await user_collection.update_one(
                {'id': receiver_id},
                {'$push': {'characters': gift['character']}}
            )
        else:
            await user_collection.insert_one({
                'id': receiver_id,
                'username': gift['receiver_username'],
                'first_name': gift['receiver_first_name'],
                'characters': [gift['character']],
            })

        del pending_gifts[(sender_id, receiver_id)]
        await callback_query.answer("Gift sent successfully!", show_alert=False)

        receiver_mention = f'<a href="tg://user?id={receiver_id}">{escape(gift["receiver_first_name"])}</a>'
        success_caption = f"🎁 <b>Gɪғᴛ sᴜᴄᴄᴇssғᴜʟʟʏ sᴇɴᴛ ᴛᴏ</b>\n{receiver_mention}"

        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption=success_caption,
                parse_mode='HTML',
                reply_markup=None,
            )
        else:
            await callback_query.message.edit_text(
                success_caption,
                parse_mode='HTML',
                reply_markup=None,
            )

    else:
        del pending_gifts[(sender_id, receiver_id)]
        await callback_query.answer("Gift cancelled.", show_alert=False)

        cancel_caption = "❌ <b>Gɪғᴛ Cᴀɴᴄᴇʟʟᴇᴅ</b>\n\nTʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ʜᴀs ɴᴏᴛ ʙᴇᴇɴ sᴇɴᴛ."
        if callback_query.message.photo:
            await callback_query.message.edit_caption(
                caption=cancel_caption,
                parse_mode='HTML',
                reply_markup=None,
            )
        else:
            await callback_query.message.edit_text(
                cancel_caption,
                parse_mode='HTML',
                reply_markup=None,
            )

