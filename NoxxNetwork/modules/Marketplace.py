"""
Waifu Marketplace — Rich UI (Kurigram)
Commands:
    /market               - browse listings (paginated, 10/page)
    /sellwaifu <id> <price>
    /wbuy <listing_id>
    /cancelsell <listing_id>
    /mylistings
    /marketstats          (sudo)
"""
from __future__ import annotations

import html as _html
import os
import random
import re as _re
import string
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from telegram.error import BadRequest

from NoxxNetwork import (
    application, db, user_collection, collection,
    LOGGER, OWNER_ID, sudo_users,
)


# ══════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════
MARKET_IMG_URL = os.getenv(
    "MARKET_IMG_URL",
    "https://i.ibb.co/8gvNGSbL/26831adc4ea1.jpg",
)

MARKET_TAX_RATE = 0.05
LISTINGS_PER_PAGE = 10
LISTING_ID_LEN = 7
LISTING_PREFIX = "MKT"
MIN_PRICE = 1
MAX_PRICE = 10_000_000


# ─── Coins module ─────────────────────────────────────────────
try:
    from NoxxNetwork.modules.coin import coins_collection, get_balance
except Exception as _e:
    LOGGER.warning(f"[marketplace] coin module missing: {_e}")
    coins_collection = db['user_coins']

    async def get_balance(user_id):
        doc = await coins_collection.find_one({'user_id': user_id})
        return int(doc.get('coins', 0)) if doc else 0


# ══════════════════════════════════════════════════════════════
# Fallback helpers
# ══════════════════════════════════════════════════════════════
def _fb_esc(v) -> str:
    if v is None:
        return ""
    return _html.escape(str(v), quote=False)


def _fb_heading(text: str, level: int = 2) -> str:
    return f"<b>{text}</b>\n"


def _fb_note(text: str, expandable: bool = False) -> str:
    return f"<blockquote>{text}</blockquote>"


def _fb_code(value) -> str:
    return f"<code>{_fb_esc(value)}</code>"


# ══════════════════════════════════════════════════════════════
# Rich UI import
# ══════════════════════════════════════════════════════════════
RICH_UI_OK = False
_rich_send = None
_rich_edit = None
_rich_esc = None
_rich_heading = None
_rich_table = None
_rich_note = None
_rich_code = None

try:
    from NoxxNetwork.rich_ui_decoded import (
        rich_send as _rich_send,
        rich_edit as _rich_edit,
        rich_esc as _rich_esc,
        rich_heading as _rich_heading,
        rich_table as _rich_table,
        rich_note as _rich_note,
        rich_code as _rich_code,
    )
    RICH_UI_OK = True
    LOGGER.info("[marketplace] rich_ui loaded ✅")
except Exception as _e:
    LOGGER.warning(f"[marketplace] rich_ui unavailable, using fallbacks: {_e}")


# ─── Safe wrappers ────────────────────────────────────────────
def rich_esc(v):
    if _rich_esc:
        try:
            return _rich_esc(v)
        except Exception:
            pass
    return _fb_esc(v)


def rich_heading(text, level=2):
    if _rich_heading:
        try:
            return _rich_heading(text, level)
        except Exception:
            pass
    return _fb_heading(text, level)


def rich_note(text, expandable=False):
    if _rich_note:
        try:
            return _rich_note(text, expandable)
        except Exception:
            pass
    return _fb_note(text, expandable)


def rich_code(v):
    if _rich_code:
        try:
            return _rich_code(v)
        except Exception:
            pass
    return _fb_code(v)


# ─── Pyrogram client ──────────────────────────────────────────
try:
    from NoxxNetwork import Waifuu as _Waifuu
except Exception:
    _Waifuu = None

PYRO_OK = _Waifuu is not None


# ══════════════════════════════════════════════════════════════
# Rarity symbol extractor
# ══════════════════════════════════════════════════════════════
def _rar_symbol_only(value) -> str:
    """'🟡 Legendary' → '🟡'"""
    if not value:
        return "⚪"
    s = str(value).strip()
    if not s:
        return "⚪"
    first = s.split()[0] if s.split() else ""
    if first and not first[0].isalnum():
        return first
    return "⚪"


