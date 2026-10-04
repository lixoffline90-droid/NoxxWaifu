import random
import string
import time
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import (
    application,
    user_collection,
    collection,
    db,
    sudo_users,
    OWNER_ID,
    LOGGER,
)

redeem_codes_col = db['redeem_codes']


def _is_sudo(user_id: int) -> bool:
    return str(user_id) in sudo_users or user_id == OWNER_ID


def _generate_code(length=10):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


# ───────────────────────────────────────────────────────────────
# /charkill <char_id>  (reply to a user)  — Sudo/Owner only
# ───────────────────────────────────────────────────────────────
async def charkill(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Only Sudo Users can use this command.")
        return

    message = update.effective_message

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await update.message.reply_text(
            "U sᴀɢᴇ: Rᴇᴘʟʏ ᴛᴏ ᴀ ᴜsᴇʀ ᴡɪᴛʜ /charkill <character_id>\n"
            "Exᴀᴍᴘʟᴇ: /charkill 05"
        )
        return

    if not context.args:
        await update.message.reply_text("U sᴀɢᴇ: /charkill <character_id>")
        return

    target = message.reply_to_message.from_user
    character_id = str(context.args[0]).strip()

    target_user = await user_collection.find_one({'id': target.id})
    if not target_user:
        await update.message.reply_text("Tʜɪs ᴜsᴇʀ ᴅᴏᴇsɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴄʜᴀʀᴀᴄᴛᴇʀs.")
        return

    chars = list(target_user.get('characters', []))

    # Try multiple ID formats
    candidates = [character_id, character_id.zfill(2), character_id.lstrip('0') or '0']
    matched_char = None
    for c in chars:
        if str(c.get('id')) in candidates:
            matched_char = c
            break

    if not matched_char:
        await update.message.reply_text(
            f"❌ Cʜᴀʀᴀᴄᴛᴇʀ <code>{character_id}</code> ɴᴏᴛ ɪɴ ᴛʜᴀᴛ ᴜsᴇʀ's ʜᴀʀᴇᴍ.",
            parse_mode='HTML',
        )
        return

    # Remove only first occurrence
    removed = False
    new_chars = []
    for c in chars:
        if not removed and str(c.get('id')) == str(matched_char.get('id')):
            removed = True
            continue
        new_chars.append(c)

    await user_collection.update_one(
        {'id': target.id},
        {'$set': {'characters': new_chars}},
    )

    target_mention = f'<a href="tg://user?id={target.id}">{escape(target.first_name or "User")}</a>'
    await update.message.reply_text(
        f"☠️ <b>Cʜᴀʀᴀᴄᴛᴇʀ Kɪʟʟᴇᴅ</b>\n\n"
        f"👤 Fʀᴏᴍ: {target_mention}\n"
        f"🎴 Cʜᴀʀᴀᴄᴛᴇʀ: <b>{escape(str(matched_char.get('name', 'Unknown')))}</b>\n"
        f"🆔 ID: <code>{matched_char.get('id')}</code>",
        parse_mode='HTML',
    )


# ───────────────────────────────────────────────────────────────
# /create_code <char_id> [max_uses]  — Sudo/Owner only
# ───────────────────────────────────────────────────────────────
async def create_code(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Only Sudo Users can use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "U sᴀɢᴇ: /create_code <character_id> [max_uses]\n\n"
            "Exᴀᴍᴘʟᴇ:\n"
            "• <code>/create_code 05</code> — Unlimited uses\n"
            "• <code>/create_code 05 10</code> — 10 uses only",
            parse_mode='HTML',
        )
        return

    character_id = str(context.args[0]).strip()

    # Verify character exists
    character = await collection.find_one({'id': character_id})
    if not character:
        padded = character_id.zfill(2)
        character = await collection.find_one({'id': padded})
        if character:
            character_id = padded

    if not character:
        await update.message.reply_text(
            f"❌ Cʜᴀʀᴀᴄᴛᴇʀ <code>{character_id}</code> ɴᴏᴛ ғᴏᴜɴᴅ.",
            parse_mode='HTML',
        )
        return

    max_uses = 0  # 0 = unlimited
    if len(context.args) >= 2:
        try:
            max_uses = int(context.args[1])
            if max_uses < 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ Mᴀx ᴜsᴇs ᴍᴜsᴛ ʙᴇ ᴀ ᴘᴏsɪᴛɪᴠᴇ ɴᴜᴍʙᴇʀ (ᴏʀ 0 ғᴏʀ ᴜɴʟɪᴍɪᴛᴇᴅ)."
            )
            return

    # Generate unique code
    code = None
    for _ in range(10):
        temp = _generate_code(10)
        existing = await redeem_codes_col.find_one({'code': temp})
        if not existing:
            code = temp
            break

    if not code:
        await update.message.reply_text("❌ Fᴀɪʟᴇᴅ ᴛᴏ ɢᴇɴᴇʀᴀᴛᴇ ᴄᴏᴅᴇ. Tʀʏ ᴀɢᴀɪɴ.")
        return

    await redeem_codes_col.insert_one({
        'code': code,
        'character_id': character_id,
        'character_data': character,
        'created_by': caller_id,
        'created_at': int(time.time()),
        'max_uses': max_uses,
        'redeemed_by': [],
    })

    uses_text = "Unlimited ♾️" if max_uses == 0 else str(max_uses)
    await update.message.reply_text(
        f"🎁 <b>Rᴇᴅᴇᴇᴍ Cᴏᴅᴇ Cʀᴇᴀᴛᴇᴅ</b>\n\n"
        f"🎴 Cʜᴀʀᴀᴄᴛᴇʀ: <b>{escape(str(character.get('name', 'Unknown')))}</b>\n"
        f"🌸 Aɴɪᴍᴇ: {escape(str(character.get('anime', 'Unknown')))}\n"
        f"🆔 ID: <code>{character_id}</code>\n"
        f"🔑 Cᴏᴅᴇ: <code>{code}</code>\n"
        f"👥 Usᴇs: {uses_text}\n\n"
        f"Usᴇ: <code>/redeem {code}</code>",
        parse_mode='HTML',
    )


