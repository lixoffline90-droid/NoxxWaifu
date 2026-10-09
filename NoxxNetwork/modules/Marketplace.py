"""
Waifu Marketplace — Secure Rich UI (Kurigram)
Commands:
    /market               - browse listings (paginated, 10/page)
    /marketplace          - alias
    /sellwaifu <id> <price>
    /wbuy <listing_id>
    /buywaifu <listing_id> - alias
    /cancelsell <listing_id>
    /unsell <listing_id>   - alias
    /mylistings
    /marketstats          (sudo/owner only)
"""
from __future__ import annotations

import html as _html
import os
import random
import re as _re
import secrets
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
# CONFIG
# ══════════════════════════════════════════════════════════════
MARKET_IMG_URL = os.getenv("MARKET_IMG_URL", "https://i.ibb.co/8gvNGSbL/26831adc4ea1.jpg")
MARKET_TAX_RATE = 0.05
LISTINGS_PER_PAGE = 10
LISTING_ID_LEN = 7
LISTING_PREFIX = "MKT"
MIN_PRICE = 1
MAX_PRICE = 10_000_000
PENDING_TTL = 300             # 5 minutes to confirm
PROCESSING_TIMEOUT = 300      # 5 minutes before recovery considers a txn stuck


# ══════════════════════════════════════════════════════════════
# COINS MODULE
# ══════════════════════════════════════════════════════════════
try:
    from NoxxNetwork.modules.coin import coins_collection
except Exception as _e:
    LOGGER.warning(f"[marketplace] coin module missing: {_e}")
    coins_collection = db['user_coins']


async def get_balance(user_id: int) -> int:
    doc = await coins_collection.find_one({'user_id': user_id})
    return int(doc.get('coins', 0)) if doc else 0


# ══════════════════════════════════════════════════════════════
# FALLBACK HELPERS (HTML-safe)
# ══════════════════════════════════════════════════════════════
def _esc(v) -> str:
    """Escape untrusted text for HTML output."""
    if v is None:
        return ""
    return _html.escape(str(v), quote=False)


def _fb_heading(text: str, level: int = 2) -> str:
    return f"<b>{text}</b>\n"


def _fb_note(text: str, expandable: bool = False) -> str:
    return f"<blockquote>{text}</blockquote>"


def _fb_code(value) -> str:
    return f"<code>{_esc(value)}</code>"


# ══════════════════════════════════════════════════════════════
# RICH UI IMPORT
# ══════════════════════════════════════════════════════════════
RICH_UI_OK = False
_rich_send = _rich_edit = None
_rich_esc = _rich_heading = _rich_table = _rich_note = _rich_code = None

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
    return _esc(v)


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


def rich_table(headers, rows, border=1):
    if RICH_UI_OK and _rich_table:
        try:
            return _rich_table(headers, rows, border=border)
        except Exception as e:
            LOGGER.warning(f"[marketplace] rich_table failed: {e}")
    return _build_ascii_table(headers, rows)


# ─── Pyrogram client ──────────────────────────────────────────
try:
    from NoxxNetwork import Waifuu as _Waifuu
except Exception:
    _Waifuu = None

PYRO_OK = _Waifuu is not None


# ══════════════════════════════════════════════════════════════
# COLLECTIONS
# ══════════════════════════════════════════════════════════════
marketplace_col = db['marketplace_listings']
market_txn_col = db['marketplace_transactions']
market_stats_col = db['marketplace_stats']
market_locks_col = db['marketplace_locks']
market_pending_col = db['marketplace_pending']


# ══════════════════════════════════════════════════════════════
# HELPERS
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
    return LISTING_PREFIX + "".join(random.choices(alphabet, k=LISTING_ID_LEN - len(LISTING_PREFIX)))


def _snap(c: dict) -> dict:
    return {
        'id': str(c.get('id', '')),
        'name': str(c.get('name', 'Unknown')),
        'anime': str(c.get('anime', '')),
        'rarity': str(c.get('rarity', '⚪ Common')),
        'img_url': str(c.get('img_url', '')),
        'emoji': str(c.get('emoji', '') or ''),
    }