# ══════════════════════════════════════════════════════════════
# Collections
# ══════════════════════════════════════════════════════════════
marketplace_col = db['marketplace_listings']
market_txn_col = db['marketplace_transactions']
market_stats_col = db['marketplace_stats']
market_locks_col = db['marketplace_locks']


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════
def _is_sudo(uid: int) -> bool:
    return str(uid) in (sudo_users or []) or uid == OWNER_ID


def _fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def _now() -> int:
    return int(time.time())


def _gen_listing_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    rand_len = LISTING_ID_LEN - len(LISTING_PREFIX)
    return LISTING_PREFIX + "".join(random.choices(alphabet, k=rand_len))


def _snap(c: dict) -> dict:
    return {
        'id': str(c.get('id', '')),
        'name': str(c.get('name', 'Unknown')),
        'anime': str(c.get('anime', '')),
        'rarity': str(c.get('rarity', '⚪ Common')),
        'img_url': str(c.get('img_url', '')),
        'emoji': str(c.get('emoji', '') or ''),
    }


async def ensure_indexes():
    try:
        await marketplace_col.create_index('listing_id', unique=True)
        await marketplace_col.create_index('status')
        await marketplace_col.create_index('seller_id')
        await marketplace_col.create_index('waifu_id')
        await marketplace_col.create_index([('status', 1), ('created_at', -1)])
        await market_txn_col.create_index('listing_id')
        await market_txn_col.create_index('timestamp')
        await market_locks_col.create_index([('seller_id', 1), ('waifu_id', 1)])
        LOGGER.info("[marketplace] indexes ensured")
    except Exception as e:
        LOGGER.warning(f"[marketplace] index: {e}")


async def is_waifu_locked(user_id: int, waifu_id: str) -> bool:
    doc = await market_locks_col.find_one({'seller_id': user_id, 'waifu_id': str(waifu_id)})
    return doc is not None


async def _lock(seller_id: int, waifu_id: str, listing_id: str):
    await market_locks_col.update_one(
        {'seller_id': seller_id, 'waifu_id': str(waifu_id)},
        {'$set': {'listing_id': listing_id, 'locked_at': _now()}},
        upsert=True,
    )


async def _unlock(seller_id: int, waifu_id: str):
    await market_locks_col.delete_one({'seller_id': seller_id, 'waifu_id': str(waifu_id)})


async def _tax_pot() -> int:
    d = await market_stats_col.find_one({'_id': 'marketplace'})
    return int(d.get('tax_pot', 0)) if d else 0


async def _add_tax(amount: int):
    await market_stats_col.update_one(
        {'_id': 'marketplace'}, {'$inc': {'tax_pot': int(amount)}}, upsert=True,
    )


def _plain_fallback(html: str) -> str:
    """Strip rich-only tags but keep <pre>, <code>, <b> etc."""
    t = _re.sub(r'<img\b[^>]*/?>', '', html, flags=_re.I)
    t = _re.sub(
        r'</?(?:h[1-6]|table|thead|tbody|tr|th|td|details|summary|mark|sub|sup|tg-button|button)(?:\s[^>]*)?>',
        '', t, flags=_re.I,
    )
    t = _re.sub(r'<br\s*/?>', '\n', t, flags=_re.I)
    t = _re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# ══════════════════════════════════════════════════════════════
# ASCII Table Builder (emoji-aware widths)
# ══════════════════════════════════════════════════════════════
def _display_width(s: str) -> int:
    """Emoji count as 2, others as 1."""
    width = 0
    for ch in str(s):
        cp = ord(ch)
        if (0x1F300 <= cp <= 0x1FAFF or
                0x2600 <= cp <= 0x27BF or
                0x1F000 <= cp <= 0x1F2FF or
                0x2190 <= cp <= 0x21FF):
            width += 2
        else:
            width += 1
    return width


