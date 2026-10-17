"""Elara-style interactive admin dashboard for NoxxWaifu."""
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler
from NoxxNetwork import (
    application, sudo_users, OWNER_ID, SUPPORT_CHAT, LOGGER,
    user_collection, user_totals_collection, group_user_totals_collection,
    top_global_groups_collection, pm_users, banned_users, banned_groups,
    collection, user_coins, marketplace_listings, redeem_codes,
)


def _is_sudo(user_id: int) -> bool:
    return user_id == OWNER_ID or str(user_id) in (sudo_users or [])


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def _home_kb(user_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📊 Dashboard", callback_data="apanel:dashboard"), InlineKeyboardButton("👥 Users", callback_data="apanel:users")],
        [InlineKeyboardButton("🚫 Banned Users", callback_data="apanel:banned"), InlineKeyboardButton("📢 Broadcast", callback_data="apanel:broadcast")],
        [InlineKeyboardButton("📡 Broadcast Stats", callback_data="apanel:broadcaststats"), InlineKeyboardButton("🗄 Database", callback_data="apanel:database")],
        [InlineKeyboardButton("🎴 Character Tools", callback_data="apanel:cat:char"), InlineKeyboardButton("🛡️ Moderation", callback_data="apanel:cat:ban")],
        [InlineKeyboardButton("💰 Economy", callback_data="apanel:cat:coins"), InlineKeyboardButton("⚙️ More Commands", callback_data="apanel:categories")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="apanel:home"), InlineKeyboardButton("❌ Close", callback_data="apanel:close")],
    ]
    if SUPPORT_CHAT:
        rows.insert(-1, [InlineKeyboardButton("🌐 Support", url=f"https://t.me/{SUPPORT_CHAT.lstrip('@')}")])
    return InlineKeyboardMarkup(rows)


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀ Back to Admin Panel", callback_data="apanel:home")]])


def _categories_kb(user_id: int) -> InlineKeyboardMarkup:
    keys = [("char", "🎴 Character"), ("spawn", "🎯 Spawn"), ("ban", "🚫 Ban"), ("coins", "💰 Coins"),
            ("market", "🏪 Market"), ("redeem", "🎁 Redeem"), ("approval", "✅ Approval"),
            ("gift", "🎀 Gift"), ("misc", "🛠 Utilities")]
    if _is_owner(user_id): keys.append(("owner", "👑 Owner Only"))
    rows=[]
    for i in range(0,len(keys),2):
        rows.append([InlineKeyboardButton(label, callback_data=f"apanel:cat:{key}") for key,label in keys[i:i+2]])
    rows.append([InlineKeyboardButton("◀ Back", callback_data="apanel:home")])
    return InlineKeyboardMarkup(rows)

CATEGORIES = {
    "char": ("🎴 CHARACTER MANAGEMENT", "sudo", [
        ("/upload <url> <name> <anime> <rarity>", "Add a character"), ("/update <id> <field> <value>", "Edit a character"),
        ("/delete <id>", "Delete a character"), ("/resync", "Re-upload characters to channel"),
        ("/setrarity <id> <prob>", "Change rarity probability"), ("/rarities", "Show rarity probabilities"),
        ("/charkill <id> (reply)", "Remove character from a harem")]),
    "spawn": ("🎯 SPAWN CONTROL", "sudo", [("/spawn <id> <freq> <Main/global>", "Set spawn rate"), ("/changetime <num>", "Set group spawn frequency")]),
    "ban": ("🚫 BAN SYSTEM", "sudo", [("/banuser <id> or reply", "Ban a user"), ("/unbanuser <id> or reply", "Unban a user"), ("/bangroup <group_id>", "Ban a group"), ("/unbangroup <group_id>", "Unban a group"), ("/bannedlist", "List banned users and groups")]),
    "coins": ("💰 COIN MANAGEMENT", "sudo", [("/wadd <amount> (reply)", "Add coins"), ("/wremove <amount> (reply)", "Remove coins")]),
    "market": ("🏪 MARKETPLACE", "sudo", [("/marketstats", "View marketplace stats"), ("/TransferHarem <from_id> <to_id>", "Transfer a full harem")]),
    "redeem": ("🎁 REDEEM CODES", "sudo", [("/create_code <char_id> [max_uses]", "Create a code"), ("/codes", "List codes"), ("/delcode <code>", "Delete a code")]),
    "approval": ("✅ APPROVAL SYSTEM", "sudo", [("/wallow <id> or reply", "Approve uploader"), ("/wdeny <id> or reply", "Revoke uploader access"), ("/approvedlist", "List approved uploaders")]),
    "gift": ("🎀 GIFT TOOLS", "sudo", [("/gift <id> (reply)", "Gift a character")]),
    "misc": ("🛠 UTILITIES", "sudo", [("/ping", "Check latency"), ("/list", "Export users list"), ("/groups", "Export groups list")]),
    "owner": ("👑 OWNER ONLY", "owner", [("/broadcast (reply)", "Broadcast a replied message"), ("/stats", "Bot statistics"), ("/e /ev /eval <code>", "Python evaluation"), ("/x /ex /exec <code>", "Python execution"), ("/clearlocals", "Clear eval namespace")]),
}