def _rar_symbol_only(value) -> str:
    if not value:
        return "⚪"
    s = str(value).strip()
    if not s:
        return "⚪"
    first = s.split()[0] if s.split() else ""
    if first and not first[0].isalnum():
        return first
    return "⚪"


def _valid_price(p) -> bool:
    try:
        p = int(p)
    except (TypeError, ValueError):
        return False
    return MIN_PRICE <= p <= MAX_PRICE


# ══════════════════════════════════════════════════════════════
# INDEXES
# ══════════════════════════════════════════════════════════════
async def ensure_indexes():
    try:
        # Unique per listing_id
        await marketplace_col.create_index('listing_id', unique=True)
        # Query helpers
        await marketplace_col.create_index('status')
        await marketplace_col.create_index('seller_id')
        await marketplace_col.create_index('waifu_id')
        await marketplace_col.create_index([('status', 1), ('created_at', -1)])
        # Prevent duplicate active listing for same (seller, waifu)
        # Partial unique index — only enforced for ACTIVE listings
        try:
            await marketplace_col.create_index(
                [('seller_id', 1), ('waifu_id', 1)],
                unique=True,
                partialFilterExpression={'status': 'ACTIVE'},
                name='uniq_active_seller_waifu',
            )
        except Exception as e:
            LOGGER.warning(f"[marketplace] partial unique index: {e}")
        # Locks
        await market_locks_col.create_index([('seller_id', 1), ('waifu_id', 1)], unique=True)
        await market_locks_col.create_index('listing_id')
        # Pending confirmations
        await market_pending_col.create_index('token', unique=True)
        await market_pending_col.create_index('expires_at')
        # Transactions
        await market_txn_col.create_index('transaction_id', unique=True)
        await market_txn_col.create_index('listing_id')
        await market_txn_col.create_index('timestamp')
        LOGGER.info("[marketplace] indexes ensured")
    except Exception as e:
        LOGGER.warning(f"[marketplace] index setup: {e}")


# ══════════════════════════════════════════════════════════════
# LOCK MANAGEMENT
# ══════════════════════════════════════════════════════════════
async def is_waifu_locked(user_id: int, waifu_id: str) -> bool:
    doc = await market_locks_col.find_one({'seller_id': int(user_id), 'waifu_id': str(waifu_id)})
    return doc is not None


async def _lock(seller_id: int, waifu_id: str, listing_id: str):
    await market_locks_col.update_one(
        {'seller_id': int(seller_id), 'waifu_id': str(waifu_id)},
        {'$set': {
            'listing_id': listing_id,
            'locked_at': _now(),
        }},
        upsert=True,
    )


async def _unlock(seller_id: int, waifu_id: str, listing_id: str | None = None):
    """Unlock — if listing_id given, only delete if it matches (safety)."""
    query = {'seller_id': int(seller_id), 'waifu_id': str(waifu_id)}
    if listing_id is not None:
        query['listing_id'] = listing_id
    await market_locks_col.delete_one(query)


# ══════════════════════════════════════════════════════════════
# PENDING CONFIRMATIONS (secure tokens)
# ══════════════════════════════════════════════════════════════
async def _create_pending(user_id: int, action: str, params: dict, ttl: int = PENDING_TTL) -> str:
    """Create a pending confirmation. Returns token."""
    token = secrets.token_urlsafe(16)
    await market_pending_col.insert_one({
        'token': token,
        'user_id': int(user_id),
        'action': action,
        'params': params,
        'created_at': _now(),
        'expires_at': _now() + ttl,
        'consumed': False,
    })
    return token


async def _consume_pending(token: str, user_id: int) -> dict | None:
    """Atomically consume a pending confirmation.
    Returns the doc if valid + owned by user, else None.
    """
    if not token or not isinstance(token, str):
        return None
    doc = await market_pending_col.find_one_and_update(
        {
            'token': token,
            'user_id': int(user_id),
            'consumed': False,
            'expires_at': {'$gt': _now()},
        },
        {'$set': {'consumed': True, 'consumed_at': _now()}},
        return_document=True,  # ReturnDocument.AFTER
    )
    return doc