def _build_ascii_table(headers, rows) -> str:
    """Return <pre>-wrapped ASCII box-drawing table (emoji-aware)."""
    widths = [_display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _display_width(cell))

    def _pad(cell, w):
        pad = w - _display_width(cell)
        return str(cell) + " " * max(0, pad)

    lines = []
    lines.append("┌" + "┬".join("─" * (w + 2) for w in widths) + "┐")
    lines.append("│" + "│".join(f" {_pad(h, widths[i])} " for i, h in enumerate(headers)) + "│")
    lines.append("├" + "┼".join("─" * (w + 2) for w in widths) + "┤")
    for row in rows:
        lines.append("│" + "│".join(f" {_pad(row[i], widths[i])} " for i in range(len(widths))) + "│")
    lines.append("└" + "┴".join("─" * (w + 2) for w in widths) + "┘")

    table = "\n".join(lines)
    return f"<pre>{_html.escape(table, quote=False)}</pre>"


# ══════════════════════════════════════════════════════════════
# PAGE RENDERER
# Order: Heading → Image → Info → Table → Tip
# ══════════════════════════════════════════════════════════════
def build_marketplace_page(listings, page, total_pages, total) -> str:
    h = []

    # 1. Heading
    h.append(rich_heading("🏪 WAIFU MARKETPLACE", 1))

    # 2. Image (inline in rich message)
    if MARKET_IMG_URL:
        h.append(f'<img src="{rich_esc(MARKET_IMG_URL)}" />')

    if total == 0:
        h.append(rich_note("😔 No active listings. Be the first to /sellwaifu!"))
        return "".join(h)

    # 3. Info line
    h.append(rich_note(
        f"📊 <b>{total}</b> active listings · Page <b>{page}/{total_pages}</b>"
    ))

    # 4. Table
    headers = ["Listing", "Char ID", "Name", "Rarity", "Price"]
    rows = []
    for l in listings:
        nm = str(l.get('waifu_name', 'Unknown'))
        if len(nm) > 14:
            nm = nm[:13] + "…"
        rows.append([
            str(l.get('listing_id', '?')),
            str(l.get('waifu_id', '?')),
            nm,
            _rar_symbol_only(l.get('waifu_rarity', '')),
            f"${_fmt(l.get('price', 0))}",
        ])

    # Try rich table (Kurigram) → ASCII fallback
    if RICH_UI_OK and _rich_table:
        try:
            h.append(_rich_table(headers, rows, border=1))
        except Exception:
            h.append(_build_ascii_table(headers, rows))
    else:
        h.append(_build_ascii_table(headers, rows))

    # 5. Tip
    h.append(rich_note("💡 Use <code>/wbuy &lt;listing_id&gt;</code> to purchase."))

    return "".join(h)


def _market_kb(page, total_pages):
    if total_pages <= 1:
        return None
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("◀️", callback_data=f"mkt:page:{page - 1}"))
    row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="mkt:noop"))
    if page < total_pages:
        row.append(InlineKeyboardButton("▶️", callback_data=f"mkt:page:{page + 1}"))
    return InlineKeyboardMarkup([row])


# ══════════════════════════════════════════════════════════════
# Send / Edit
# ══════════════════════════════════════════════════════════════
async def _send(update, html: str, *, kb=None, with_image: bool = False):
    chat = update.effective_chat
    if not chat:
        return None

    # 1. Rich send via Kurigram
    if RICH_UI_OK and PYRO_OK and _rich_send is not None:
        try:
            return await _rich_send(_Waifuu, chat.id, html, reply_markup=kb)
        except Exception as e:
            LOGGER.warning(f"[marketplace] rich send failed: {e}")

    # 2. Fallback — text with <pre> table, then image separately
    plain = _plain_fallback(html)
    try:
        msg = await update.message.reply_text(
            plain, reply_markup=kb, parse_mode='HTML',
        )
    except Exception as e:
        LOGGER.warning(f"[marketplace] ptb text send failed: {e}")
        return None

    if with_image and MARKET_IMG_URL:
        try:
            await update.message.reply_photo(photo=MARKET_IMG_URL)
        except Exception as e:
            LOGGER.warning(f"[marketplace] photo fallback failed: {e}")

    return msg


