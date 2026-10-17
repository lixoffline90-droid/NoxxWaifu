"""Rich UI admin panel for NoxxWaifu.

Uses NoxxNetwork.rich_ui_decoded for rich tables/cards and Pyrogram's rich
message support, with a Telegram HTML fallback provided by rich_ui itself.
"""
from html import escape

from telegram import Update
from telegram.ext import CommandHandler, CallbackQueryHandler, CallbackContext
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from NoxxNetwork import (
    application, Waifuu, OWNER_ID, sudo_users, SUPPORT_CHAT, LOGGER,
    user_collection, user_totals_collection, group_user_totals_collection,
    top_global_groups_collection, pm_users, banned_users, banned_groups,
    collection, user_coins, marketplace_listings, redeem_codes,
)
from NoxxNetwork.rich_ui_decoded import (
    rich_send, rich_edit, rich_esc, rich_heading, rich_table, rich_note,
)

PREFIX = "noxxap:"


def _is_owner(uid: int) -> bool:
    return int(uid) == int(OWNER_ID)


def _is_sudo(uid: int) -> bool:
    if _is_owner(uid):
        return True
    try:
        return int(uid) in {int(x) for x in (sudo_users or [])}
    except (TypeError, ValueError):
        return str(uid) in {str(x) for x in (sudo_users or [])}


def _btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


def _home_markup(uid):
    rows = [
        [_btn("📊 Dashboard", PREFIX + "dashboard"), _btn("📚 All Commands", PREFIX + "commands")],
        [_btn("🎴 Character", PREFIX + "cat:character"), _btn("🛡 Moderation", PREFIX + "cat:moderation")],
        [_btn("💰 Economy", PREFIX + "cat:economy"), _btn("🎯 Spawn & Rarity", PREFIX + "cat:spawn")],
        [_btn("✅ Approval", PREFIX + "cat:approval"), _btn("🏪 Marketplace", PREFIX + "cat:market")],
        [_btn("🗄 Database", PREFIX + "database"), _btn("🚫 Banned", PREFIX + "banned")],
        [_btn("📡 Broadcast Info", PREFIX + "broadcast")],
    ]
    if _is_owner(uid):
        rows.append([_btn("👑 Owner Tools", PREFIX + "cat:owner")])
    rows.append([_btn("🔄 Refresh", PREFIX + "dashboard"), _btn("✖ Close", PREFIX + "close")])
    if SUPPORT_CHAT:
        support = str(SUPPORT_CHAT).strip()
        if support.startswith("https://t.me/"):
            rows.insert(-1, [InlineKeyboardButton("🌐 Support", url=support)])
        elif support.startswith("@"):
            rows.insert(-1, [InlineKeyboardButton("🌐 Support", url="https://t.me/" + support[1:])])
    return InlineKeyboardMarkup(rows)


def _back_markup(uid):
    return InlineKeyboardMarkup([
        [_btn("◀ Admin Home", PREFIX + "home"), _btn("📚 All Commands", PREFIX + "commands")],
        [_btn("✖ Close", PREFIX + "close")],
    ])