async def _cleanup_expired_pendings():
    try:
        await market_pending_col.delete_many({
            'expires_at': {'$lt': _now() - 3600},
        })
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# RECOVERY — stuck PROCESSING listings
# ══════════════════════════════════════════════════════════════
async def _recover_stuck_processings():
    """On startup, reconcile listings stuck in PROCESSING.
    - If a completed transaction exists for the listing → mark SOLD, unlock
    - Else → mark FAILED (needs admin). We DO NOT auto-revert to ACTIVE,
      because we can't prove whether coin/waifu changes were applied.
    """
    cutoff = _now() - PROCESSING_TIMEOUT
    fixed = 0
    failed = 0
    try:
        async for l in marketplace_col.find({
            'status': 'PROCESSING',
            'processing_at': {'$lt': cutoff},
        }):
            lid = l['listing_id']
            txn = await market_txn_col.find_one({'listing_id': lid, 'status': 'COMPLETED'})
            if txn:
                await marketplace_col.update_one(
                    {'listing_id': lid},
                    {'$set': {'status': 'SOLD', 'updated_at': _now(),
                              'sold_at': txn.get('timestamp', _now())}},
                )
                await _unlock(l['seller_id'], l['waifu_id'], lid)
                fixed += 1
            else:
                # Uncertain state → mark FAILED
                await marketplace_col.update_one(
                    {'listing_id': lid},
                    {'$set': {'status': 'FAILED', 'updated_at': _now()}},
                )
                failed += 1
        if fixed or failed:
            LOGGER.info(f"[marketplace] recovery: sold={fixed} failed={failed}")
    except Exception as e:
        LOGGER.warning(f"[marketplace] recovery error: {e}")


# ══════════════════════════════════════════════════════════════
# PLAIN FALLBACK
# ══════════════════════════════════════════════════════════════
def _plain_fallback(html: str) -> str:
    t = _re.sub(r'<img\b[^>]*/?>', '', html, flags=_re.I)
    t = _re.sub(
        r'</?(?:h[1-6]|table|thead|tbody|tr|th|td|details|summary|mark|sub|sup|tg-button|button)(?:\s[^>]*)?>',
        '', t, flags=_re.I,
    )
    t = _re.sub(r'<br\s*/?>', '\n', t, flags=_re.I)
    t = _re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


# ══════════════════════════════════════════════════════════════
# ASCII TABLE (emoji-aware)
# ══════════════════════════════════════════════════════════════
def _display_width(s: str) -> int:
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
    """Build ASCII table, HTML-escape content, wrap in <pre>."""
    headers = [str(h) for h in headers]
    rows = [[str(c) if c is not None else "" for c in r] for r in rows]

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
# ══════════════════════════════════════════════════════════════
def build_marketplace_page(listings, page, total_pages, total) -> str:
    h = [rich_heading("🏪 WAIFU MARKETPLACE", 1)]

    if MARKET_IMG_URL:
        h.append(f'<img src="{rich_esc(MARKET_IMG_URL)}" />')

    if total == 0:
        h.append(rich_note("😔 No active listings. Be the first to /sellwaifu!"))
        return "".join(h)

    h.append(rich_note(
        f"📊 <b>{total}</b> active listings · Page <b>{page}/{total_pages}</b>"
    ))

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

    h.append(rich_table(headers, rows, border=1))
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
# SEND / EDIT
# ══════════════════════════════════════════════════════════════
async def _send(update, html: str, *, kb=None, with_image: bool = False):
    chat = update.effective_chat
    if not chat:
        LOGGER.warning("[marketplace] _send: no chat")
        return None

    LOGGER.info(f"[marketplace] _send chat={chat.id} rich_ok={RICH_UI_OK} pyro_ok={PYRO_OK}")

    # 1. Rich send
    if RICH_UI_OK and PYRO_OK and _rich_send is not None:
        try:
            result = await _rich_send(_Waifuu, chat.id, html, reply_markup=kb)
            if result:
                LOGGER.info("[marketplace] rich send OK")
                return result
            LOGGER.warning("[marketplace] rich send returned None → PTB fallback")
        except Exception as e:
            LOGGER.warning(f"[marketplace] rich send exception: {e} → PTB fallback")

    # 2. PTB fallback
    plain = _plain_fallback(html)
    try:
        msg = await update.message.reply_text(
            plain, reply_markup=kb, parse_mode='HTML',
        )
        LOGGER.info("[marketplace] PTB fallback OK")
        return msg
    except Exception as e:
        LOGGER.error(f"[marketplace] PTB text failed: {e}")

    # 3. Photo fallback
    if with_image and MARKET_IMG_URL:
        try:
            await update.message.reply_photo(photo=MARKET_IMG_URL)
            LOGGER.info("[marketplace] photo fallback OK")
        except Exception as e:
            LOGGER.warning(f"[marketplace] photo fallback failed: {e}")

    return None


