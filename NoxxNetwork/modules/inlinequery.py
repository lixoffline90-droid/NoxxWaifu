import re
import time
from html import escape
from cachetools import TTLCache
from pymongo import ASCENDING

from telegram import Update, InlineQueryResultPhoto
from telegram.ext import InlineQueryHandler, CallbackContext

from NoxxNetwork import user_collection, collection, application, db


# ---------------------------------------------------------------------------
# Indexes (motor is async — must be awaited)
# ---------------------------------------------------------------------------
async def ensure_indexes():
    """Create indexes used by the inline query for fast lookups."""
    await collection.create_index([('id', ASCENDING)])
    await collection.create_index([('anime', ASCENDING)])
    await collection.create_index([('img_url', ASCENDING)])

    await user_collection.create_index([('characters.id', ASCENDING)])
    await user_collection.create_index([('characters.name', ASCENDING)])
    await user_collection.create_index([('characters.img_url', ASCENDING)])


all_characters_cache = TTLCache(maxsize=10000, ttl=36000)
user_collection_cache = TTLCache(maxsize=10000, ttl=60)


# ---------------------------------------------------------------------------
# Inline query
# ---------------------------------------------------------------------------
async def inlinequery(update: Update, context: CallbackContext) -> None:
    query = update.inline_query.query.strip()
    offset = int(update.inline_query.offset) if update.inline_query.offset else 0

    user = None

    if query.startswith('collection.'):
        # user's own collection view
        user_id, *search_terms = query.split(' ')[0].split('.')[1], ' '.join(query.split(' ')[1:])
        if user_id.isdigit():
            if user_id in user_collection_cache:
                user = user_collection_cache[user_id]
            else:
                user = await user_collection.find_one({'id': int(user_id)})
                user_collection_cache[user_id] = user

            if user:
                all_characters = list({v['id']: v for v in user['characters']}.values())
                if search_terms:
                    regex = re.compile(' '.join(search_terms), re.IGNORECASE)
                    all_characters = [
                        c for c in all_characters
                        if regex.search(c.get('name', '')) or regex.search(c.get('anime', ''))
                    ]
            else:
                all_characters = []
        else:
            all_characters = []
    else:
        # global search
        if query:
            regex = re.compile(re.escape(query), re.IGNORECASE)
            all_characters = list(
                await collection.find(
                    {"$or": [{"name": regex}, {"anime": regex}]}
                ).to_list(length=None)
            )
        else:
            if 'all_characters' in all_characters_cache:
                all_characters = all_characters_cache['all_characters']
            else:
                all_characters = list(await collection.find({}).to_list(length=None))
                all_characters_cache['all_characters'] = all_characters

    characters = all_characters[offset:offset + 50]
    next_offset = str(offset + 50) if len(characters) == 50 else ""

    results = []
    for character in characters:
        char_id = str(character.get('id', ''))
        char_name = character.get('name', 'Unknown')
        char_anime = character.get('anime', 'Unknown')
        char_rarity = character.get('rarity', '⚪ Common')
        img_url = character.get('img_url', '')

        # Global catch count
        try:
            global_count = await user_collection.count_documents({'characters.id': char_id})
        except Exception:
            global_count = 0

        if query.startswith('collection.') and user:
            # User's collection view
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
            # Global view — screenshot style
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
                id=f"{char_id}_{offset}_{int(time.time())}",
                photo_url=img_url,
                caption=caption,
                parse_mode='HTML',
            )
        )

    await update.inline_query.answer(results, next_offset=next_offset, cache_time=5)


application.add_handler(InlineQueryHandler(inlinequery, block=False))