# Aliases below are taken from the CommandHandler registrations in this repo.
# Alias spellings are grouped on one row; access descriptions are based on the
# module's own checks and should be treated as a quick reference, not security.
COMMANDS = {
    "character": ("🎴 CHARACTER MANAGEMENT", "Sudo / approved uploader where module allows", [
        ("/upload", "Add a character", "Alias: none"),
        ("/update", "Update character details", "Alias: none"),
        ("/delete", "Delete a character", "Alias: none"),
        ("/resync", "Resync character channel", "Alias: none"),
        ("/setrarity", "Set rarity probability", "Alias: /setrarityprob"),
        ("/rarities", "Show rarity probabilities", "Alias: none"),
        ("/charkill", "Remove a character from a harem", "Alias: none"),
        ("/create_code", "Create a redeem code", "Alias: /createcode"),
        ("/codes", "List redeem codes", "Alias: /codelist"),
        ("/delcode", "Delete a redeem code", "Alias: none"),
        ("/redeem", "Redeem a character code", "Alias: none; user command"),
    ]),
    "moderation": ("🛡 MODERATION", "Owner/Sudo (verify each module's guard)", [
        ("/banuser", "Ban a user", "Alias: none"),
        ("/unbanuser", "Unban a user", "Alias: none"),
        ("/bangroup", "Ban a group", "Alias: none"),
        ("/unbangroup", "Unban a group", "Alias: none"),
        ("/bannedlist", "List banned users/groups", "Alias: none"),
    ]),
    "economy": ("💰 COINS & ECONOMY", "Mixed access; see each command's module", [
        ("/wadd", "Add coins", "Alias: /addcoins"),
        ("/wremove", "Remove coins", "Alias: /removecoins"),
        ("/wpocket", "View coin pocket/balance", "Aliases: /pocket, /balance"),
        ("/wsend", "Send coins", "Aliases: /sendcoins, /pay"),
        ("/ball", "Roll the ball game", "Alias: none"),
        ("/wtop", "Coin leaderboard", "Alias: /cointop"),
    ]),
    "spawn": ("🎯 SPAWN & RARITY", "Owner/Sudo or module-specific access", [
        ("/spawn", "Configure spawn", "Alias: none"),
        ("/changetime", "Change spawn interval", "Alias: /setchangetime"),
        ("/setrarity", "Set rarity probability", "Alias: /setrarityprob"),
        ("/rarities", "View rarity probability", "Alias: none"),
    ]),
    "approval": ("✅ UPLOADER APPROVAL", "Restricted; check module guards", [
        ("/wallow", "Approve an uploader", "Alias: none"),
        ("/wdeny", "Revoke uploader approval", "Alias: none"),
        ("/approvedlist", "List approved uploaders", "Alias: none"),
    ]),
    "market": ("🏪 MARKETPLACE & TRANSFER", "Mixed access; see module guards", [
        ("/market", "Open marketplace", "Alias: /marketplace"),
        ("/sellwaifu", "List a character for sale", "Alias: none"),
        ("/wbuy", "Buy a listing", "Alias: /buywaifu"),
        ("/cancelsell", "Cancel a listing", "Alias: /unsell"),
        ("/mylistings", "View own listings", "Alias: none"),
        ("/marketstats", "Marketplace statistics", "Alias: none"),
        ("/TransferHarem", "Transfer a full harem", "Aliases: /transferharem, /tharem"),
        ("/trade", "Trade characters", "Alias: none"),
        ("/gift", "Gift a character", "Alias: none"),
    ]),
    "owner": ("👑 OWNER / DEVELOPER TOOLS", "Owner-only where enforced by module", [
        ("/broadcast", "Broadcast a replied-to message", "Alias: none"),
        ("/stats", "Bot statistics", "Alias: none"),
        ("/e", "Evaluate Python", "Aliases: /ev, /eva, /eval"),
        ("/x", "Execute Python", "Aliases: /ex, /exe, /exec, /py"),
        ("/clearlocals", "Clear eval namespace", "Alias: none"),
        ("/list", "Export users list", "Alias: none"),
        ("/groups", "Export groups list", "Alias: none"),
        ("/TopGroups", "Global group leaderboard", "Case-insensitive command"),
        ("/ping", "Check bot latency", "Alias: none"),
    ]),
}

async def _counts():
    async def count(col):
        try:
            return await col.count_documents({})
        except Exception:
            return 0
    try:
        groups = len(await top_global_groups_collection.distinct("group_id"))
    except Exception:
        groups = 0
    return {
        "users": await count(user_collection),
        "private": await count(pm_users),
        "groups": groups,
        "banned_users": await count(banned_users),
        "banned_groups": await count(banned_groups),
        "characters": await count(collection),
        "coin_accounts": await count(user_coins),
        "listings": await count(marketplace_listings),
        "codes": await count(redeem_codes),
        "user_totals": await count(user_totals_collection),
        "group_totals": await count(group_user_totals_collection),
    }


def _table_for_commands(items):
    rows = []
    for command, description, aliases in items:
        rows.append([f"<code>{rich_esc(command)}</code>", rich_esc(description), rich_esc(aliases)])
    return rich_table(["Command", "Purpose", "Aliases"], rows, border=1)

