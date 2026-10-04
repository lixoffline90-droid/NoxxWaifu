from telegram import Update
from telegram.ext import CommandHandler, CallbackContext
from pymongo import ReturnDocument

from NoxxNetwork import user_totals_collection, application, sudo_users, OWNER_ID


async def change_time(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Check admin
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status = str(getattr(member, "status", "")).lower()
        is_admin = status in {"administrator", "creator"}
    except Exception:
        await update.message.reply_text('⚠️ Cᴏᴜʟᴅ ɴᴏᴛ ᴠᴇʀɪғʏ ᴀᴅᴍɪɴ sᴛᴀᴛᴜs.')
        return

    # Check sudo/owner
    is_sudo = str(user_id) in sudo_users or user_id == OWNER_ID

    # Must be either group admin OR sudo/owner
    if not is_admin and not is_sudo:
        await update.message.reply_text('⚠️ Oɴʟʏ ɢʀᴏᴜᴘ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜɪs.')
        return

    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text('⚙️ U sᴀɢᴇ: /changetime 100')
            return

        new_frequency = int(args[0])

        # ─── Minimum rules ────────────────────────────────────────────
        if is_sudo:
            # Sudo/Owner: minimum 1
            if new_frequency < 1:
                await update.message.reply_text('⚠️ Fʀᴇǫᴜᴇɴᴄʏ ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1.')
                return
        else:
            # Normal admin: minimum 100
            if new_frequency < 100:
                await update.message.reply_text(
                    '⚠️ Fʀᴇǫᴜᴇɴᴄʏ ᴍᴜsᴛ ʙᴇ 100 ᴏʀ ʜɪɢʜᴇʀ ғᴏʀ ʀᴇɢᴜʟᴀʀ ᴀᴅᴍɪɴs.'
                )
                return

        await user_totals_collection.find_one_and_update(
            {'chat_id': str(chat_id)},
            {'$set': {'message_frequency': new_frequency}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        badge = "👑 Sᴜᴅᴏ" if is_sudo else "🛡️ Aᴅᴍɪɴ"
        await update.message.reply_text(
            f'✅ Sᴘᴀᴡɴ Fʀᴇǫᴜᴇɴᴄʏ Uᴘᴅᴀᴛᴇᴅ\n\n'
            f'{badge}\n'
            f'✦ Nᴇᴡ ғʀᴇǫᴜᴇɴᴄʏ: <b>{new_frequency}</b> ᴍᴇssᴀɢᴇs',
            parse_mode='HTML',
        )
    except Exception as e:
        await update.message.reply_text(f'❌ Fᴀɪʟᴇᴅ Tᴏ Uᴘᴅᴀᴛᴇ\n\n{str(e)}')


application.add_handler(
    CommandHandler(["changetime", "setchangetime"], change_time, block=False)
)