async def _edit(query, html: str, *, kb=None):
    # 1. Rich edit
    if RICH_UI_OK and PYRO_OK and _rich_edit is not None:
        try:
            return await _rich_edit(
                _Waifuu, html,
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                reply_markup=kb,
            )
        except Exception as e:
            LOGGER.warning(f"[marketplace] rich edit failed: {e}")

    # 2. Text edit
    plain = _plain_fallback(html)
    try:
        await query.edit_message_text(plain, reply_markup=kb, parse_mode='HTML')
    except BadRequest:
        pass


# ══════════════════════════════════════════════════════════════
# /market
# ══════════════════════════════════════════════════════════════
async def _render_market(update, page=1, edit_query=None):
    total = await marketplace_col.count_documents({'status': 'ACTIVE'})
    total_pages = max(1, (total + LISTINGS_PER_PAGE - 1) // LISTINGS_PER_PAGE)
    page = max(1, min(page, total_pages))

    cursor = (marketplace_col
              .find({'status': 'ACTIVE'})
              .sort('created_at', -1)
              .skip((page - 1) * LISTINGS_PER_PAGE)
              .limit(LISTINGS_PER_PAGE))
    listings = await cursor.to_list(length=LISTINGS_PER_PAGE)

    html = build_marketplace_page(listings, page, total_pages, total)
    kb = _market_kb(page, total_pages)

    if edit_query:
        return await _edit(edit_query, html, kb=kb)
    return await _send(update, html, kb=kb, with_image=True)


async def market(update: Update, context: CallbackContext):
    await _render_market(update, page=1)


# ══════════════════════════════════════════════════════════════
# /sellwaifu
# ══════════════════════════════════════════════════════════════
async def sellwaifu(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args or []

    if len(args) != 2:
        await _send(update, "❌ Usage: <code>/sellwaifu &lt;waifu_id&gt; &lt;price&gt;</code>")
        return

    waifu_id = str(args[0]).strip()
    try:
        price = int(args[1])
    except ValueError:
        await _send(update, "❌ Invalid price.")
        return

    if price < MIN_PRICE or price > MAX_PRICE:
        await _send(update, f"❌ Price must be {_fmt(MIN_PRICE)}–{_fmt(MAX_PRICE)}.")
        return

    user_doc = await user_collection.find_one({'id': user.id})
    if not user_doc or not user_doc.get('characters'):
        await _send(update, "❌ You don't own any characters.")
        return

    matched = next(
        (c for c in user_doc['characters'] if str(c.get('id', '')).strip() == waifu_id),
        None,
    )
    if not matched:
        await _send(update, f"❌ You don't own waifu <code>{rich_esc(waifu_id)}</code>.")
        return

    if await marketplace_col.find_one(
        {'seller_id': user.id, 'waifu_id': waifu_id, 'status': 'ACTIVE'}
    ):
        await _send(update, "❌ Already listed.")
        return

    if await is_waifu_locked(user.id, waifu_id):
        await _send(update, "❌ This waifu is already locked.")
        return

    tax = int(round(price * MARKET_TAX_RATE))
    gets = price - tax
    snap = _snap(matched)
    rar = _rar_symbol_only(snap['rarity'])

    headers = ["Field", "Value"]
    rows = [
        ["🌸 Name", f"<b>{rich_esc(snap['name'])}</b>"],
        ["⭐ Rarity", f"{rar} <b>{rich_esc(snap['rarity'])}</b>"],
        ["🆔 Char ID", rich_code(snap['id'])],
        ["💰 Price", f"<b>{_fmt(price)}</b>"],
        ["🏦 Tax (5%)", f"<b>{_fmt(tax)}</b>"],
        ["💵 You receive", f"<b>{_fmt(gets)}</b>"],
    ]

    if RICH_UI_OK and _rich_table:
        try:
            table_html = _rich_table(headers, rows, border=1)
        except Exception:
            table_html = _build_ascii_table(headers, rows)
    else:
        table_html = _build_ascii_table(headers, rows)

    body = (
        rich_heading("🏪 LIST WAIFU", 2)
        + table_html
        + rich_note("Confirm to create this listing?")
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ LIST FOR SALE",
                             callback_data=f"mkt:sell:ok:{waifu_id}:{price}"),
        InlineKeyboardButton("❌ CANCEL", callback_data="mkt:cancel"),
    ]])
    await _send(update, body, kb=kb)