# ───────────────────────────────────────────────────────────────
# /redeem <code>  — Everyone
# ───────────────────────────────────────────────────────────────
async def redeem(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text("U sᴀɢᴇ: /redeem <code>")
        return

    code = str(context.args[0]).strip().upper()

    code_doc = await redeem_codes_col.find_one({'code': code})
    if not code_doc:
        await update.message.reply_text("❌ Iɴᴠᴀʟɪᴅ ᴏʀ ᴇxᴘɪʀᴇᴅ ᴄᴏᴅᴇ.")
        return

    redeemed_by = code_doc.get('redeemed_by', [])
    if user_id in redeemed_by:
        await update.message.reply_text("⚠️ Yᴏᴜ'ᴠᴇ ᴀʟʀᴇᴀᴅʏ ʀᴇᴅᴇᴇᴍᴇᴅ ᴛʜɪs ᴄᴏᴅᴇ!")
        return

    max_uses = int(code_doc.get('max_uses', 0))
    if max_uses > 0 and len(redeemed_by) >= max_uses:
        await redeem_codes_col.delete_one({'code': code})
        await update.message.reply_text("❌ Tʜɪs ᴄᴏᴅᴇ ʜᴀs ʀᴇᴀᴄʜᴇᴅ ɪᴛs ᴍᴀxɪᴍᴜᴍ ᴜsᴇs.")
        return

    character = code_doc.get('character_data')
    if not character:
        character_id = code_doc.get('character_id')
        character = await collection.find_one({'id': character_id})
        if not character:
            await redeem_codes_col.delete_one({'code': code})
            await update.message.reply_text("❌ Cʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ. Cᴏᴅᴇ ᴇxᴘɪʀᴇᴅ.")
            return

    # Add to user's harem
    user_doc = await user_collection.find_one({'id': user_id})
    if user_doc:
        await user_collection.update_one(
            {'id': user_id},
            {'$push': {'characters': character}},
        )
        update_fields = {}
        if user.username and user_doc.get('username') != user.username:
            update_fields['username'] = user.username
        if user.first_name and user_doc.get('first_name') != user.first_name:
            update_fields['first_name'] = user.first_name
        if update_fields:
            await user_collection.update_one({'id': user_id}, {'$set': update_fields})
    else:
        await user_collection.insert_one({
            'id': user_id,
            'username': user.username,
            'first_name': user.first_name,
            'characters': [character],
        })

    # Mark as redeemed
    await redeem_codes_col.update_one(
        {'code': code},
        {'$push': {'redeemed_by': user_id}},
    )

    # Check max uses after
    new_uses = len(redeemed_by) + 1
    if max_uses > 0 and new_uses >= max_uses:
        await redeem_codes_col.delete_one({'code': code})
        remaining_text = "⚠️ Lᴀsᴛ ᴜsᴇ — ᴄᴏᴅᴇ ᴇxᴘɪʀᴇᴅ."
    else:
        remaining = "Unlimited" if max_uses == 0 else f"{max_uses - new_uses} ʟᴇғᴛ"
        remaining_text = f"🔓 Rᴇᴍᴀɪɴɪɴɢ: {remaining}"

    await update.message.reply_text(
        f"🎉 <b>Cᴏᴅᴇ Rᴇᴅᴇᴇᴍᴇᴅ!</b>\n\n"
        f"🎴 Cʜᴀʀᴀᴄᴛᴇʀ: <b>{escape(str(character.get('name', 'Unknown')))}</b>\n"
        f"🌸 Aɴɪᴍᴇ: {escape(str(character.get('anime', 'Unknown')))}\n"
        f"⭐ Rᴀʀɪᴛʏ: {escape(str(character.get('rarity', 'Unknown')))}\n"
        f"🆔 ID: <code>{character.get('id')}</code>\n\n"
        f"Aᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ /harem!\n"
        f"{remaining_text}",
        parse_mode='HTML',
    )


# ───────────────────────────────────────────────────────────────
# /codes  — list active codes (Sudo/Owner)
# ───────────────────────────────────────────────────────────────
async def codes_list(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Only Sudo Users can use this command.")
        return

    cursor = redeem_codes_col.find({}).sort('created_at', -1).limit(20)
    data = await cursor.to_list(length=20)

    if not data:
        await update.message.reply_text("Nᴏ ᴀᴄᴛɪᴠᴇ ᴄᴏᴅᴇs.")
        return

    lines = ["🎁 <b>Aᴄᴛɪᴠᴇ Rᴇᴅᴇᴇᴍ Cᴏᴅᴇs</b>", ""]
    for doc in data:
        code = doc.get('code', '???')
        char_id = doc.get('character_id', '?')
        char_name = doc.get('character_data', {}).get('name', 'Unknown')
        max_uses = int(doc.get('max_uses', 0))
        used = len(doc.get('redeemed_by', []))
        uses_text = f"{used}/∞" if max_uses == 0 else f"{used}/{max_uses}"
        lines.append(
            f"🔑 <code>{code}</code> — {escape(str(char_name))} [{char_id}] • {uses_text}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


# ───────────────────────────────────────────────────────────────
# /delcode <code>  — Sudo/Owner
# ───────────────────────────────────────────────────────────────
async def delete_code(update: Update, context: CallbackContext) -> None:
    caller_id = update.effective_user.id
    if not _is_sudo(caller_id):
        await update.message.reply_text("⚠️ Only Sudo Users can use this command.")
        return

    if not context.args:
        await update.message.reply_text("U sᴀɢᴇ: /delcode <code>")
        return

    code = str(context.args[0]).strip().upper()
    result = await redeem_codes_col.delete_one({'code': code})
    if result.deleted_count == 0:
        await update.message.reply_text("❌ Cᴏᴅᴇ ɴᴏᴛ ғᴏᴜɴᴅ.")
        return

    await update.message.reply_text(
        f"✅ Cᴏᴅᴇ <code>{code}</code> ᴅᴇʟᴇᴛᴇᴅ.",
        parse_mode='HTML',
    )


# ───────────────────────────────────────────────────────────────
# Handler registration
# ───────────────────────────────────────────────────────────────
application.add_handler(CommandHandler("charkill", charkill, block=False))
application.add_handler(CommandHandler(["create_code", "createcode"], create_code, block=False))
application.add_handler(CommandHandler("redeem", redeem, block=False))
application.add_handler(CommandHandler(["codes", "codelist"], codes_list, block=False))
application.add_handler(CommandHandler("delcode", delete_code, block=False))
