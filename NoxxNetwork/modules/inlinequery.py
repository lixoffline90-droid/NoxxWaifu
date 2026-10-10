import re
import time
from html import escape
from cachetools import TTLCache
from pymongo import ASCENDING

from telegram import Update, InlineQueryResultPhoto
from telegram.ext import InlineQueryHandler, CallbackContext

from NoxxNetwork import user_collection, collection, application, LOGGER
from NoxxNetwork.rarity import RARITIES, rarity_name, rarity_id_from_value


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------
async def ensure_indexes():
    try:
        await collection.create_index([('id', ASCENDING)])
        await collection.create_index([('anime', ASCENDING)])
        await collection.create_index([('img_url', ASCENDING)])
        await collection.create_index([('rarity', ASCENDING)])
        await user_collection.create_index([('characters.id', ASCENDING)])
        await user_collection.create_index([('characters.name', ASCENDING)])
        await user_collection.create_index([('characters.img_url', ASCENDING)])
        await user_collection.create_index([('characters.rarity', ASCENDING)])
        LOGGER.info("Inline indexes ensured")
    except Exception as e:
        LOGGER.warning(f"Index creation failed: {e}")


all_characters_cache = TTLCache(maxsize=10000, ttl=60)
user_collection_cache = TTLCache(maxsize=10000, ttl=60)


# ---------------------------------------------------------------------------
# Rarity search helpers
# ---------------------------------------------------------------------------
def _all_rarity_names():
    """Return list of (name_lower, emoji, name) tuples from RARITIES."""
    out = []
    for number, (emoji, name) in RARITIES.items():
        out.append((name.lower(), emoji, name))
    return out


def _match_rarity(query: str):
    """If query matches a rarity name (partial or exact), return (emoji, name).
    Otherwise None.
    """
    if not query:
        return None
    q = query.strip().lower()
    if len(q) < 3:
        return None

    # Exact match first
    for name_lower, emoji, name in _all_rarity_names():
        if q == name_lower:
            return (emoji, name)

    # Partial match — query contained in rarity name
    matches = []
    for name_lower, emoji, name in _all_rarity_names():
        if q in name_lower or name_lower.startswith(q):
            matches.append((emoji, name, len(name_lower)))

    if matches:
        # Prefer the shortest matching name (most specific)
        matches.sort(key=lambda x: x[2])
        return (matches[0][0], matches[0][1])

    return None


def _rarity_matches_character(char_rarity_value, target_rarity_name: str) -> bool:
    """Check if a stored character rarity matches the target rarity name."""
    if not char_rarity_value:
        return False
    try:
        return rarity_name(char_rarity_value).lower() == target_rarity_name.lower()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Inline query