async def _do_sell(query, waifu_id: str, price: int):
    user = query.from_user
    user_doc = await user_collection.find_one({'id': user.id})
    if not user_doc:
        await query.answer("No collection.", show_alert=True)
        return

    matched = next(
        (c for c in user_doc.get('characters', []) if str(c.get('id', '')).strip() == waifu_id),
        None,
    )
    if not matched:
        await query.answer("Not in collection.", show_alert=True)
        return

    if await marketplace_col.find_one(
        {'seller_id': user.id, 'waifu_id': waifu_id, 'status': 'ACTIVE'}
    ):
        await query.answer("Already listed.", show_alert=True)
        return

    if await is_waifu_locked(user.id, waifu_id):
        await query.answer("Already locked.", show_alert=True)
        return

    listing_id = None
    for _ in range(8):
        c = _gen_listing_id()
        if not await marketplace_col.find_one({'listing_id': c}):
            listing_id = c
            break
    if not listing_id:
        await query.answer("Try again.", show_alert=True)
        return

    snap = _snap(matched)
    now = _now()
    doc = {
        'listing_id': listing_id,
        'seller_id': user.id,
        'seller_username': user.username,
        'seller_first_name': user.first_name,
        'waifu_id': snap['id'],
        'waifu_name': snap['name'],
        'waifu_anime': snap['anime'],
        'waifu_rarity': snap['rarity'],
        'waifu_img_url': snap['img_url'],
        'waifu_snapshot': snap,
        'price': price,
        'tax_rate': MARKET_TAX_RATE,
        'status': 'ACTIVE',
        'created_at': now,
        'updated_at': now,
        'sold_at': None,
        'buyer_id': None,
    }

    try:
        await marketplace_col.insert_one(doc)
        await _lock(user.id, waifu_id, listing_id)
    except Exception as e:
        LOGGER.error(f"[marketplace] sell insert: {e}")
        await query.answer("Failed.", show_alert=True)
        return

    tax = int(round(price * MARKET_TAX_RATE))
    txt = (
        f"✅ <b>Listing created</b>\n\n"
        f"🆔 <code>{listing_id}</code>\n"
        f"🌸 {rich_esc(snap['name'])}\n"
        f"💰 <b>{_fmt(price)}</b>\n"
        f"💵 You'll receive: <b>{_fmt(price - tax)}</b>"
    )
    try:
        await query.edit_message_text(_plain_fallback(txt), parse_mode='HTML')
    except Exception:
        try:
            await query.edit_message_text(txt, parse_mode='HTML')
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# /wbuy
# ══════════════════════════════════════════════════════════════
async def wbuy(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args or []
    if len(args) != 1:
        await _send(update, "❌ Usage: <code>/wbuy &lt;listing_id&gt;</code>")
        return

    lid = args[0].strip().upper()
    listing = await marketplace_col.find_one({'listing_id': lid})
    if not listing:
        await _send(update, "❌ Listing not found.")
        return
    if listing.get('status') != 'ACTIVE':
        await _send(update, f"❌ Listing is <b>{listing.get('status')}</b>.")
        return
    if listing.get('seller_id') == user.id:
        await _send(update, "❌ You can't buy your own listing.")
        return

    price = int(listing['price'])
    bal = await get_balance(user.id)
    if bal < price:
        await _send(update, f"❌ Need <b>{_fmt(price)}</b>, you have <b>{_fmt(bal)}</b>.")
        return

    seller = await user_collection.find_one({'id': listing['seller_id']})
    if not seller or not any(
        str(c.get('id', '')).strip() == str(listing['waifu_id'])
        for c in seller.get('characters', [])
    ):
        await marketplace_col.update_one({'listing_id': lid}, {'$set': {'status': 'EXPIRED'}})
        await _unlock(listing['seller_id'], listing['waifu_id'])
        await _send(update, "❌ Seller no longer owns this waifu. Listing expired.")
        return

    rar = _rar_symbol_only(listing['waifu_rarity'])
    headers = ["Field", "Value"]
    rows = [
        ["🌸 Waifu", f"<b>{rich_esc(listing['waifu_name'])}</b>"],
        ["⭐ Rarity", f"{rar} <b>{rich_esc(listing['waifu_rarity'])}</b>"],
        ["🆔 Char ID", rich_code(listing['waifu_id'])],
        ["💰 Price", f"<b>{_fmt(price)}</b>"],
        ["💳 Your balance", f"<b>{_fmt(bal)}</b>"],
    ]

    if RICH_UI_OK and _rich_table:
        try:
            table_html = _rich_table(headers, rows, border=1)
        except Exception:
            table_html = _build_ascii_table(headers, rows)
    else:
        table_html = _build_ascii_table(headers, rows)

    body = (
        rich_heading("🛒 PURCHASE CONFIRMATION", 2)
        + table_html
        + rich_note("Are you sure you want to buy this waifu?")
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ CONFIRM", callback_data=f"mkt:buy:ok:{lid}"),
        InlineKeyboardButton("❌ CANCEL", callback_data="mkt:cancel"),
    ]])
    await _send(update, body, kb=kb)


