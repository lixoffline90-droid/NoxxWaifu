import urllib.request
from pymongo import ReturnDocument

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    sudo_users,
    collection,
    user_collection,
    db,
    CHARA_CHANNEL_ID,
    SUPPORT_CHAT,
    LOGGER,
)
from NoxxNetwork.rarity import (
    RARITIES,
    rarity_text,
    set_probability,
    get_probability_table,
)

WRONG_FORMAT_TEXT = """Wrong ❌️ format...

/upload <img_url> <character-name> <anime-name> <rarity-number>

🔹 Rarities:
1. ⚪ Common
2. 🌟 Galaxies
3. 🌤️ Summer
4. 🍬 Galactic
5. 🎄 Christmas
6. 🎨 Holi edition
7. 🐦‍🔥 Marvelous
8. 💮 Exclusive
9. 🔖 Manga rush
10. 🔮 Mythical
11. 🛖 Tribe
12. 🛷 X-Mas
13. 🟡 Legendary
14. 🟢 Medium
15. 🟣 Rare
16. 🧣 Winters
17. 🪁 Skyrise
18. 🪔 Diwali edition
19. 🪢 Corrupted
20. 🪼 Exotic
21. 🫧 Special"""


def _clear_inline_cache():
    """Clear the inline query character cache so new uploads appear immediately."""
    try:
        from NoxxNetwork.modules.inlinequery import all_characters_cache
        all_characters_cache.clear()
    except Exception as e:
        LOGGER.warning(f"Could not clear inline cache: {e}")


async def get_next_sequence_number(sequence_name):
    sequence_collection = db.sequences
    sequence_document = await sequence_collection.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'sequence_value': 1}},
        return_document=ReturnDocument.AFTER,
    )
    if not sequence_document:
        await sequence_collection.insert_one({'_id': sequence_name, 'sequence_value': 0})
        return 0
    return sequence_document['sequence_value']


# ---------------------------------------------------------------------------
# /upload
# ---------------------------------------------------------------------------
async def upload(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask My Owner...')
        return

    try:
        args = context.args
        if len(args) != 4:
            await update.message.reply_text(WRONG_FORMAT_TEXT)
            return

        character_name = args[1].replace('-', ' ').title()
        anime = args[2].replace('-', ' ').title()

        try:
            urllib.request.urlopen(args[0])
        except Exception:
            await update.message.reply_text('Invalid URL.')
            return

        try:
            rarity = rarity_text(int(args[3]))
        except (KeyError, ValueError):
            await update.message.reply_text("Invalid rarity. Please use a number from 1 to 21.")
            return

        id = str(await get_next_sequence_number('character_id')).zfill(2)

        character = {
            'img_url': args[0],
            'name': character_name,
            'anime': anime,
            'rarity': rarity,
            'id': id,
        }

        caption = (
            f'<b>Character Name:</b> {character_name}\n'
            f'<b>Anime Name:</b> {anime}\n'
            f'<b>Rarity:</b> {rarity}\n'
            f'<b>ID:</b> {id}\n'
            f'Added by <a href="tg://user?id={update.effective_user.id}">'
            f'{update.effective_user.first_name}</a>'
        )

        try:
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=args[0],
                caption=caption,
                parse_mode='HTML',
            )
            character['message_id'] = message.message_id
            await collection.insert_one(character)

            # 🔥 Clear inline cache so new character shows up immediately
            _clear_inline_cache()

            await update.message.reply_text(
                f'✅ CHARACTER ADDED with ID <code>{id}</code>',
                parse_mode='HTML',
            )
        except Exception as channel_error:
            LOGGER.warning(f"Channel send failed, saving to DB only: {channel_error}")
            await collection.insert_one(character)

            # 🔥 Clear inline cache
            _clear_inline_cache()

            await update.message.reply_text(
                f"✅ Character Added (ID <code>{id}</code>) but no Database Channel Found.",
                parse_mode='HTML',
            )

    except Exception as e:
        await update.message.reply_text(
            f'Character Upload Unsuccessful. Error: {str(e)}\n'
            f'If you think this is a source error, forward to: {SUPPORT_CHAT}'
        )


