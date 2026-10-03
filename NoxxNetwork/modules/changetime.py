from pymongo import  ReturnDocument
from pyrogram.enums import ChatMemberStatus, ChatType
from NoxxNetwork import user_totals_collection, Waifuu
from pyrogram import Client, filters
from pyrogram.types import Message

ADMINS = [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]


@Waifuu.on_message(filters.command(["changetime", "setchangetime"]))
async def change_time(client: Client, message: Message):
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    member = await Waifuu.get_chat_member(chat_id,user_id)
        

    if member.status not in ADMINS :
        await message.reply_text('⚠️ Oɴʟʏ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.')
        return

    try:
        args = message.command
        if len(args) != 2:
            await message.reply_text('⚙️ U sᴀɢᴇ: /changetime 100')
            return

        new_frequency = int(args[1])
        if new_frequency < 100:
            await message.reply_text('⚠️ Fʀᴇǫᴜᴇɴᴄʏ ᴍᴜsᴛ ʙᴇ 100 ᴏʀ ʜɪɢʜᴇʀ.')
            return

    
        chat_frequency = await user_totals_collection.find_one_and_update(
            {'chat_id': str(chat_id)},
            {'$set': {'message_frequency': new_frequency}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )

        await message.reply_text(f'✅ Sᴘᴀᴡɴ Fʀᴇǫᴜᴇɴᴄʏ Uᴘᴅᴀᴛᴇᴅ\n\n✦ Nᴇᴡ ғʀᴇǫᴜᴇɴᴄʏ: {new_frequency} ᴍᴇssᴀɢᴇs')
    except Exception as e:
        await message.reply_text(f'❌ Fᴀɪʟᴇᴅ Tᴏ Uᴘᴅᴀᴛᴇ\n\n{str(e)}')