async def _do_buy(query, lid: str):
    buyer = query.from_user
    now = _now()

    claim = await marketplace_col.update_one(
        {'listing_id': lid, 'status': 'ACTIVE'},
        {'$set': {'status': 'PROCESSING', 'buyer_id': buyer.id, 'processing_at': now}},
    )
    if claim.modified_count == 0:
        await query.answer("❌ Listing no longer available.", show_alert=True)
        return

    listing = await marketplace_col.find_one({'listing_id': lid})
    if not listing:
        await query.answer("Listing missing.", show_alert=True)
        return

    async def rollback(reason):
        await marketplace_col.update_one(
            {'listing_id': lid, 'status': 'PROCESSING'},
            {'$set': {'status': 'ACTIVE', 'buyer_id': None, 'processing_at': None}},
        )
        LOGGER.error(f"[mkt] rollback {lid}: {reason}")
        await query.answer(f"❌ {reason}", show_alert=True)

    price = int(listing['price'])
    tax = int(round(price * float(listing.get('tax_rate', MARKET_TAX_RATE))))
    gets = price - tax
    seller_id = listing['seller_id']
    waifu_id = str(listing['waifu_id'])

    bal = await get_balance(buyer.id)
    if bal < price:
        await rollback("Balance changed")
        return

    d = await coins_collection.update_one(
        {'user_id': buyer.id, 'coins': {'$gte': price}},
        {'$inc': {'coins': -price}},
    )
    if d.modified_count == 0:
        await rollback("Balance changed")
        return

    seller = await user_collection.find_one({'id': seller_id})
    if not seller:
        await coins_collection.update_one({'user_id': buyer.id}, {'$inc': {'coins': price}})
        await rollback("Seller gone")
        return

    seller_chars = list(seller.get('characters', []))
    removed, new_chars = False, []
    for c in seller_chars:
        if not removed and str(c.get('id', '')).strip() == waifu_id:
            removed = True
            continue
        new_chars.append(c)

    if not removed:
        await coins_collection.update_one({'user_id': buyer.id}, {'$inc': {'coins': price}})
        await rollback("Seller no longer owns waifu")
        return

    s = await user_collection.update_one({'id': seller_id}, {'$set': {'characters': new_chars}})
    if s.modified_count == 0:
        await coins_collection.update_one({'user_id': buyer.id}, {'$inc': {'coins': price}})
        await rollback("Seller update failed")
        return

    snap = listing.get('waifu_snapshot') or _snap({
        'id': waifu_id, 'name': listing.get('waifu_name'),
        'rarity': listing.get('waifu_rarity'), 'anime': listing.get('waifu_anime'),
        'img_url': listing.get('waifu_img_url'),
    })
    buyer_doc = await user_collection.find_one({'id': buyer.id})
    if buyer_doc:
        await user_collection.update_one({'id': buyer.id}, {'$push': {'characters': snap}})
    else:
        await user_collection.insert_one({
            'id': buyer.id, 'username': buyer.username,
            'first_name': buyer.first_name, 'characters': [snap],
        })

    await coins_collection.update_one({'user_id': seller_id}, {'$inc': {'coins': gets}}, upsert=True)
    await _add_tax(tax)

    await marketplace_col.update_one({'listing_id': lid}, {'$set': {
        'status': 'SOLD', 'sold_at': _now(), 'updated_at': _now(),
        'buyer_id': buyer.id, 'tax_paid': tax, 'seller_received': gets,
    }})
    await _unlock(seller_id, waifu_id)

    txn_id = "TXN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=9))
    await market_txn_col.insert_one({
        'transaction_id': txn_id, 'listing_id': lid,
        'buyer_id': buyer.id, 'seller_id': seller_id,
        'waifu_id': waifu_id, 'waifu_name': listing.get('waifu_name'),
        'amount': price, 'tax': tax, 'seller_received': gets,
        'timestamp': _now(), 'status': 'COMPLETED',
    })

    try:
        await query.edit_message_text(
            f"✅ <b>Purchase complete</b>\n\n"
            f"🌸 {rich_esc(listing.get('waifu_name', ''))}\n"
            f"💰 Paid: <b>{_fmt(price)}</b>\n"
            f"📜 <code>{txn_id}</code>",
            parse_mode='HTML',
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# /cancelsell
# ══════════════════════════════════════════════════════════════
async def cancelsell(update: Update, context: CallbackContext):
    user = update.effective_user
    args = context.args or []
    if len(args) != 1:
        await _send(update, "❌ Usage: <code>/cancelsell &lt;listing_id&gt;</code>")
        return

    lid = args[0].strip().upper()
    listing = await marketplace_col.find_one({'listing_id': lid})
    if not listing:
        await _send(update, "❌ Listing not found.")
        return
    if listing.get('seller_id') != user.id:
        await _send(update, "❌ Not your listing.")
        return
    if listing.get('status') != 'ACTIVE':
        await _send(update, f"❌ Listing is <b>{listing.get('status')}</b>.")
        return

    await marketplace_col.update_one(
        {'listing_id': lid},
        {'$set': {'status': 'CANCELLED', 'updated_at': _now()}},
    )
    await _unlock(user.id, listing['waifu_id'])
    await _send(update, f"✅ Listing <code>{lid}</code> cancelled.")


# ══════════════════════════════════════════════════════════════
# /mylistings
# ══════════════════════════════════════════════════════════════
async def _render_my(update, user_id, page=1, edit_query=None):
    total = await marketplace_col.count_documents({'seller_id': user_id, 'status': 'ACTIVE'})
    total_pages = max(1, (total + LISTINGS_PER_PAGE - 1) // LISTINGS_PER_PAGE)
    page = max(1, min(page, total_pages))

    cursor = (marketplace_col.find({'seller_id': user_id, 'status': 'ACTIVE'})
              .sort('created_at', -1)
              .skip((page - 1) * LISTINGS_PER_PAGE)
              .limit(LISTINGS_PER_PAGE))
    listings = await cursor.to_list(length=LISTINGS_PER_PAGE)

    h = [rich_heading("📦 MY MARKETPLACE LISTINGS", 2)]
    if total == 0:
        h.append(rich_note("You have no active listings."))
    else:
        h.append(rich_note(f"📊 {total} active · Page {page}/{total_pages}"))
        headers = ["Listing", "Char ID", "Name", "Rarity", "Price"]
        rows = []
        for l in listings:
            nm = str(l['waifu_name'])
            if len(nm) > 14:
                nm = nm[:13] + "…"
            rows.append([
                str(l['listing_id']),
                str(l.get('waifu_id', '?')),
                nm,
                _rar_symbol_only(l.get('waifu_rarity', '')),
                f"${_fmt(l['price'])}",
            ])

        if RICH_UI_OK and _rich_table:
            try:
                h.append(_rich_table(headers, rows, border=1))
            except Exception:
                h.append(_build_ascii_table(headers, rows))
        else:
            h.append(_build_ascii_table(headers, rows))

    kb = None
    if total > 1:
        row = []
        if page > 1:
            row.append(InlineKeyboardButton("◀️", callback_data=f"mkt:mylist:{page - 1}"))
        row.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data="mkt:noop"))
        if page < total_pages:
            row.append(InlineKeyboardButton("▶️", callback_data=f"mkt:mylist:{page + 1}"))
        kb = InlineKeyboardMarkup([row])

    if edit_query:
        return await _edit(edit_query, "".join(h), kb=kb)
    return await _send(update, "".join(h), kb=kb)