async def _edit(query, html: str, *, kb=None):
    try:
        if RICH_UI_OK and PYRO_OK and _rich_edit is not None:
            result = await _rich_edit(
                _Waifuu, html,
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                reply_markup=kb,
            )
            if result:
                return result
    except Exception as e:
        LOGGER.warning(f"[marketplace] rich edit failed: {e}")

    plain = _plain_fallback(html)
    try:
        await query.edit_message_text(plain, reply_markup=kb, parse_mode='HTML')
    except BadRequest:
        pass
    except Exception as e:
        LOGGER.warning(f"[marketplace] edit fallback failed: {e}")


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
    try:
        await _render_market(update, page=1)
    except Exception as e:
        LOGGER.exception(f"[marketplace] market error: {e}")


# ══════════════════════════════════════════════════════════════
# /sellwaifu <waifu_id> <price>
# ══════════════════════════════════════════════════════════════
async def sellwaifu(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        args = context.args or []

        LOGGER.info(f"[sellwaifu] user={user.id} args={args}")

        if len(args) != 2:
            await _send(update, "❌ Usage: <code>/sellwaifu &lt;waifu_id&gt; &lt;price&gt;</code>")
            return

        waifu_id = str(args[0]).strip()
        try:
            price = int(args[1])
        except ValueError:
            await _send(update, "❌ Invalid price.")
            return

        if not _valid_price(price):
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

        # Check existing ACTIVE listing
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

        # Secure pending token (not raw data)
        token = await _create_pending(
            user.id, 'sell',
            {'waifu_id': waifu_id, 'price': price, 'waifu_name': snap['name']},
        )

        rows = [
            ["🌸 Name", f"<b>{rich_esc(snap['name'])}</b>"],
            ["⭐ Rarity", f"{rar} <b>{rich_esc(snap['rarity'])}</b>"],
            ["🆔 Char ID", rich_code(snap['id'])],
            ["💰 Price", f"<b>{_fmt(price)}</b>"],
            ["🏦 Tax (5%)", f"<b>{_fmt(tax)}</b>"],
            ["💵 You receive", f"<b>{_fmt(gets)}</b>"],
        ]
        body = (
            rich_heading("🏪 LIST WAIFU", 2)
            + rich_table(["Field", "Value"], rows, border=1)
            + rich_note("Confirm to create this listing?")
        )

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ LIST FOR SALE", callback_data=f"mkt:yes:{token}"),
            InlineKeyboardButton("❌ CANCEL", callback_data=f"mkt:no:{token}"),
        ]])
        await _send(update, body, kb=kb)
    except Exception as e:
        LOGGER.exception(f"[sellwaifu] error: {e}")


