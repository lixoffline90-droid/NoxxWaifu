from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import application, collection, user_collection, LOGGER
from NoxxNetwork.rarity import RARITIES, rarity_id_from_value


# ---------------------------------------------------------------------------
# /wrarity  — show user's collection grouped by rarity
# ---------------------------------------------------------------------------
async def wrarity(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id

    # ─── Get user's collection ────────────────────────────────────
    user_doc = await user_collection.find_one({'id': user_id})
    owned_chars = user_doc.get('characters', []) if user_doc else []

    if not owned_chars:
        await update.message.reply_text(
            "🌸 <b>Yᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴄʜᴀʀᴀᴄᴛᴇʀs ʏᴇᴛ!</b>\n\n"
            "Usᴇ /ɢʀᴀʙ ɪɴ ᴀ ɢʀᴏᴜᴘ ᴛᴏ sᴛᴀʀᴛ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴡᴀɪғᴜs.",
            parse_mode='HTML',
        )
        return

    # ─── Count owned characters per rarity (unique IDs) ────────────
    owned_by_rarity = {}
    seen_ids = set()
    for c in owned_chars:
        cid = str(c.get('id', ''))
        if cid in seen_ids:
            continue  # count unique characters only
        seen_ids.add(cid)
        rid = rarity_id_from_value(c.get('rarity'))
        owned_by_rarity[rid] = owned_by_rarity.get(rid, 0) + 1

    # ─── Count total characters per rarity from main DB ────────────
    total_by_rarity = {rid: 0 for rid in RARITIES.keys()}
    seen_global_ids = set()

    try:
        # Aggregate by rarity string
        pipeline = [
            {"$group": {"_id": "$rarity", "ids": {"$push": "$id"}}}
        ]
        cursor = collection.aggregate(pipeline)
        async for doc in cursor:
            rarity_value = doc.get('_id')
            ids = doc.get('ids', [])
            rid = rarity_id_from_value(rarity_value)
            # Count unique IDs across legacy + new rarity labels
            for cid in ids:
                sid = str(cid)
                key = (rid, sid)
                if key not in seen_global_ids:
                    seen_global_ids.add(key)
                    total_by_rarity[rid] = total_by_rarity.get(rid, 0) + 1
    except Exception as exc:
        LOGGER.warning(f"Rarity aggregation failed, falling back: {exc}")
        # Fallback: fetch all and count
        all_chars = await collection.find({}).to_list(length=None)
        for c in all_chars:
            cid = str(c.get('id', ''))
            rid = rarity_id_from_value(c.get('rarity'))
            key = (rid, cid)
            if key not in seen_global_ids:
                seen_global_ids.add(key)
                total_by_rarity[rid] = total_by_rarity.get(rid, 0) + 1

    # ─── Build output ─────────────────────────────────────────────
    lines = [
        "✨ <b>Yᴏᴜʀ Cʜᴀʀᴀᴄᴛᴇʀ Cᴏʟʟᴇᴄᴛɪᴏɴ ʙʏ Rᴀʀɪᴛʏ</b> ✨",
        "",
        "🔹 <b>Rᴀʀɪᴛɪᴇs:</b>",
    ]

    total_owned = 0
    total_possible = 0

    for rid in sorted(RARITIES.keys()):
        emoji, name = RARITIES[rid]
        owned = owned_by_rarity.get(rid, 0)
        total = total_by_rarity.get(rid, 0)
        total_owned += owned
        total_possible += total

        # Format: • ⚪ Common: 12/78
        if total > 0:
            lines.append(f"• {emoji} {escape(name)}: <b>{owned}</b>/{total}")
        else:
            lines.append(f"• {emoji} {escape(name)}: <b>{owned}</b>/0")

    lines.append("")
    lines.append(f"📊 <b>Tᴏᴛᴀʟ:</b> {total_owned}/{total_possible}")
    lines.append("")
    lines.append("✨ <i>Kᴇᴇᴘ ᴄᴏʟʟᴇᴄᴛɪɴɢ ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ ʏᴏᴜʀ ʜᴀʀᴇᴍ!</i> ✨")

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------
application.add_handler(
    CommandHandler(["wrarity", "wrarities", "rarities_me"], wrarity, block=False)
)