async def _page(page, uid):
    role = "OWNER 👑" if _is_owner(uid) else "SUDO 🛡"
    if page in ("home", "dashboard"):
        c = await _counts()
        body = rich_heading("NOXXWAIFU • ADMIN DASHBOARD", 1)
        body += f"\n<b>Role:</b> {role}  |  <b>ID:</b> <code>{uid}</code>\n"
        body += rich_table(["Metric", "Count"], [
            ["Registered users", str(c["users"])], ["Private chats", str(c["private"])],
            ["Groups", str(c["groups"])], ["Banned users", str(c["banned_users"])],
            ["Banned groups", str(c["banned_groups"])], ["Characters", str(c["characters"])],
            ["Coin accounts", str(c["coin_accounts"])], ["Marketplace listings", str(c["listings"])],
            ["Redeem codes", str(c["codes"])],
        ], border=1)
        body += "\n" + rich_note("Choose a section below. Command tables include registered aliases where available.")
        return body
    if page == "commands":
        chunks = [rich_heading("COMMAND DIRECTORY & ALIASES", 1)]
        for key, (title, access, items) in COMMANDS.items():
            if key == "owner" and not _is_owner(uid):
                continue
            chunks.append(rich_heading(title, 3))
            chunks.append(f"<i>{rich_esc(access)}</i>\n")
            chunks.append(_table_for_commands(items))
        return "\n".join(chunks)
    if page.startswith("cat:"):
        key = page.split(":", 1)[1]
        cat = COMMANDS.get(key)
        if not cat:
            return rich_note("Category not found.")
        if key == "owner" and not _is_owner(uid):
            return rich_heading("OWNER ONLY", 2) + rich_note("This section is visible to the bot owner only.")
        title, access, items = cat
        return rich_heading(title, 1) + f"\n<i>{rich_esc(access)}</i>\n" + _table_for_commands(items) + "\n" + rich_note(f"{len(items)} command entries. Aliases are shown in the third column.")
    if page == "database":
        c = await _counts()
        return rich_heading("DATABASE OVERVIEW", 1) + rich_table(["Collection", "Documents"], [
            ["Characters", str(c["characters"])], ["Users", str(c["users"])],
            ["User totals", str(c["user_totals"])], ["Group totals", str(c["group_totals"])],
            ["Coin accounts", str(c["coin_accounts"])], ["Marketplace listings", str(c["listings"])],
            ["Redeem codes", str(c["codes"])], ["Banned users", str(c["banned_users"])],
            ["Banned groups", str(c["banned_groups"])],
        ], border=1) + "\n" + rich_note("Read-only view; no database records were changed.")
    if page == "banned":
        c = await _counts()
        try:
            users = await banned_users.find({}).limit(15).to_list(length=15)
        except Exception:
            users = []
        try:
            groups = await banned_groups.find({}).limit(15).to_list(length=15)
        except Exception:
            groups = []
        rows = [["User", rich_esc(x.get("user_id", x.get("_id", "?")))] for x in users]
        rows += [["Group", rich_esc(x.get("chat_id", x.get("group_id", x.get("_id", "?"))))] for x in groups]
        if not rows:
            rows = [["—", "No banned records found"]]
        return rich_heading("BANNED USERS & GROUPS", 1) + f"\nUsers: <b>{c['banned_users']}</b> | Groups: <b>{c['banned_groups']}</b>\n" + rich_table(["Type", "ID"], rows, border=1)
    if page == "broadcast":
        if not _is_owner(uid):
            return rich_heading("OWNER ONLY", 2) + rich_note("Broadcast is restricted to the owner.")
        c = await _counts()
        return rich_heading("BROADCAST", 1) + rich_table(["Step", "Action"], [
            ["1", "Send the message you want to broadcast"],
            ["2", "Reply to that message with /broadcast"],
            ["3", f"Known targets: {c['private']} private chats + {c['groups']} groups"],
        ]) + "\n" + rich_note("Broadcast sends messages to many chats. Use responsibly.")
    return rich_note("Unknown panel section.")

async def adminpanel(update: Update, context: CallbackContext):
    user = update.effective_user
    msg = update.effective_message
    if not user or not _is_sudo(user.id):
        if msg:
            await msg.reply_text("⛔ This panel is available to the bot owner and sudo users only.")
        return
    if Waifuu is None:
        await msg.reply_text("Rich UI client is unavailable. Check NoxxNetwork.Waifuu startup.")
        return
    try:
        await rich_send(Waifuu, update.effective_chat.id, await _page("home", user.id), reply_markup=_home_markup(user.id), reply_to_message_id=msg.message_id)
    except Exception as exc:
        LOGGER.exception("Admin panel send failed: %s", exc)
        await msg.reply_text("Admin panel failed to load. Check the logs.")

async def adminpanel_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    if not _is_sudo(user.id):
        await query.answer("Not authorized", show_alert=True)
        return
    data = query.data or ""
    if not data.startswith(PREFIX):
        return
    action = data[len(PREFIX):]
    await query.answer()
    if action == "close":
        try:
            await query.delete_message()
        except Exception:
            try:
                await query.edit_message_text("Admin panel closed.")
            except Exception:
                pass
        return
    try:
        text = await _page(action, user.id)
        markup = _home_markup(user.id) if action in ("home", "dashboard") else _back_markup(user.id)
        await rich_edit(query, text, reply_markup=markup, client=Waifuu)
    except Exception as exc:
        LOGGER.exception("Admin panel callback failed: %s", exc)
        try:
            await query.edit_message_text("Could not load this section. Check the logs.")
        except Exception:
            pass

application.add_handler(CommandHandler(["adminpanel", "adminhelp", "commands"], adminpanel, block=False))
application.add_handler(CallbackQueryHandler(adminpanel_callback, pattern=r"^noxxap:", block=False))
