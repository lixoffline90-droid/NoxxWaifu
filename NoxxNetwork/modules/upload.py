import urllib.request
from pymongo import ReturnDocument

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import application, sudo_users, collection, db, CHARA_CHANNEL_ID, SUPPORT_CHAT
from NoxxNetwork.rarity import RARITIES, rarity_text, normalize_rarity, set_probability, get_probability_table

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



async def get_next_sequence_number(sequence_name):
    sequence_collection = db.sequences
    sequence_document = await sequence_collection.find_one_and_update(
        {'_id': sequence_name}, 
        {'$inc': {'sequence_value': 1}}, 
        return_document=ReturnDocument.AFTER
    )
    if not sequence_document:
        await sequence_collection.insert_one({'_id': sequence_name, 'sequence_value': 0})
        return 0
    return sequence_document['sequence_value']

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
        except:
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
            'id': id
        }

        try:
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=args[0],
                caption=f'<b>Character Name:</b> {character_name}\n<b>Anime Name:</b> {anime}\n<b>Rarity:</b> {rarity}\n<b>ID:</b> {id}\nAdded by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                parse_mode='HTML'
            )
            character['message_id'] = message.message_id
            await collection.insert_one(character)
            await update.message.reply_text('CHARACTER ADDED....')
        except:
            await collection.insert_one(character)
            update.effective_message.reply_text("Character Added but no Database Channel Found, Consider adding one.")
        
    except Exception as e:
        await update.message.reply_text(f'Character Upload Unsuccessful. Error: {str(e)}\nIf you think this is a source error, forward to: {SUPPORT_CHAT}')

async def delete(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('Ask my Owner to use this Command...')
        return

    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('Incorrect format... Please use: /delete ID')
            return

        
        character = await collection.find_one_and_delete({'id': args[0]})

        if character:
            
            await context.bot.delete_message(chat_id=CHARA_CHANNEL_ID, message_id=character['message_id'])
            await update.message.reply_text('DONE')
        else:
            await update.message.reply_text('Deleted Successfully from db, but character not found In Channel')
    except Exception as e:
        await update.message.reply_text(f'{str(e)}')

async def update(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in sudo_users:
        await update.message.reply_text('You do not have permission to use this command.')
        return

    try:
        args = context.args
        if len(args) != 3:
            await update.message.reply_text('Incorrect format. Please use: /update id field new_value')
            return

        # Get character by ID
        character = await collection.find_one({'id': args[0]})
        if not character:
            await update.message.reply_text('Character not found.')
            return

        # Check if field is valid
        valid_fields = ['img_url', 'name', 'anime', 'rarity', 'emoji']
        if args[1] not in valid_fields:
            await update.message.reply_text(f'Invalid field. Please use one of the following: {", ".join(valid_fields)}')
            return

        # Update field
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

        await collection.find_one_and_update({'id': args[0]}, {'$set': {args[1]: new_value}})
        updated_character = dict(character)
        updated_character[args[1]] = new_value

        if args[1] == 'img_url':
            await context.bot.delete_message(chat_id=CHARA_CHANNEL_ID, message_id=character['message_id'])
            message = await context.bot.send_photo(
                chat_id=CHARA_CHANNEL_ID,
                photo=new_value,
                caption=f'<b>Character Name:</b> {updated_character["name"]}\n<b>Anime Name:</b> {updated_character["anime"]}\n<b>Rarity:</b> {updated_character["rarity"]}\n<b>ID:</b> {updated_character["id"]}\nUpdated by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                parse_mode='HTML'
            )
            character['message_id'] = message.message_id
            await collection.find_one_and_update({'id': args[0]}, {'$set': {'message_id': message.message_id}})
        else:
            
            await context.bot.edit_message_caption(
                chat_id=CHARA_CHANNEL_ID,
                message_id=character['message_id'],
                caption=f'<b>Character Name:</b> {updated_character["name"]}\n<b>Anime Name:</b> {updated_character["anime"]}\n<b>Rarity:</b> {updated_character["rarity"]}\n<b>ID:</b> {updated_character["id"]}\nUpdated by <a href="tg://user?id={update.effective_user.id}">{update.effective_user.first_name}</a>',
                parse_mode='HTML'
            )

        await update.message.reply_text('Updated Done in Database.... But sometimes it Takes Time to edit Caption in Your Channel..So wait..')
    except Exception as e:
        await update.message.reply_text(f'I guess did not added bot in channel.. or character uploaded Long time ago.. Or character not exits.. orr Wrong id')

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


UPLOAD_HANDLER = CommandHandler('upload', upload, block=False)
application.add_handler(UPLOAD_HANDLER)
DELETE_HANDLER = CommandHandler('delete', delete, block=False)
application.add_handler(DELETE_HANDLER)
UPDATE_HANDLER = CommandHandler('update', update, block=False)
application.add_handler(UPDATE_HANDLER)
SET_RARITY_HANDLER = CommandHandler(['setrarity', 'setrarityprob'], set_rarity_probability, block=False)
application.add_handler(SET_RARITY_HANDLER)
RARITY_HANDLER = CommandHandler('rarities', show_rarity_probabilities, block=False)
application.add_handler(RARITY_HANDLER)