async def mylistings(update: Update, context: CallbackContext):
    await _render_my(update, update.effective_user.id, 1)


# ══════════════════════════════════════════════════════════════
# /marketstats
# ══════════════════════════════════════════════════════════════
async def marketstats(update: Update, context: CallbackContext):
    if not _is_sudo(update.effective_user.id):
        await _send(update, "❌ Sudo only.")
        return

    active = await marketplace_col.count_documents({'status': 'ACTIVE'})
    sold = await marketplace_col.count_documents({'status': 'SOLD'})
    cancelled = await marketplace_col.count_documents({'status': 'CANCELLED'})
    txns = await market_txn_col.count_documents({})
    pot = await _tax_pot()

    headers = ["Metric", "Value"]
    rows = [
        ["🟢 Active", f"<b>{active}</b>"],
        ["✅ Sold", f"<b>{sold}</b>"],
        ["❌ Cancelled", f"<b>{cancelled}</b>"],
        ["📜 Txns", f"<b>{txns}</b>"],
        ["💰 Tax pot", f"<b>{_fmt(pot)}</b>"],
    ]

    if RICH_UI_OK and _rich_table:
        try:
            table_html = _rich_table(headers, rows, border=1)
        except Exception:
            table_html = _build_ascii_table(headers, rows)
    else:
        table_html = _build_ascii_table(headers, rows)

    body = rich_heading("🏦 MARKETPLACE STATS", 2) + table_html
    await _send(update, body)


