import re
import time
from html import escape
from cachetools import TTLCache
from pymongo import ASCENDING

from telegram import Update, InlineQueryResultPhoto
from telegram.ext import InlineQueryHandler, CallbackContext

from NoxxNetwork import user_collection, collection, application, LOGGER


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
async def ensure_indexes():
    """Create indexes used by the inline query for fast lookups."""
    try:
        await collection.create_index([('id', ASCENDING)])
        await collection.create_index([('anime', ASCENDING)])
        await collection.create_index([('img_url', ASCENDING)])
        await user_collection.create_index([('characters.id', ASCENDING)])
        await user_collection.create_index([('characters.name', ASCENDING)])
        await user_collection.create_index([('characters.img_url', ASCENDING)])
        LOGGER.info("Inline indexes ensured")
    except Exception as e:
        LOGGER.warning(f"Index creation failed: {e}")


all_characters_cache = TTLCache(maxsize=10000, ttl=60)
user_collection_cache = TTLCache(maxsize=10000, ttl=60)


# ---------------------------------------------------------------------------
# Inline query
# ---------------------------------------------------------------------------
async def inlinequery(update: Update, context: CallbackContext) -> None:
    try:
        query = (update.inline_query.query or "").strip()
        offset = int(update.inline_query.offset) if update.inline_query.offset else 0

        LOGGER.info(f"Inline query received: '{query}' offset={offset}")

        user = None

        # ─── Collection view ───────────────────────────────────────
        if query.startswith('collection.'):
            user_id_part = query.split(' ')[0].split('.')[1]
            search_terms = ' '.join(query.split(' ')[1:])

            if user_id_part.isdigit():
                user_id = int(user_id_part)
                if user_id in user_collection_cache:
                    user = user_collection_cache[user_id]
                else:
                    user = await user_collection.find_one({'id': user_id})
                    user_collection_cache[user_id] = user

                if user:
                    all_characters = list({v['id']: v for v in user.get('characters', [])}.values())
                    if search_terms:
                        regex = re.compile(re.escape(search_terms), re.IGNORECASE)
                        all_characters = [
                            c for c in all_characters
                            if regex.search(c.get('name', '')) or regex.search(c.get('anime', ''))
                        ]
                else:
                    all_characters = []
            else:
                all_characters = []

        # ─── Normal search ─────────────────────────────────────────
        else:
            if query:
                regex = re.compile(re.escape(query), re.IGNORECASE)
                all_characters = list(
                    await collection.find(
                        {"$or": [{"name": regex}, {"anime": regex}]}
                    ).to_list(length=200)
                )
            else:
                # Empty query — show all (cached)
                if 'all_characters' in all_characters_cache:
                    all_characters = all_characters_cache['all_characters']
                else:
                    all_characters = list(await collection.find({}).to_list(length=500))
                    all_characters_cache['all_characters'] = all_characters

        LOGGER.info(f"Inline query found {len(all_characters)} characters")

        # Pagination
        characters = all_characters[offset:offset + 50]
        if len(all_characters) > offset + 50:
            next_offset = str(offset + 50)
        else:
            next_offset = ""

        results = []
        for character in characters:
            char_id = str(character.get('id', ''))
            char_name = character.get('name', 'Unknown')
            char_anime = character.get('anime', 'Unknown')
            char_rarity = character.get('rarity', '⚪ Common')
            img_url = character.get('img_url', '')

            if not img_url:
                continue

            try:
                global_count = await user_collection.count_documents({'characters.id': char_id})
            except Exception:
                global_count = 0

            if query.startswith('collection.') and user:
                user_catch_count = sum(
                    1 for c in user.get('characters', []) if str(c.get('id')) == char_id
                )
                caption = (
                    f"<b>OwO! Check out Character!!</b>\n\n"
                    f"<b>{escape(str(char_name))}</b>\n"
                    f"{escape(char_id)}:{escape(str(char_name))}\n\n"
                    f"<b>RARITY</b> ({escape(str(char_rarity))})\n\n"
                    f"<b>You have {user_catch_count} copy(s)</b>"
                )
            else:
                caption = (
                    f"<b>OwO! Check out Character!!</b>\n\n"
                    f"<b>{escape(str(char_anime))}</b>\n"
                    f"{escape(char_id)}:{escape(str(char_name))}\n\n"
                    f"<b>RARITY</b> ({escape(str(char_rarity))})\n\n"
                    f"<b>Globally catches {global_count} Times...</b>"
                )

            results.append(
                InlineQueryResultPhoto(
                    thumbnail_url=img_url,
                    id=f"{char_id}_{offset}_{int(time.time() * 1000)}",
                    photo_url=img_url,
                    caption=caption,
                    parse_mode='HTML',
                )
            )

        await update.inline_query.answer(
            results,
            next_offset=next_offset,
            cache_time=5,
            is_personal=True,
        )

    except Exception as e:
        LOGGER.exception(f"Inline query error: {e}")
        try:
            await update.inline_query.answer([], cache_time=1)
        except Exception:
            pass


application.add_handler(InlineQueryHandler(inlinequery, block=False))
