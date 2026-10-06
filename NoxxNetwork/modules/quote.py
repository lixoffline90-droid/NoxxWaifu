# --------------------------------------------------------------------------------
#  Elara © 2026
#  handlers/quote.py — 📱 Quote Sticker / Image Generator
#  Commands: /q, /q img, /q N, /q -N, /q r, /q c, /qhelp
# --------------------------------------------------------------------------------

from __future__ import annotations

import os
import re
import tempfile

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from core.bot import app
from core.quotly import (
    build_message_dict,
    crop_to_strip,
    generate_quote_png,
    png_to_webp,
)

PREFIXES = ["/", "!", "."]

_NUM_RE = re.compile(r"^-?\d+$")


def _parse_args(raw: list[str]):
    count = 0
    as_image = False
    show_reply = False
    crop = False
    for a in raw:
        al = a.lower()
        if _NUM_RE.match(al):
            try:
                count = int(al)
            except ValueError:
                pass
        elif al in ("img", "png", "image"):
            as_image = True
        elif al in ("r", "reply"):
            show_reply = True
        elif al in ("c", "crop"):
            crop = True
    return count, as_image, show_reply, crop


async def _collect_range(message: Message, count: int) -> list[Message]:
    """Collect replied message + optional N below/above."""
    reply = message.reply_to_message
    if not reply:
        return []

    targets = [reply]

    if count > 0:
        # replied + N below (newer messages)
        try:
            async for m in app.get_chat_history(
                message.chat.id,
                offset_id=reply.id,
                limit=count + 1,
            ):
                if m and m.id > reply.id:
                    targets.append(m)
                    if len(targets) >= count + 1:
                        break
        except Exception:
            pass

    elif count < 0:
        # replied + N above (older messages)
        n = abs(count)
        try:
            older = []
            async for m in app.get_chat_history(
                message.chat.id,
                offset_id=reply.id,
                limit=n + 1,
            ):
                if m and m.id < reply.id:
                    older.append(m)
                    if len(older) >= n:
                        break
            older.reverse()
            targets = older + targets
        except Exception:
            pass

    return targets


def _help_text() -> str:
    return (
        "📱 <b>ǫᴜᴏᴛᴇ ɢᴇɴᴇʀᴀᴛᴏʀ</b>\n\n"
        "<b>📌 ʙᴀsɪᴄ:</b>\n"
        "• <b>ᴘʀɪᴠᴀᴛᴇ:</b> ꜰᴏʀᴡᴀʀᴅ ᴀ ᴍᴇssᴀɢᴇ → ɢᴇᴛ ᴀ sᴛɪᴄᴋᴇʀ\n"
        "• <b>ɢʀᴏᴜᴘ:</b> ʀᴇᴘʟʏ <code>/q</code> ᴛᴏ ᴀɴʏ ᴍᴇssᴀɢᴇ\n\n"
        "<b>📚 ᴍᴜʟᴛɪᴘʟᴇ ᴍᴇssᴀɢᴇs:</b>\n"
        "• <code>/q 3</code> — ʀᴇᴘʟɪᴇᴅ + 3 ʙᴇʟᴏᴡ ɪᴛ\n"
        "• <code>/q -3</code> — ʀᴇᴘʟɪᴇᴅ + 3 ᴀʙᴏᴠᴇ ɪᴛ\n\n"
        "<b>🖼 ꜰᴏʀᴍᴀᴛ:</b>\n"
        "• <code>/q img</code> — ᴘɴɢ ɪɴsᴛᴇᴀᴅ ᴏꜰ sᴛɪᴄᴋᴇʀ\n\n"
        "<b>🎯 ᴇxᴛʀᴀs:</b>\n"
        "• <code>/q c</code> — sᴍᴀʀᴛ ᴄʀᴏᴘ (ɴᴀʀʀᴏᴡ sᴛʀɪᴘ)\n"
        "• <code>/q r</code> — ɪɴᴄʟᴜᴅᴇs ʀᴇᴘʟɪᴇᴅ ᴍᴇssᴀɢᴇ\n\n"
        "<i>💡 ᴄᴏᴍʙɪɴᴇ ꜰʟᴀɢs: <code>/q 3 img</code>, <code>/q r img</code>, ᴇᴛᴄ.</i>"
    )