async def _counts():
    # Counts use the collections already maintained by this bot.
    users = await user_collection.count_documents({})
    private_users = await pm_users.count_documents({})
    groups = len(await top_global_groups_collection.distinct("group_id"))
    banned_u = await banned_users.count_documents({})
    banned_g = await banned_groups.count_documents({})
    chars = await collection.count_documents({})
    coins = await user_coins.count_documents({})
    listings = await marketplace_listings.count_documents({})
    codes = await redeem_codes.count_documents({})
    totals = await user_totals_collection.count_documents({})
    return {"users": users, "private": private_users, "groups": groups, "banned_users": banned_u,
            "banned_groups": banned_g, "characters": chars, "coin_accounts": coins,
            "listings": listings, "codes": codes, "user_totals": totals}

async def _render(page: str, user_id: int) -> str:
    role = "👑 Owner" if _is_owner(user_id) else "🛡️ Sudo"
    if page in ("home", "dashboard"):
        c = await _counts()
        return ("<b>🔐 NOXXWAIFU • ADMIN PANEL</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Role:</b> {role}\n🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                "<b>📊 Dashboard</b>\n"
                f"👥 Users: <b>{c['users']}</b>  |  💬 Private: <b>{c['private']}</b>\n"
                f"🌐 Groups: <b>{c['groups']}</b>\n"
                f"🚫 Banned users: <b>{c['banned_users']}</b>  |  Groups: <b>{c['banned_groups']}</b>\n"
                f"🎴 Characters: <b>{c['characters']}</b>\n\n"
                "Choose a section below to manage your bot.")
    if page == "users":
        c=await _counts()
        return ("<b>👥 USER OVERVIEW</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"Registered user records: <b>{c['users']}</b>\nPrivate chat records: <b>{c['private']}</b>\n"
                f"User total records: <b>{c['user_totals']}</b>\n\nUse <code>/list</code> to export the users list.")
    if page == "banned":
        c=await _counts()
        users=await banned_users.find({}).limit(15).to_list(length=15)
        groups=await banned_groups.find({}).limit(15).to_list(length=15)
        lines=["<b>🚫 BANNED USERS & GROUPS</b>","━━━━━━━━━━━━━━━━━━",f"Users: <b>{c['banned_users']}</b>",f"Groups: <b>{c['banned_groups']}</b>",""]
        if users:
            lines.append("<b>Recent banned users:</b>")
            lines.extend(f"• <code>{escape(str(x.get('user_id','?')))}</code>" for x in users)
        if groups:
            lines.append("\n<b>Recent banned groups:</b>")
            lines.extend(f"• <code>{escape(str(x.get('chat_id','?')))}</code>" for x in groups)
        if not users and not groups: lines.append("No banned users or groups found.")
        return "\n".join(lines)
    if page == "broadcast":
        if not _is_owner(user_id): return "<b>⛔ OWNER ONLY</b>\nBroadcast access is restricted to the bot owner."
        return ("<b>📢 BROADCAST</b>\n━━━━━━━━━━━━━━━━━━\n"
                "To broadcast a message, send the bot a message and reply to it with <code>/broadcast</code>.\n\n"
                "The current broadcast command forwards to known private users and groups.\n"
                "⚠️ Use responsibly; this action sends messages to many chats.")
    if page == "broadcaststats":
        c=await _counts()
        return ("<b>📡 BROADCAST TARGETS</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"Private user records: <b>{c['private']}</b>\nGroup records: <b>{c['groups']}</b>\n"
                f"Approx. unique targets: <b>{c['private'] + c['groups']}</b>\n\n"
                "This is an estimate; duplicate or unreachable chats may affect actual delivery.")
    if page == "database":
        c=await _counts()
        return ("<b>🗄 DATABASE OVERVIEW</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"🎴 Characters: <b>{c['characters']}</b>\n👥 User records: <b>{c['users']}</b>\n"
                f"💰 Coin accounts: <b>{c['coin_accounts']}</b>\n🏪 Marketplace listings: <b>{c['listings']}</b>\n"
                f"🎁 Redeem codes: <b>{c['codes']}</b>\n🚫 Banned users: <b>{c['banned_users']}</b>\n"
                f"🚫 Banned groups: <b>{c['banned_groups']}</b>\n\nRead-only overview; no database records were changed.")
    if page.startswith("cat:"):
        key=page.split(":",1)[1]
        cat=CATEGORIES.get(key)
        if not cat: return "Category not found."
        title, access, items=cat
        if access == "owner" and not _is_owner(user_id): return "<b>⛔ OWNER ONLY</b>"
        lines=[f"<b>{title}</b>","━━━━━━━━━━━━━━━━━━"]
        for cmd,desc in items: lines.append(f"<code>{escape(cmd)}</code> — {escape(desc)}")
        lines.append(f"\nTotal entries: <b>{len(items)}</b>")
        return "\n".join(lines)
    if page == "categories":
        return "<b>⚙️ COMMAND CATEGORIES</b>\nChoose a category below to view commands."
    return "Unknown panel section."

