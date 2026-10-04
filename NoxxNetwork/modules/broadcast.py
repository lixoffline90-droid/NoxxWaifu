import asyncio

from telegram import Update
from telegram.ext import CallbackContext, CommandHandler

from NoxxNetwork import (
    application,
    top_global_groups_collection,
    pm_users,
    OWNER_ID,
    LOGGER,
)


async def broadcast(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    message_to_broadcast = update.message.reply_to_message

    if message_to_broadcast is None:
        await update.message.reply_text("Please reply to a message to broadcast.")
        return

    all_chats = await top_global_groups_collection.distinct("group_id")
    all_users = await pm_users.distinct("_id")

    # Merge + dedupe
    targets = list(set(all_chats + all_users))

    if not targets:
        await update.message.reply_text("No chats/users found to broadcast.")
        return

    status_msg = await update.message.reply_text(
        f"📢 Broadcasting to {len(targets)} chats/users..."
    )

    failed_sends = 0
    success_sends = 0
    blocked = 0

    for chat_id in targets:
        try:
            await context.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=message_to_broadcast.chat_id,
                message_id=message_to_broadcast.message_id,
            )
            success_sends += 1
        except Exception as e:
            error_text = str(e).lower()
            if "blocked" in error_text or "deactivated" in error_text or "chat not found" in error_text:
                blocked += 1
            else:
                LOGGER.warning(f"Broadcast failed for {chat_id}: {e}")
            failed_sends += 1

        # Flood-wait safety (Telegram allows ~30 msg/sec)
        await asyncio.sleep(0.05)

        # Progress update every 50 sends
        if (success_sends + failed_sends) % 50 == 0:
            try:
                await status_msg.edit_text(
                    f"📢 Broadcasting...\n"
                    f"✅ Sent: {success_sends}\n"
                    f"❌ Failed: {failed_sends}\n"
                    f"🚫 Blocked: {blocked}"
                )
            except Exception:
                pass

    await status_msg.edit_text(
        f"✅ <b>Bʀᴏᴀᴅᴄᴀsᴛ Cᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
        f"📊 Total: {len(targets)}\n"
        f"✅ Sent: {success_sends}\n"
        f"❌ Failed: {failed_sends}\n"
        f"🚫 Blocked/Deactivated: {blocked}",
        parse_mode="HTML",
    )


application.add_handler(CommandHandler("broadcast", broadcast, block=False))