# ---------------------------------------------------------------------------
async def inlinequery(update: Update, context: CallbackContext) -> None:
    try:
        query = (update.inline_query.query or "").strip()
        offset = int(update.inline_query.offset) if update.inline_query.offset else 0

        user = None
        is_collection = False
        is_rarity_search = False
        rarity_target = None  # (emoji, name)

        # ─── Collection view (collection.<user_id> [search] [rarity]) ───
        if query.startswith('collection.'):
            is_collection = True
            first_part, *rest = query.split(' ')
            user_id_part = first_part.split('.')[1]
            search_terms = ' '.join(rest).strip()

            if user_id_part.isdigit():
                owner_id = int(user_id_part)
                if owner_id in user_collection_cache:
                    user = user_collection_cache[owner_id]
                else:
                    user = await user_collection.find_one({'id': owner_id})
                    user_collection_cache[owner_id] = user

                if user:
                    all_characters = list({v['id']: v for v in user.get('characters', [])}.values())

                    if search_terms:
                        # Check if search_terms matches a rarity
                        rm = _match_rarity(search_terms)
                        if rm:
                            emoji, name = rm
                            all_characters = [
                                c for c in all_characters
                                if _rarity_matches_character(c.get('rarity'), name)
                            ]
                        else:
                            regex = re.compile(re.escape(search_terms), re.IGNORECASE)
                            all_characters = [
                                c for c in all_characters
                                if regex.search(c.get('name', '')) or regex.search(c.get('anime', ''))
                            ]
                else:
                    all_characters = []
            else:
                all_characters = []

        # ─── Global search ──────────────────────────────────────
        else:
            if query:
                # First, check if query is a rarity name
                rm = _match_rarity(query)
                if rm:
                    emoji, name = rm
                    is_rarity_search = True
                    rarity_target = (emoji, name)
                    # Fetch all and filter by rarity
                    all_chars = list(await collection.find({}).to_list(length=2000))
                    all_characters = [
                        c for c in all_chars
                        if _rarity_matches_character(c.get('rarity'), name)
                    ]
                else:
                    # Normal name/anime search
                    regex = re.compile(re.escape(query), re.IGNORECASE)
                    all_characters = list(
                        await collection.find(
                            {"$or": [{"name": regex}, {"anime": regex}]}
                        ).to_list(length=200)
                    )
            else:
                if 'all_characters' in all_characters_cache:
                    all_characters = all_characters_cache['all_characters']
                else:
                    all_characters = list(await collection.find({}).to_list(length=500))
                    all_characters_cache['all_characters'] = all_characters

        characters = all_characters[offset:offset + 50]
        next_offset = str(offset + 50) if len(all_characters) > offset + 50 else ""

        # ─── Precompute owner's anime count ─────────────────────
        owner_anime_counts = {}
        if is_collection and user:
            for c in user.get('characters', []):
                anime = c.get('anime', 'Unknown')
                owner_anime_counts[anime] = owner_anime_counts.get(anime, 0) + 1

        results = []
        for character in characters:
            char_id = str(character.get('id', ''))
            char_name = character.get('name', 'Unknown')
            char_anime = character.get('anime', 'Unknown')
            char_rarity = character.get('rarity', '⚪ Common')
            img_url = character.get('img_url', '')

            if not img_url:
                continue

            if is_collection and user:
                owner_catch_count = sum(
                    1 for c in user.get('characters', []) if str(c.get('id')) == char_id
                )
                owner_anime_count = owner_anime_counts.get(char_anime, 0)
                anime_total = await collection.count_documents({'anime': char_anime})

                caption = (
                    f"<b>OᴡO! Cʜᴇᴄᴋ ᴏᴜᴛ {user['id']}'s Wᴀɪғᴜ</b>\n\n"
                    f"<b>{escape(str(char_anime))} ({owner_anime_count}/{anime_total})</b>\n"
                    f"{escape(char_id)}:{escape(str(char_name))} (x{owner_catch_count})\n\n"
                    f"<b>RARITY</b> ( {escape(str(char_rarity))} )"
                )
            elif is_rarity_search and rarity_target:
                # Rarity search caption
                emoji, rname = rarity_target
                try:
                    global_count = await user_collection.count_documents(
                        {'characters.id': char_id}
                    )
                except Exception:
                    global_count = 0

                caption = (
                    f"<b>{emoji} {escape(rname.upper())} Cᴏʟʟᴇᴄᴛɪᴏɴ</b>\n\n"
                    f"<b>{escape(str(char_anime))}</b>\n"
                    f"{escape(char_id)}:{escape(str(char_name))}\n\n"
                    f"<b>RARITY</b> ( {escape(str(char_rarity))} )\n\n"
                    f"<b>Gʟᴏʙᴀʟʟʏ ᴄᴀᴛᴄʜᴇs {global_count} ᴛɪᴍᴇs...</b>"
                )
            else:
                try:
                    global_count = await user_collection.count_documents({'characters.id': char_id})
                except Exception:
                    global_count = 0

                caption = (
                    f"<b>OᴡO! Cʜᴇᴄᴋ ᴏᴜᴛ Cʜᴀʀᴀᴄᴛᴇʀ!!</b>\n\n"
                    f"<b>{escape(str(char_anime))}</b>\n"
                    f"{escape(char_id)}:{escape(str(char_name))}\n\n"
                    f"<b>RARITY</b> ( {escape(str(char_rarity))} )\n\n"
                    f"<b>Gʟᴏʙᴀʟʟʏ ᴄᴀᴛᴄʜᴇs {global_count} ᴛɪᴍᴇs...</b>"
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
            cache_time=1,
            is_personal=True,
        )

    except Exception as e:
        LOGGER.exception(f"Inline query error: {e}")
        try:
            await update.inline_query.answer([], cache_time=1)
        except Exception:
            pass


application.add_handler(InlineQueryHandler(inlinequery, block=False))