# ---------------------------------------------------------------------------
# DELETE — Bulletproof: DB delete is ALWAYS priority
# ---------------------------------------------------------------------------
async def delete(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask my Owner to use this Command...')
        return

    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Incorrect format... Please use: /delete <character_id>')
            return

        raw_id = str(args[0]).strip()

        # Try multiple ID variants
        character = None
        candidates = [raw_id, raw_id.zfill(2), raw_id.lstrip('0') or '0']
        for candidate in candidates:
            character = await collection.find_one({'id': candidate})
            if character:
                raw_id = candidate
                break

        if not character:
            await update.message.reply_text(
                f"❌ Character with ID <code>{raw_id}</code> not found in database.",
                parse_mode='HTML',
            )
            return

        character_id = character['id']
        character_name = character.get('name', 'Unknown')
        old_message_id = character.get('message_id')

        # 1️⃣ Delete from main characters collection (ALWAYS)
        delete_result = await collection.delete_one({'id': character_id})
        if delete_result.deleted_count == 0:
            await update.message.reply_text("❌ Failed to delete from database.")
            return

        # 2️⃣ Pull from ALL user collections
        removed_from_users = 0
        try:
            result = await user_collection.update_many(
                {},
                {'$pull': {'characters': {'id': character_id}}},
            )
            removed_from_users = result.modified_count
        except Exception as e:
            LOGGER.warning(f"Failed to pull from user collections: {e}")

        # 3️⃣ Try channel delete (best effort)
        channel_status = "ℹ️ No channel message linked"
        if old_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=CHARA_CHANNEL_ID,
                    message_id=old_message_id,
                )
                channel_status = "📢 Channel message deleted"
            except Exception as e:
                err = str(e).lower()
                if "message to delete not found" in err or "not found" in err:
                    channel_status = "ℹ️ Channel message not found (channel changed or already deleted)"
                elif "not enough rights" in err or "chat not found" in err or "bot was kicked" in err:
                    channel_status = "⚠️ Channel: bot not admin / not in channel"
                else:
                    channel_status = f"⚠️ Channel delete failed"

        # 🔥 Clear inline cache
        _clear_inline_cache()

        # 4️⃣ Report
        lines = [
            "✅ <b>Character Deleted</b>",
            "",
            f"🆔 ID: <code>{character_id}</code>",
            f"📛 Name: <b>{character_name}</b>",
            f"👥 Removed from {removed_from_users} user collection(s)",
            channel_status,
        ]
        await update.message.reply_text("\n".join(lines), parse_mode='HTML')

    except Exception as e:
        LOGGER.exception("Delete command failed")
        await update.message.reply_text(f'❌ Error: {str(e)}')


