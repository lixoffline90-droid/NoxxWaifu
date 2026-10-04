from telegram import Update
from telegram.ext import CommandHandler, CallbackContext

from NoxxNetwork import application, db, sudo_users, OWNER_ID
from NoxxNetwork.rarity import RARITIES

rarity_config_col = db['rarity_spawn_config']

DEFAULT_CONFIG = {
    'enabled': True,
    'frequency': 0,
    'scope': 'global',
}


def _is_sudo(user_id: int) -> bool:
    return str(user_id) in sudo_users or user_id == OWNER_ID


async def get_all_rarity_configs() -> dict:
    """Return {rarity_id: {enabled, frequency, scope}} for all rarities."""
    result = {}
    async for doc in rarity_config_col.find({}):
        try:
            rid = int(doc['rarity_id'])
        except (KeyError, ValueError, TypeError):
            continue
        result[rid] = {
            'enabled': bool(doc.get('enabled', True)),
            'frequency': int(doc.get('frequency', 0)),
            'scope': str(doc.get('scope', 'global')),
        }
    for rid in RARITIES:
        if rid not in result:
            result[rid] = dict(DEFAULT_CONFIG)
    return result


async def get_rarity_config(rarity_id: int) -> dict:
    doc = await rarity_config_col.find_one({'rarity_id': rarity_id})
    if not doc:
        return dict(DEFAULT_CONFIG)
    return {
        'enabled': bool(doc.get('enabled', True)),
        'frequency': int(doc.get('frequency', 0)),
        'scope': str(doc.get('scope', 'global')),
    }


async def set_rarity_config(rarity_id: int, enabled=None, frequency=None, scope=None):
    updates = {}
    if enabled is not None:
        updates['enabled'] = bool(enabled)
    if frequency is not None:
        updates['frequency'] = int(frequency)
    if scope is not None:
        updates['scope'] = str(scope)
    if not updates:
        return
    await rarity_config_col.update_one(
        {'rarity_id': rarity_id},
        {'$set': updates},
        upsert=True,
    )


# ---------------------------------------------------------------------------
# /spawn
# ---------------------------------------------------------------------------
async def spawn_cmd(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if not _is_sudo(user_id):
        await update.message.reply_text("⚠️ Only Sudo Users can use this command.")
        return

    args = context.args or []

    # No args → show all
    if not args:
        await _show_all(update)
        return

    first = args[0].lower()

    # /spawn list
    if first in ('list', 'all', 'show'):
        await _show_all(update)
        return

    # /spawn on  /  /spawn off → toggle all
    if first in ('on', 'off') and len(args) == 1:
        enable = (first == 'on')
        for rid in RARITIES:
            await set_rarity_config(rid, enabled=enable)
        status = "ENABLED ✅" if enable else "DISABLED 🚫"
        await update.message.reply_text(f"All rarities {status}")
        return

    # Parse rarity_id
    try:
        rarity_id = int(first)
    except ValueError:
        await update.message.reply_text(
            "Usᴀɢᴇ:\n"
            "<code>/spawn &lt;rarity_id&gt; &lt;frequency&gt; &lt;Main/global&gt;</code>\n"
            "<code>/spawn &lt;rarity_id&gt; on|off</code>\n"
            "<code>/spawn list</code>",
            parse_mode='HTML',
        )
        return

    if rarity_id not in RARITIES:
        await update.message.reply_text(f"❌ Invalid rarity ID. Use 1-{max(RARITIES)}.")
        return

    # /spawn <id> → show one
    if len(args) == 1:
        await _show_one(update, rarity_id)
        return

    second = args[1].lower()

    # /spawn <id> off
    if second == 'off':
        await set_rarity_config(rarity_id, enabled=False)
        emoji, name = RARITIES[rarity_id]
        await update.message.reply_text(f"🚫 {emoji} {name} has been DISABLED.")
        return

    # /spawn <id> on
    if second == 'on':
        await set_rarity_config(rarity_id, enabled=True)
        emoji, name = RARITIES[rarity_id]
        await update.message.reply_text(f"✅ {emoji} {name} has been ENABLED.")
        return

    # /spawn <id> <frequency> [scope]
    try:
        frequency = int(second)
        if frequency < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Frequency must be a positive number (0 = no limit).")
        return

    scope = 'global'
    if len(args) >= 3:
        scope_arg = args[2].lower()
        if scope_arg in ('main', 'mainchat', 'main_chat'):
            scope = 'main'
        elif scope_arg in ('global', 'all', 'everywhere'):
            scope = 'global'
        else:
            await update.message.reply_text("❌ Scope must be 'Main' or 'global'.")
            return

    await set_rarity_config(rarity_id, enabled=True, frequency=frequency, scope=scope)

    emoji, name = RARITIES[rarity_id]
    scope_text = "🏠 Main GC only" if scope == 'main' else "🌐 Global (all chats)"
    freq_text = f"every {frequency} messages" if frequency > 0 else "no limit"

    await update.message.reply_text(
        f"✅ <b>Spawn Config Updated</b>\n\n"
        f"🎴 Rarity: {emoji} {name} (ID: {rarity_id})\n"
        f"📊 Frequency: {freq_text}\n"
        f"🌐 Scope: {scope_text}\n"
        f"✅ Status: ENABLED",
        parse_mode='HTML',
    )


async def _show_one(update, rarity_id):
    cfg = await get_rarity_config(rarity_id)
    emoji, name = RARITIES[rarity_id]
    status = "✅ ENABLED" if cfg['enabled'] else "🚫 DISABLED"
    scope_text = "🏠 Main GC only" if cfg['scope'] == 'main' else "🌐 Global (all chats)"
    freq_text = f"every {cfg['frequency']} messages" if cfg['frequency'] > 0 else "no limit"

    await update.message.reply_text(
        f"🎴 <b>Rarity {rarity_id}: {emoji} {name}</b>\n\n"
        f"Status: {status}\n"
        f"Frequency: {freq_text}\n"
        f"Scope: {scope_text}",
        parse_mode='HTML',
    )


async def _show_all(update):
    configs = await get_all_rarity_configs()
    lines = ["🎴 <b>Rarity Spawn Config</b>", ""]
    for rid in sorted(RARITIES.keys()):
        emoji, name = RARITIES[rid]
        cfg = configs.get(rid, DEFAULT_CONFIG)
        status_icon = "✅" if cfg['enabled'] else "🚫"
        scope_icon = "🌐" if cfg['scope'] == 'global' else "🏠"
        freq = cfg['frequency']
        freq_text = f"~{freq}msg" if freq > 0 else "∞"
        lines.append(f"{status_icon} <code>{rid:>2}</code>. {emoji} {name} — {freq_text} {scope_icon}")

    lines.append("")
    lines.append("Usᴀɢᴇ: <code>/spawn &lt;id&gt; &lt;frequency&gt; &lt;Main/global&gt;</code>")
    lines.append("Exᴀᴍᴘʟᴇ: <code>/spawn 21 2500 Main</code>")
    lines.append("Oɴ/Oғғ: <code>/spawn &lt;id&gt; on|off</code>")

    await update.message.reply_text("\n".join(lines), parse_mode='HTML')


application.add_handler(CommandHandler("spawn", spawn_cmd, block=False))