# ══════════════════════════════════════════════════════════════
# Callback dispatcher
# ══════════════════════════════════════════════════════════════
async def market_cb(update: Update, context: CallbackContext):
    q = update.callback_query
    data = q.data or ""

    if data == "mkt:noop":
        await q.answer()
        return

    if data == "mkt:cancel":
        await q.answer("Cancelled")
        try:
            await q.edit_message_text("❌ Cancelled.")
        except Exception:
            pass
        return

    if data.startswith("mkt:page:"):
        try:
            page = int(data.split(":")[2])
        except Exception:
            page = 1
        await q.answer()
        await _render_market(None, page=page, edit_query=q)
        return

    if data.startswith("mkt:mylist:"):
        try:
            page = int(data.split(":")[2])
        except Exception:
            page = 1
        await q.answer()
        await _render_my(None, q.from_user.id, page=page, edit_query=q)
        return

    if data.startswith("mkt:sell:ok:"):
        parts = data.split(":")
        if len(parts) < 5:
            await q.answer("Bad data.", show_alert=True)
            return
        try:
            wid, price = parts[3], int(parts[4])
        except Exception:
            await q.answer("Bad data.", show_alert=True)
            return
        await q.answer("Creating...")
        await _do_sell(q, wid, price)
        return

    if data.startswith("mkt:buy:ok:"):
        lid = data.split(":", 3)[3]
        await q.answer()
        await _do_buy(q, lid)
        return

    await q.answer()


# ══════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════
application.add_handler(CommandHandler(["market", "marketplace"], market, block=False))
application.add_handler(CommandHandler("sellwaifu", sellwaifu, block=False))
application.add_handler(CommandHandler(["wbuy", "buywaifu"], wbuy, block=False))
application.add_handler(CommandHandler(["cancelsell", "unsell"], cancelsell, block=False))
application.add_handler(CommandHandler("mylistings", mylistings, block=False))
application.add_handler(CommandHandler("marketstats", marketstats, block=False))

application.add_handler(CallbackQueryHandler(market_cb, pattern=r'^mkt:', block=False))

# Indexes
try:
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(ensure_indexes())
except Exception as _e:
    LOGGER.warning(f"[marketplace] index schedule: {_e}")