# ══════════════════════════════════════════════════════════════
# /wbuy <listing_id>
# ══════════════════════════════════════════════════════════════
async def wbuy(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        args = context.args or []

        LOGGER.info(f"[wbuy] user={user.id} args={args}")

        if len(args) != 1:
            await _send(update, "❌ Usage: <code>/wbuy &lt;listing_id&gt;</code>")
            return

        lid = str(args[0]).strip().upper()
        if not _re.match(r'^MKT[A-Z0-9]{2,12}$', lid):
            await _send(update, "❌ Invalid listing ID format.")
            return

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

        # Verify seller still owns
        seller = await user_collection.find_one({'id': listing['seller_id']})
        if not seller or not any(
            str(c.get('id', '')).strip() == str(listing['waifu_id'])
            for c in seller.get('characters', [])
        ):
            await marketplace_col.update_one({'listing_id': lid}, {'$set': {'status': 'EXPIRED'}})
            await _unlock(listing['seller_id'], listing['waifu_id'], lid)
            await _send(update, "❌ Seller no longer owns this waifu. Listing expired.")
            return

        rar = _rar_symbol_only(listing['waifu_rarity'])
        token = await _create_pending(
            user.id, 'buy',
            {'listing_id': lid, 'price': price},
        )

        rows = [
            ["🌸 Waifu", f"<b>{rich_esc(listing['waifu_name'])}</b>"],
            ["⭐ Rarity", f"{rar} <b>{rich_esc(listing['waifu_rarity'])}</b>"],
            ["🆔 Char ID", rich_code(listing['waifu_id'])],
            ["💰 Price", f"<b>{_fmt(price)}</b>"],
            ["💳 Your balance", f"<b>{_fmt(bal)}</b>"],
        ]
        body = (
            rich_heading("🛒 PURCHASE CONFIRMATION", 2)
            + rich_table(["Field", "Value"], rows, border=1)
            + rich_note("Are you sure you want to buy this waifu?")
        )

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ CONFIRM", callback_data=f"mkt:yes:{token}"),
            InlineKeyboardButton("❌ CANCEL", callback_data=f"mkt:no:{token}"),
        ]])
        await _send(update, body, kb=kb)
    except Exception as e:
        LOGGER.exception(f"[wbuy] error: {e}")