async def _safe_edit(query, text, keyboard):
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        if "message is not modified" not in str(e).lower(): LOGGER.warning("Admin panel edit failed: %s", e)

async def adminpanel(update: Update, context: CallbackContext) -> None:
    user=update.effective_user
    if not user or not _is_sudo(user.id):
        await update.effective_message.reply_text("⚠️ You are not authorized to open the admin panel.")
        return
    text=await _render("home",user.id)
    await update.effective_message.reply_text(text, reply_markup=_home_kb(user.id), parse_mode="HTML", disable_web_page_preview=True)

async def adminpanel_callback(update: Update, context: CallbackContext) -> None:
    q=update.callback_query
    await q.answer()
    uid=q.from_user.id
    if not _is_sudo(uid):
        await q.answer("You are not authorized.", show_alert=True)
        return
    data=q.data or ""
    if data == "apanel:close":
        try: await q.message.delete()
        except Exception: pass
        return
    if data in ("apanel:home", "apanel:dashboard"):
        await _safe_edit(q, await _render("home",uid), _home_kb(uid)); return
    page_map={"apanel:users":"users", "apanel:banned":"banned", "apanel:broadcast":"broadcast",
              "apanel:broadcaststats":"broadcaststats", "apanel:database":"database"}
    if data in page_map:
        page=page_map[data]
        if page == "broadcast" and not _is_owner(uid):
            await q.answer("Broadcast is owner-only.", show_alert=True); return
        await _safe_edit(q, await _render(page,uid), _back_kb()); return
    if data == "apanel:categories":
        await _safe_edit(q, await _render("categories",uid), _categories_kb(uid)); return
    if data.startswith("apanel:cat:"):
        key=data.split(":",2)[2]
        await _safe_edit(q, await _render("cat:"+key,uid), _back_kb()); return

application.add_handler(CommandHandler(["adminpanel", "adminhelp", "commands"], adminpanel, block=False))
application.add_handler(CallbackQueryHandler(adminpanel_callback, pattern=r"^apanel:", block=False))