@app.on_message(filters.command(["qhelp", "quotehelp"], prefixes=PREFIXES))
async def qhelp_cmd(_, message: Message):
    await message.reply(_help_text(), parse_mode=ParseMode.HTML)


@app.on_message(
    filters.command("q", prefixes=PREFIXES) & (filters.group | filters.private)
)
async def quote_cmd(_, message: Message):
    if not message.from_user:
        return

    # No reply → show help
    if not message.reply_to_message:
        return await message.reply(_help_text(), parse_mode=ParseMode.HTML)

    raw_args = [str(x) for x in (message.command or [])[1:]]
    count, as_image, show_reply, crop = _parse_args(raw_args)

    targets = await _collect_range(message, count)
    if not targets:
        return

    # Build payload
    payload = []
    for m in targets:
        try:
            payload.append(await build_message_dict(m, include_reply=show_reply))
        except Exception:
            continue

    if not payload:
        return await message.reply(
            "❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ʙᴜɪʟᴅ ǫᴜᴏᴛᴇ.</b>",
            parse_mode=ParseMode.HTML,
        )

    # Progress message
    try:
        status = await message.reply(
            "🎨 <b>ɢᴇɴᴇʀᴀᴛɪɴɢ ǫᴜᴏᴛᴇ...</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        status = None

    png = await generate_quote_png(payload)
    if not png:
        if status:
            try:
                await status.delete()
            except Exception:
                pass
        return await message.reply(
            "❌ <b>ǫᴜᴏᴛᴇ sᴇʀᴠɪᴄᴇ ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ. ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>",
            parse_mode=ParseMode.HTML,
        )

    if crop:
        png = crop_to_strip(png)

    # Write to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    tmp.write(png)
    tmp.close()
    path = tmp.name

    try:
        if as_image:
            await message.reply_photo(photo=path)
        else:
            webp = png_to_webp(png)
            if webp:
                tmp2 = tempfile.NamedTemporaryFile(delete=False, suffix=".webp")
                tmp2.write(webp)
                tmp2.close()
                try:
                    await message.reply_sticker(sticker=tmp2.name)
                finally:
                    try:
                        os.remove(tmp2.name)
                    except Exception:
                        pass
            else:
                # Fallback: send as photo
                await message.reply_photo(photo=path)
    except Exception as e:
        print(f"[QUOTE send] {type(e).__name__}: {e}", flush=True)
    finally:
        if status:
            try:
                await status.delete()
            except Exception:
                pass
        try:
            os.remove(path)
        except Exception:
            pass


# ── Private chat: forward any message → sticker quote ─────────────────────────
@app.on_message(filters.private & filters.forwarded)
async def quote_forward_cmd(_, message: Message):
    # Ignore if message looks like a command
    if message.text and message.text.startswith(tuple(PREFIXES)):
        return
    # Ignore bot's own messages
    if message.from_user and message.from_user.is_bot:
        return

    try:
        payload = [await build_message_dict(message, include_reply=False)]
    except Exception:
        return

    png = await generate_quote_png(payload)
    if not png:
        return

    webp = png_to_webp(png)
    if webp:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".webp")
        tmp.write(webp)
        tmp.close()
        try:
            await message.reply_sticker(sticker=tmp.name)
        except Exception as e:
            print(f"[QUOTE fwd-sticker] {type(e).__name__}: {e}", flush=True)
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.write(png)
        tmp.close()
        try:
            await message.reply_photo(photo=tmp.name)
        except Exception:
            pass
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
