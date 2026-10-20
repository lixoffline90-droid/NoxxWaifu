import uuid
import secrets
from datetime import datetime, timezone

from NoxxNetwork import db, LOGGER

giveaways_col = db['giveaways']
entries_col = db['giveaway_entries']
winners_col = db['giveaway_winners']

async def ensure_giveaway_indexes():
    """Create necessary indexes for giveaway system"""
    try:
        # Ek user ek giveaway me ek hi baar enter kar sakta hai
        await entries_col.create_index([('giveaway_id', 1), ('user_id', 1)], unique=True)
        await giveaways_col.create_index([('giveaway_id', 1)], unique=True)
        LOGGER.info("[giveaway] Indexes ensured")
    except Exception as e:
        LOGGER.error(f"[giveaway] Index error: {e}")

async def create_giveaway(
    title, prize_pool, winner_count, allocations, duration_hours, created_by, chat_id, image_url=None
):
    """Naya giveaway create karta hai"""
    giveaway_id = "GW" + uuid.uuid4().hex[:8].upper()
    now = datetime.now(timezone.utc)
    ends_at = now.timestamp() + (duration_hours * 3600)

    doc = {
        'giveaway_id': giveaway_id,
        'title': title,
        'prize_pool': prize_pool,
        'winner_count': winner_count,
        'prize_allocations': allocations, # list of dicts: {'position': 1, 'amount': 50000}
        'created_by': created_by,
        'chat_id': chat_id,
        'message_id': None,
        'created_at': now,
        'ends_at': ends_at,
        'status': 'active',
        'image_url': image_url,
        'participant_count': 0,
        'winner_ids': [],
        'draw_version': 0
    }
    await giveaways_col.insert_one(doc)
    return doc

async def get_giveaway(giveaway_id):
    return await giveaways_col.find_one({'giveaway_id': giveaway_id})

async def get_active_giveaway():
    return await giveaways_col.find_one({'status': 'active'})

async def join_giveaway(giveaway_id, user_id, username, first_name):
    """User ko giveaway me enter karta hai (Unique index prevents duplicates)"""
    now = datetime.now(timezone.utc)
    
    # 1. Check if giveaway is active and not expired
    gw = await get_giveaway(giveaway_id)
    if not gw or gw['status'] != 'active':
        return False, "❌ This giveaway is not active."
    if now.timestamp() > gw['ends_at']:
        return False, "❌ This giveaway has ended."

    # 2. Insert entry
    entry = {
        'giveaway_id': giveaway_id,
        'user_id': user_id,
        'username': username,
        'first_name': first_name,
        'joined_at': now
    }
    
    try:
        await entries_col.insert_one(entry)
        # Count badhao
        await giveaways_col.update_one(
            {'giveaway_id': giveaway_id},
            {'$inc': {'participant_count': 1}}
        )
        new_count = gw['participant_count'] + 1
        return True, new_count
    except Exception as e:
        # DuplicateKeyError
        if "E11000 duplicate key error" in str(e):
            return False, "⚠️ You have already joined this giveaway."
        LOGGER.error(f"[giveaway] Join error: {e}")
        return False, "❌ An error occurred while joining."

async def draw_winners(giveaway_id):
    """Randomly pick winners"""
    gw = await get_giveaway(giveaway_id)
    if not gw:
        return False, "Giveaway not found"

    # Get all valid entries
    entries = await entries_col.find({'giveaway_id': giveaway_id}).to_list(length=None)
    if not entries:
        return False, "No participants found."

    winner_count = min(gw['winner_count'], len(entries))
    if winner_count == 0:
        return False, "Not enough participants."

    # Secure random selection
    rng = secrets.SystemRandom()
    selected_entries = rng.sample(entries, k=winner_count)

    # Prepare winner docs
    winners = []
    now = datetime.now(timezone.utc)
    
    for idx, entry in enumerate(selected_entries):
        pos = idx + 1
        # Find allocation for this position
        allocation = next((a for a in gw['prize_allocations'] if a['position'] == pos), {'amount': 0})
        
        winner_doc = {
            'giveaway_id': giveaway_id,
            'user_id': entry['user_id'],
            'first_name': entry['first_name'],
            'username': entry['username'],
            'position': pos,
            'prize_amount': allocation['amount'],
            'draw_version': gw['draw_version'] + 1,
            'drawn_at': now,
            'payment_status': 'pending' # Important: Pending until manual payment
        }
        winners.append(winner_doc)

    # Save winners
    await winners_col.insert_many(winners)

    # Update giveaway status
    await giveaways_col.update_one(
        {'giveaway_id': giveaway_id},
        {
            '$set': {'status': 'drawn', 'drawn_at': now},
            '$inc': {'draw_version': 1}
        }
    )

    return True, winners

async def mark_paid(giveaway_id, user_id, paid_by):
    """Manual payment mark"""
    now = datetime.now(timezone.utc)
    result = await winners_col.update_one(
        {'giveaway_id': giveaway_id, 'user_id': user_id, 'payment_status': 'pending'},
        {'$set': {'payment_status': 'paid', 'paid_by': paid_by, 'paid_at': now}}
    )
    return result.modified_count > 0