# ---------------------------------------------------------------------------
# /update <id> <field> <value>
# ---------------------------------------------------------------------------
async def update_character(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('You do not have permission to use this command.')
        return

    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text('Incorrect format. Please use: /update id field new_value')
            return

        character_id = str(args[0]).strip()

        character = await collection.find_one({'id': character_id})
        if not character:
            padded = character_id.zfill(2)
            character = await collection.find_one({'id': padded})
            if character:
                character_id = padded

        if not character:
            await update.message.reply_text('Character not found.')
            return

        valid_fields = ['img_url', 'name', 'anime', 'rarity', 'emoji']
        if args[1] not in valid_fields:
            await update.message.reply_text(
                f'Invalid field. Please use one of the following: {", ".join(valid_fields)}'
            )
            return

        if args[1] in ['name', 'anime']:
            new_value = args[2].replace('-', ' ').title()
        elif args[1] == 'rarity':
            try:
                new_value = rarity_text(int(args[2]))
            except (KeyError, ValueError):
                await update.message.reply_text("Invalid rarity. Please use a number from 1 to 21.")
                return
        else:
            new_value = args[2]

        await collection.find_one_and_update(
            {'id': character_id}, {'$set': {args[1]: new_value}}
        )

        updated_character = dict(character)
        updated_character[args[1]] = new_value

        new_caption = (
            f'<b>Character Name:</b> {updated_character["name"]}\n'
            f'<b>Anime Name:</b> {updated_character["anime"]}\n'
            f'<b>Rarity:</b> {updated_character["rarity"]}\n'
            f'<b>ID:</b> {updated_character["id"]}\n'
            f'Updated by <a href="tg://user?id={update.effective_user.id}">'
            f'{update.effective_user.first_name}</a>'
        )

        old_message_id = character.get('message_id')

        if args[1] == 'img_url':
            if old_message_id:
                try:
                    await context.bot.delete_message(
                        chat_id=CHARA_CHANNEL_ID, message_id=old_message_id
                    )
                except Exception as e:
                    LOGGER.warning(f"Old channel message delete failed: {e}")

            try:
                message = await context.bot.send_photo(
                    chat_id=CHARA_CHANNEL_ID,
                    photo=new_value,
                    caption=new_caption,
                    parse_mode='HTML',
                )
                await collection.find_one_and_update(
                    {'id': character_id}, {'$set': {'message_id': message.message_id}}
                )
            except Exception as e:
                LOGGER.warning(f"Channel update failed: {e}")
        else:
            if old_message_id:
                try:
                    await context.bot.edit_message_caption(
                        chat_id=CHARA_CHANNEL_ID,
                        message_id=old_message_id,
                        caption=new_caption,
                        parse_mode='HTML',
                    )
                except Exception as e:
                    LOGGER.warning(f"Channel caption edit failed (channel changed?): {e}")

        # 🔥 Clear inline cache
        _clear_inline_cache()

        await update.message.reply_text(
            f'✅ Updated <code>{args[1]}</code> for character <code>{character_id}</code>.',
            parse_mode='HTML',
        )

    except Exception as e:
        LOGGER.exception("Update command failed")
        await update.message.reply_text(f'Error: {e}')


# ---------------------------------------------------------------------------
# /resync — re-upload all characters to current channel
# ---------------------------------------------------------------------------
async def resync_channel(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask my Owner to use this Command...')
        return

    status = await update.message.reply_text(
        "🔄 Starting channel resync... This may take a while."
    )

    total = 0
    updated = 0
    failed = 0

    async for char in collection.find({}):
        total += 1
        try:
            caption = (
                f'<b>Character Name:</b> {char.get("name", "Unknown")}\n'
                f'<b>Anime Name:</b> {char.get("anime", "Unknown")}\n'
                f'<b>Rarity:</b> {char.get("rarity", "Unknown")}\n'
                f'<b>ID:</b> {char.get("id")}\n'
                f'Resynced by <a href="tg://user?id={update.effective_user.id}">'
                f'{update.effective_user.first_name}</a>'
            )
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=char['img_url'],
                caption=caption,
                parse_mode='HTML',
            )
            await collection.update_one(
                {'id': char['id']},
                {'$set': {'message_id': message.message_id}},
            )
            updated += 1
        except Exception as e:
            LOGGER.warning(f"Resync failed for {char.get('id')}: {e}")
            failed += 1

        import asyncio
        await asyncio.sleep(1.5)

        if (updated + failed) % 10 == 0:
            try:
                await status.edit_text(
                    f"🔄 Resyncing...\n"
                    f"✅ Updated: {updated}\n"
                    f"❌ Failed: {failed}\n"
                    f"📊 Total: {total}"
                )
            except Exception:
                pass

    await status.edit_text(
        f"✅ <b>Resync Complete</b>\n\n"
        f"📊 Total: {total}\n"
        f"✅ Updated: {updated}\n"
        f"❌ Failed: {failed}",
        parse_mode='HTML',
    )


# ---------------------------------------------------------------------------
# Rarity probability
# ---------------------------------------------------------------------------
async def set_rarity_probability(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text("Ask My Owner...")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setrarity <rarity_number> <probability>")
        return
    try:
        number = int(context.args[0])
        probability = float(context.args[1])
        if number not in RARITIES or probability < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Use a rarity number 1-21 and a probability of 0 or more.")
        return
    await set_probability(number, probability)
    emoji, name = RARITIES[number]
    await update.message.reply_text(f"{emoji} {name} probability set to {probability:g}.")


async def show_rarity_probabilities(update: Update, context: CallbackContext) -> None:
    probabilities = await get_probability_table()
    lines = ["🔹 <b>Rᴀʀɪᴛʏ Pʀᴏʙᴀʙɪʟɪᴛɪᴇs</b>", ""]
    for number, (emoji, name) in RARITIES.items():
        lines.append(f"{number}. {emoji} {name} — <b>{probabilities.get(number, 0):g}</b>")
    lines.append("\n<code>/setrarity 10 3</code> to change one.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
UPLOAD_HANDLER = CommandHandler('upload', upload, block=False)
application.add_handler(UPLOAD_HANDLER)

DELETE_HANDLER = CommandHandler('delete', delete, block=False)
application.add_handler(DELETE_HANDLER)

UPDATE_HANDLER = CommandHandler('update', update_character, block=False)
application.add_handler(UPDATE_HANDLER)

RESYNC_HANDLER = CommandHandler('resync', resync_channel, block=False)
application.add_handler(RESYNC_HANDLER)

SET_RARITY_HANDLER = CommandHandler(
    ['setrarity', 'setrarityprob'], set_rarity_probability, block=False
)
application.add_handler(SET_RARITY_HANDLER)

RARITY_HANDLER = CommandHandler('rarities', show_rarity_probabilities, block=False)
application.add_handler(RARITY_HANDLER)
