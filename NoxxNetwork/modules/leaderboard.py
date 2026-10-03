import os
import random
import html

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application, PHOTO_URL, OWNER_ID,
    user_collection, top_global_groups_collection,
    group_user_totals_collection,
)
from NoxxNetwork import sudo_users as SUDO_USERS


def medal(position):
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, f"{position}.")


async def global_leaderboard(update: Update, context: CallbackContext) -> None:
    cursor = top_global_groups_collection.aggregate([
        {"$project": {"group_name": 1, "count": 1}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ])
    data = await cursor.to_list(length=10)

    lines = ["🏆 <b>Tᴏᴘ Gʀᴏᴜᴘs</b>", "", "✦ Gʀᴏᴜᴘs ᴡɪᴛʜ ᴛʜᴇ ᴍᴏsᴛ ᴄᴏʟʟᴇᴄᴛᴇᴅ ᴡᴀɪғᴜs", ""]
    for i, group in enumerate(data, 1):
        name = html.escape(str(group.get('group_name', 'Unknown')))
        if len(name) > 22:
            name = name[:22] + '…'
        lines.append(f"{medal(i)} <b>{name}</b>  •  {group.get('count', 0)}")

    await update.message.reply_photo(
        photo=random.choice(PHOTO_URL),
        caption="\n".join(lines),
        parse_mode='HTML',
    )


async def ctop(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    cursor = group_user_totals_collection.aggregate([
        {"$match": {"group_id": chat_id}},
        {"$project": {"username": 1, "first_name": 1, "character_count": "$count"}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10},
    ])
    data = await cursor.to_list(length=10)

    lines = ["🏆 <b>Cʜᴀᴛ Lᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>", "", "✦ Mᴏsᴛ ᴀᴄᴛɪᴠᴇ Cᴏʟʟᴇᴄᴛᴏʀs ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ", ""]
    for i, user in enumerate(data, 1):
        name = html.escape(str(user.get('first_name', 'Unknown')))
        if len(name) > 18:
            name = name[:18] + '…'
        lines.append(f"{medal(i)} <b>{name}</b>  •  {user.get('character_count', 0)}")

    await update.message.reply_photo(photo=random.choice(PHOTO_URL), caption="\n".join(lines), parse_mode='HTML')


async def leaderboard(update: Update, context: CallbackContext) -> None:
    cursor = user_collection.aggregate([
        {"$project": {"username": 1, "first_name": 1, "character_count": {"$size": "$characters"}}},
        {"$sort": {"character_count": -1}},
        {"$limit": 10},
    ])
    data = await cursor.to_list(length=10)

    lines = ["👑 <b>Tᴏᴘ Wᴀɪғᴜ Cᴏʟʟᴇᴄᴛᴏʀs</b>", "", "✦ Mᴏsᴛ Cʜᴀʀᴀᴄᴛᴇʀs Cᴏʟʟᴇᴄᴛᴇᴅ", ""]
    for i, user in enumerate(data, 1):
        name = html.escape(str(user.get('first_name', 'Unknown')))
        if len(name) > 18:
            name = name[:18] + '…'
        lines.append(f"{medal(i)} <b>{name}</b>  •  {user.get('character_count', 0)}")

    await update.message.reply_photo(photo=random.choice(PHOTO_URL), caption="\n".join(lines), parse_mode='HTML')


async def stats(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⚠️ Yᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ.")
        return

    user_count = await user_collection.count_documents({})
    group_count = await group_user_totals_collection.distinct('group_id')
    await update.message.reply_text(
        f"📊 Bᴏᴛ Sᴛᴀᴛɪsᴛɪᴄs\n\n✦ U sᴇʀs: {user_count}\n✦ Gʀᴏᴜᴘs: {len(group_count)}"
    )


async def send_users_document(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('⚠️ Oɴʟʏ ғᴏʀ Sᴜᴅᴏ ᴜsᴇʀs.')
        return
    users = []
    async for document in user_collection.find({}):
        users.append(document)
    with open('users.txt', 'w') as f:
        f.write("\n".join(user['first_name'] for user in users))
    with open('users.txt', 'rb') as f:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
    os.remove('users.txt')


async def send_groups_document(update: Update, context: CallbackContext) -> None:
    if str(update.effective_user.id) not in SUDO_USERS:
        await update.message.reply_text('⚠️ Oɴʟʏ ғᴏʀ Sᴜᴅᴏ ᴜsᴇʀs.')
        return
    groups = []
    async for group in top_global_groups_collection.find({}):
        groups.append(group)
    with open('groups.txt', 'w') as f:
        f.write("\n\n".join(group['group_name'] for group in groups))
    with open('groups.txt', 'rb') as f:
        await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
    os.remove('groups.txt')


application.add_handler(CommandHandler('ctop', ctop, block=False))
application.add_handler(CommandHandler('stats', stats, block=False))
application.add_handler(CommandHandler('TopGroups', global_leaderboard, block=False))
application.add_handler(CommandHandler('list', send_users_document, block=False))
application.add_handler(CommandHandler('groups', send_groups_document, block=False))
application.add_handler(CommandHandler('top', leaderboard, block=False))