# ══════════════════════════════════════════════════════════════
# EXECUTE SELL (after confirmation)
# ══════════════════════════════════════════════════════════════
async def _exec_sell(query, user_id: int, params: dict):
    waifu_id = str(params.get('waifu_id', ''))
    price = int(params.get('price', 0))

    if not _valid_price(price) or not waifu_id:
        await query.answer("Invalid params.", show_alert=True)
        return

    user_doc = await user_collection.find_one({'id': user_id})
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
        {'seller_id': user_id, 'waifu_id': waifu_id, 'status': 'ACTIVE'}
    ):
        await query.answer("Already listed.", show_alert=True)
        return

    if await is_waifu_locked(user_id, waifu_id):
        await query.answer("Already locked.", show_alert=True)
        return

    # Generate unique listing id
    listing_id = None
    for _ in range(10):
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
        'seller_id': user_id,
        'seller_username': getattr(query.from_user, 'username', None),
        'seller_first_name': getattr(query.from_user, 'first_name', None),
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

    # Insert first, then lock (rollback insert if lock fails)
    try:
        await marketplace_col.insert_one(doc)
    except Exception as e:
        LOGGER.error(f"[sell] insert failed: {e}")
        await query.answer("Failed to create listing.", show_alert=True)
        return

    try:
        await _lock(user_id, waifu_id, listing_id)
    except Exception as e:
        # Rollback listing
        LOGGER.error(f"[sell] lock failed, rolling back listing {listing_id}: {e}")
        await marketplace_col.delete_one({'listing_id': listing_id})
        await query.answer("Failed to lock waifu.", show_alert=True)
        return

    tax = int(round(price * MARKET_TAX_RATE))
    txt = (
        f"✅ <b>Listing created</b>\n\n"
        f"🆔 <code>{listing_id}</code>\n"
        f"🌸 {_esc(snap['name'])}\n"
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
# EXECUTE BUY (after confirmation) — atomic + rollback
# ══════════════════════════════════════════════════════════════
async def _exec_buy(query, buyer_id: int, params: dict):
    lid = str(params.get('listing_id', ''))
    if not lid:
        await query.answer("Invalid params.", show_alert=True)
        return

    now = _now()

    # ── Step 1: Atomic claim ACTIVE → PROCESSING ─────────────
    claim = await marketplace_col.find_one_and_update(
        {'listing_id': lid, 'status': 'ACTIVE'},
        {'$set': {
            'status': 'PROCESSING',
            'buyer_id': buyer_id,
            'processing_at': now,
        }},
        return_document=True,
    )
    if not claim:
        await query.answer("❌ Listing no longer available.", show_alert=True)
        return

    listing = claim
    price = int(listing['price'])
    tax = int(round(price * float(listing.get('tax_rate', MARKET_TAX_RATE))))
    gets = price - tax
    seller_id = listing['seller_id']
    waifu_id = str(listing['waifu_id'])

    async def rollback(reason: str):
        """Revert listing to ACTIVE (we didn't touch coins/waifu yet)."""
        await marketplace_col.update_one(
            {'listing_id': lid, 'status': 'PROCESSING'},
            {'$set': {'status': 'ACTIVE', 'buyer_id': None, 'processing_at': None}},
        )
        LOGGER.error(f"[buy] rollback {lid}: {reason}")
        await query.answer(f"❌ {reason}", show_alert=True)

    # ── Step 2: Validate balance ─────────────────────────────
    bal = await get_balance(buyer_id)
    if bal < price:
        await rollback("Balance changed")
        return

    # ── Step 3: Atomic coin deduction ────────────────────────
    d = await coins_collection.update_one(
        {'user_id': buyer_id, 'coins': {'$gte': price}},
        {'$inc': {'coins': -price}},
    )
    if d.modified_count == 0:
        await rollback("Balance changed")
        return

    # Coins deducted — from here on, rollback must refund buyer
    async def rollback_with_refund(reason: str):
        await coins_collection.update_one(
            {'user_id': buyer_id},
            {'$inc': {'coins': price}},
        )
        await marketplace_col.update_one(
            {'listing_id': lid, 'status': 'PROCESSING'},
            {'$set': {'status': 'ACTIVE', 'buyer_id': None, 'processing_at': None}},
        )
        LOGGER.error(f"[buy] refunded+rollback {lid}: {reason}")
        await query.answer(f"❌ {reason}", show_alert=True)

    # ── Step 4: Verify seller + find waifu ───────────────────
    seller = await user_collection.find_one({'id': seller_id})
    if not seller:
        await rollback_with_refund("Seller gone")
        return

    seller_chars = list(seller.get('characters', []))
    idx = next(
        (i for i, c in enumerate(seller_chars) if str(c.get('id', '')).strip() == waifu_id),
        None,
    )
    if idx is None:
        await rollback_with_refund("Seller no longer owns waifu")
        return

    removed_char = seller_chars.pop(idx)

    # ── Step 5: Update seller collection ─────────────────────
    s = await user_collection.update_one(
        {'id': seller_id}, {'$set': {'characters': seller_chars}}
    )
    if s.modified_count == 0:
        await rollback_with_refund("Seller update failed")
        return

    # ── Step 6: Add to buyer collection ──────────────────────
    snap = listing.get('waifu_snapshot') or _snap({
        'id': waifu_id,
        'name': listing.get('waifu_name'),
        'rarity': listing.get('waifu_rarity'),
        'anime': listing.get('waifu_anime'),
        'img_url': listing.get('waifu_img_url'),
    })

    async def rollback_full(reason: str):
        """Full rollback: refund buyer + restore seller + revert listing."""
        try:
            await user_collection.update_one(
                {'id': seller_id},
                {'$push': {'characters': removed_char}},
            )
        except Exception as e:
            LOGGER.error(f"[buy] seller restore failed {lid}: {e}")
        try:
            await coins_collection.update_one(
                {'user_id': buyer_id},
                {'$inc': {'coins': price}},
            )
        except Exception as e:
            LOGGER.error(f"[buy] buyer refund failed {lid}: {e}")
        try:
            await marketplace_col.update_one(
                {'listing_id': lid, 'status': 'PROCESSING'},
                {'$set': {'status': 'ACTIVE', 'buyer_id': None, 'processing_at': None}},
            )
        except Exception:
            pass
        LOGGER.error(f"[buy] full rollback {lid}: {reason}")
        await query.answer(f"❌ {reason}", show_alert=True)

    buyer_doc = await user_collection.find_one({'id': buyer_id})
    try:
        if buyer_doc:
            await user_collection.update_one(
                {'id': buyer_id}, {'$push': {'characters': snap}}
            )
        else:
            await user_collection.insert_one({
                'id': buyer_id,
                'username': getattr(query.from_user, 'username', None),
                'first_name': getattr(query.from_user, 'first_name', None),
                'characters': [snap],
            })
    except Exception as e:
        LOGGER.error(f"[buy] buyer add failed: {e}")
        await rollback_full("Buyer update failed")
        return

    # ── Step 7: Credit seller + tax ──────────────────────────
    try:
        await coins_collection.update_one(
            {'user_id': seller_id},
            {'$inc': {'coins': gets}},
            upsert=True,
        )
        await market_stats_col.update_one(
            {'_id': 'marketplace'},
            {'$inc': {'tax_pot': tax}},
            upsert=True,
        )
    except Exception as e:
        LOGGER.error(f"[buy] seller credit failed: {e}")
        await rollback_full("Payment failed")
        return

    # ── Step 8: Finalize listing ─────────────────────────────
    txn_id = "TXN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=9))
    try:
        await marketplace_col.update_one(
            {'listing_id': lid},
            {'$set': {
                'status': 'SOLD',
                'sold_at': _now(),
                'updated_at': _now(),
                'buyer_id': buyer_id,
                'tax_paid': tax,
                'seller_received': gets,
                'transaction_id': txn_id,
            }},
        )
        await _unlock(seller_id, waifu_id, lid)
        await market_txn_col.insert_one({
            'transaction_id': txn_id,
            'listing_id': lid,
            'buyer_id': buyer_id,
            'seller_id': seller_id,
            'waifu_id': waifu_id,
            'waifu_name': listing.get('waifu_name'),
            'amount': price,
            'tax': tax,
            'seller_received': gets,
            'timestamp': _now(),
            'status': 'COMPLETED',
        })
    except Exception as e:
        LOGGER.error(f"[buy] finalization error: {e}")
        # Transaction already partially recorded; log for admin
        await market_txn_col.insert_one({
            'transaction_id': txn_id,
            'listing_id': lid,
            'buyer_id': buyer_id,
            'seller_id': seller_id,
            'waifu_id': waifu_id,
            'amount': price,
            'tax': tax,
            'seller_received': gets,
            'timestamp': _now(),
            'status': 'PARTIAL_FAILURE',
            'error': str(e),
        })

    LOGGER.info(f"[buy] SUCCESS {lid} txn={txn_id} buyer={buyer_id} seller={seller_id}")

    # Success message
    try:
        await query.edit_message_text(
            f"✅ <b>Purchase complete</b>\n\n"
            f"🌸 {_esc(listing.get('waifu_name', ''))}\n"
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
    try:
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
            {'listing_id': lid, 'status': 'ACTIVE'},
            {'$set': {'status': 'CANCELLED', 'updated_at': _now()}},
        )
        await _unlock(user.id, listing['waifu_id'], lid)
        await _send(update, f"✅ Listing <code>{lid}</code> cancelled.")
    except Exception as e:
        LOGGER.exception(f"[cancelsell] error: {e}")


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
        h.append(rich_table(headers, rows, border=1))

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
    try:
        await _render_my(update, update.effective_user.id, 1)
    except Exception as e:
        LOGGER.exception(f"[mylistings] error: {e}")


# ══════════════════════════════════════════════════════════════
# /marketstats (sudo only)
# ══════════════════════════════════════════════════════════════
async def marketstats(update: Update, context: CallbackContext):
    try:
        if not _is_sudo(update.effective_user.id):
            await _send(update, "❌ Sudo only.")
            return

        active = await marketplace_col.count_documents({'status': 'ACTIVE'})
        sold = await marketplace_col.count_documents({'status': 'SOLD'})
        cancelled = await marketplace_col.count_documents({'status': 'CANCELLED'})
        processing = await marketplace_col.count_documents({'status': 'PROCESSING'})
        failed = await marketplace_col.count_documents({'status': 'FAILED'})
        txns = await market_txn_col.count_documents({'status': 'COMPLETED'})
        pot_doc = await market_stats_col.find_one({'_id': 'marketplace'})
        pot = int(pot_doc.get('tax_pot', 0)) if pot_doc else 0

        headers = ["Metric", "Value"]
        rows = [
            ["🟢 Active", f"<b>{active}</b>"],
            ["✅ Sold", f"<b>{sold}</b>"],
            ["❌ Cancelled", f"<b>{cancelled}</b>"],
            ["⏳ Processing", f"<b>{processing}</b>"],
            ["⚠️ Failed", f"<b>{failed}</b>"],
            ["📜 Txns", f"<b>{txns}</b>"],
            ["💰 Tax pot", f"<b>{_fmt(pot)}</b>"],
        ]
        body = rich_heading("🏦 MARKETPLACE STATS", 2) + rich_table(headers, rows, border=1)
        await _send(update, body)
    except Exception as e:
        LOGGER.exception(f"[marketstats] error: {e}")


# ══════════════════════════════════════════════════════════════
# CALLBACK DISPATCHER (secure, always answers)
# ══════════════════════════════════════════════════════════════
async def market_cb(update: Update, context: CallbackContext):
    q = update.callback_query
    data = q.data or ""
    user_id = q.from_user.id if q.from_user else 0

    try:
        # ─── Pagination ───────────────────────────────────────
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
            await _render_my(None, user_id, page=page, edit_query=q)
            return

        # ─── Confirm YES ──────────────────────────────────────
        if data.startswith("mkt:yes:"):
            token = data[len("mkt:yes:"):]
            pending = await _consume_pending(token, user_id)
            if not pending:
                await q.answer("❌ Expired or already used.", show_alert=True)
                return
            action = pending.get('action')
            params = pending.get('params') or {}
            await q.answer("Processing...")
            if action == 'sell':
                await _exec_sell(q, user_id, params)
            elif action == 'buy':
                await _exec_buy(q, user_id, params)
            else:
                await q.answer("Unknown action.", show_alert=True)
            return

        # ─── Confirm NO ───────────────────────────────────────
        if data.startswith("mkt:no:"):
            token = data[len("mkt:no:"):]
            pending = await _consume_pending(token, user_id)
            if not pending:
                await q.answer("Already expired.", show_alert=True)
                return
            await q.answer("Cancelled")
            try:
                await q.edit_message_text("❌ Cancelled.")
            except Exception:
                pass
            return

        if data == "mkt:noop":
            await q.answer()
            return

        # Default — always answer
        await q.answer()
    except Exception as e:
        LOGGER.exception(f"[market_cb] error: {e}")
        try:
            await q.answer("Error occurred.", show_alert=True)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════
application.add_handler(CommandHandler(["market", "marketplace"], market, block=False))
application.add_handler(CommandHandler("sellwaifu", sellwaifu, block=False))
application.add_handler(CommandHandler(["wbuy", "buywaifu"], wbuy, block=False))
application.add_handler(CommandHandler(["cancelsell", "unsell"], cancelsell, block=False))
application.add_handler(CommandHandler("mylistings", mylistings, block=False))
application.add_handler(CommandHandler("marketstats", marketstats, block=False))
application.add_handler(CallbackQueryHandler(market_cb, pattern=r'^mkt:', block=False))


# ══════════════════════════════════════════════════════════════
# STARTUP — schedule indexes + recovery
# ══════════════════════════════════════════════════════════════
async def _startup():
    await ensure_indexes()
    await _cleanup_expired_pendings()
    await _recover_stuck_processings()


try:
    import asyncio
    _loop = asyncio.get_event_loop()
    _loop.create_task(_startup())
except Exception as _e:
    LOGGER.warning(f"[marketplace] startup schedule: {_e}")
