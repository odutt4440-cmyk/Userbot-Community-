import datetime
import asyncio
import os
import json
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot 
from config import ADMIN_ID, SUDO_USERS, LOG_GROUP
from core.session_manager import ACTIVE_CLIENTS, SessionManager

from database import (
    add_subscription, 
    ban_user, 
    unban_user, 
    is_banned,
    transfer_subscription, 
    cancel_subscription,
    get_sub_info,
    remove_user_session,
    has_claimed_trial,
    is_staff,
    get_sudo_info, 
    set_plan_status,
    is_plan_available,
    set_maintenance,
    db,
    get_ban_info,
    users_db_proxy, 
    set_module_testing,
    is_module_in_testing,
    subs_db_proxy,
    get_all_plans,
    update_plan_price,
    update_plan_days,
    toggle_plan_active,
    seed_default_plans,
)

# --- HELPER: STAFF PERMISSION CHECK ---
async def check_power(user_id, power_type):
    if user_id == ADMIN_ID: return True
    info = await get_sudo_info(user_id)
    if not info: return False
    return info[0] == 1 if power_type == 'ban' else info[1] == 1

# ============================================================
# --- STATE TRACKING (for pricing updates) ---
# ============================================================
# {user_id: {"action": "price"/"days", "plan_key": "std_15"}}
AWAITING_PLAN_INPUT = {}

# ============================================================
# --- SUDO PANEL ---
# ============================================================

SUDO_PANEL_BUTTONS = [
    ("🚫 Ban User", "panel_ban", ButtonStyle.DANGER),
    ("✅ Unban User", "panel_unban", ButtonStyle.SUCCESS),
    ("👑 Add Sudo", "panel_addsudo", ButtonStyle.SUCCESS),
    ("❌ Remove Sudo", "panel_rmsudo", ButtonStyle.DANGER),
    ("📢 Broadcast", "panel_broadcast", ButtonStyle.PRIMARY),
    ("🛠️ Maintenance", "panel_maint", ButtonStyle.DANGER),
    ("📊 Stats", "panel_stats", ButtonStyle.SUCCESS),
    ("📋 Sudolist", "panel_sudolist", ButtonStyle.PRIMARY),
    ("💳 Approve Plan", "panel_approve", ButtonStyle.SUCCESS),
    ("📉 Cancel Plan", "panel_cancel", ButtonStyle.DANGER),
    ("👤 User Info", "panel_info", ButtonStyle.PRIMARY),
    ("📡 Active Bots", "panel_active", ButtonStyle.PRIMARY),
    ("💰 Update Pricing", "panel_pricing", ButtonStyle.SUCCESS),
    ("🔄 Reset Plans", "panel_reset_plans", ButtonStyle.DANGER),
]

def build_sudo_panel():
    buttons = []
    row = []
    for label, data, style in SUDO_PANEL_BUTTONS:
        row.append(InlineKeyboardButton(label, callback_data=data, style=style))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Close Panel", callback_data="panel_close", style=ButtonStyle.DANGER)])
    return InlineKeyboardMarkup(buttons)

@bot.on_message(filters.command("admin") & filters.private)
async def sudo_panel_command(client, message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID and not await is_staff(user_id):
        return await message.reply("🚫 This command is restricted to admins and sudo users only.")
    
    await message.reply(
        "🛡️ **SUDO ADMIN PANEL**\n\n"
        "Select a command below:",
        reply_markup=build_sudo_panel()
    )

@bot.on_callback_query(filters.regex(r"^panel_"))
async def sudo_panel_callback(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID and not await is_staff(user_id):
        return await query.answer("Access denied.", show_alert=True)
    
    action = query.data.replace("panel_", "")
    
    if action == "close":
        return await query.message.delete()
    
    hints = {
        "ban": "🚫 **Ban User**\n\nSend: `/ban <user_id> <reason>`",
        "unban": "✅ **Unban User**\n\nSend: `/unban <user_id>`",
        "addsudo": "👑 **Add Sudo**\n\nSend: `/addsudo <user_id> <can_ban 0/1> <can_pay 0/1>`",
        "rmsudo": "❌ **Remove Sudo**\n\nSend: `/rmsudo <user_id>`",
        "broadcast": "📢 **Broadcast**\n\nSend: `/broadcast <message>`",
        "maint": "🛠️ **Maintenance**\n\nSend: `/maintenance on/off <message>`",
        "approve": "💳 **Approve Plan**\n\nSend: `/approve <user_id> <plan> <days> <hours> <minutes>`",
        "cancel": "📉 **Cancel Plan**\n\nSend: `/cancel <user_id>`",
        "info": "👤 **User Info**\n\nSend: `/info <user_id>`",
    }
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
    
    if action == "stats":
        u_count = await users_db_proxy.count_documents({})
        s_count = await subs_db_proxy.count_documents({})
        await query.message.edit_text(
            f"📊 **Empire Global Stats**\n\n"
            f"👤 **Total Registered:** `{u_count}`\n"
            f"💎 **Active Premium:** `{s_count}`\n"
            f"📡 **Running Bots:** `{len(ACTIVE_CLIENTS)}`",
            reply_markup=back_btn
        )
    elif action == "sudolist":
        from database import list_all_sudos
        rows = await list_all_sudos()
        if not rows:
            text = "📋 No sudo users found."
        else:
            text = "📋 **SUDO LIST**\n\n"
            for r in rows:
                text += f"• `{r[0]}` | Ban: {r[1]} | Pay: {r[2]}\n"
        await query.message.edit_text(text, reply_markup=back_btn)
    elif action == "active":
        if not ACTIVE_CLIENTS:
            text = "📡 No active userbots."
        else:
            text = "📡 **Active Sessions:**\n\n"
            for uid in list(ACTIVE_CLIENTS.keys()):
                text += f"👤 `{uid}`\n"
        await query.message.edit_text(text, reply_markup=back_btn)
    elif action == "pricing":
        # Show all plans as buttons to update price
        plans = await get_all_plans()
        if not plans:
            await query.message.edit_text("⚠️ No plans in database.", reply_markup=back_btn)
        else:
            buttons = []
            row = []
            for p in plans:
                label = f"{p['plan_key']} - ₹{p['price']}"
                row.append(InlineKeyboardButton(label, callback_data=f"price_sel_{p['plan_key']}", style=ButtonStyle.PRIMARY))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)])
            
            await query.message.edit_text(
                "💰 **UPDATE PRICING**\n\n"
                "Select a plan to change its price:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    elif action == "reset_plans":
        await seed_default_plans()
        await query.message.edit_text(
            "✅ **Plans Reset**\n\nAll 8 default plans have been re-seeded into the database.",
            reply_markup=back_btn
        )
    elif action == "back":
        await query.message.edit_text("🛡️ **SUDO ADMIN PANEL**\n\nSelect a command below:", reply_markup=build_sudo_panel())
    else:
        hint = hints.get(action, "❓ Unknown action.")
        await query.message.edit_text(hint, reply_markup=back_btn)
    
    await query.answer()

# --- Pricing plan selection ---
@bot.on_callback_query(filters.regex(r"^price_sel_(\w+)$"))
async def price_plan_selected(client, query):
    if query.from_user.id != ADMIN_ID and not await is_staff(query.from_user.id):
        return await query.answer("Access denied.", show_alert=True)
    
    plan_key = query.matches[0].group(1)
    AWAITING_PLAN_INPUT[query.from_user.id] = {"action": "price", "plan_key": plan_key}
    
    await query.message.edit_text(
        f"💰 **Update Price: `{plan_key}`**\n\n"
        f"Please send the **new price in INR** (numbers only):\n"
        f"Example: `20`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="panel_pricing", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# --- Handle admin's price input ---
@bot.on_message(filters.private & filters.text)
async def handle_price_input(client, message):
    user_id = message.from_user.id
    if user_id not in AWAITING_PLAN_INPUT:
        return
    
    state = AWAITING_PLAN_INPUT[user_id]
    if state["action"] != "price":
        return
    
    try:
        new_price = int(message.text.strip())
        if new_price < 1:
            raise ValueError("Price must be positive")
    except:
        return await message.reply("❌ Invalid input. Please send a positive number.")
    
    plan_key = state["plan_key"]
    success = await update_plan_price(plan_key, new_price)
    
    del AWAITING_PLAN_INPUT[user_id]
    
    if success:
        await message.reply(
            f"✅ **Price Updated!**\n\n"
            f"Plan: `{plan_key}`\n"
            f"New Price: **₹{new_price}**\n\n"
            f"Changes are live on the plans page and QR payments.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_pricing", style=ButtonStyle.PRIMARY)]
            ])
        )
    else:
        await message.reply("⚠️ Failed to update. Plan key not found.")

# ============================================================
# --- 1. SUDO MANAGEMENT (OWNER ONLY) ---
# ============================================================

@bot.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 4:
        return await message.reply("❌ Usage: `/addsudo <user_id> <can_ban 0/1> <can_pay 0/1>`")
    try:
        uid = int(args[1])
        can_ban = int(args[2])
        can_pay = int(args[3])
        from database import add_sudo
        await add_sudo(uid, can_ban, can_pay)
        await message.reply(f"👤 **Sudo Added:** `{uid}`\nPowers: Ban({can_ban}) | Pay({can_pay})")
    except Exception as e:
        await message.reply(f"❌ **Error:** {e}")

@bot.on_message(filters.command("rmsudo") & filters.private)
async def rm_sudo_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 2:
        return await message.reply("❌ Usage: `/rmsudo <user_id>`")
    uid = int(args[1])
    from database import remove_sudo
    await remove_sudo(uid)
    await message.reply(f"❌ **Sudo Removed:** `{uid}`")

@bot.on_message(filters.command("sudolist") & filters.private)
async def sudo_list(client, message):
    if message.from_user.id != ADMIN_ID: return
    from database import list_all_sudos
    rows = await list_all_sudos()
    if not rows: return await message.reply("No staff found.")
    msg = "🛡️ **Empire Staff List:**\n\n"
    for r in rows:
        msg += f"👤 `{r[0]}` | Ban: {r[1]} | Pay: {r[2]}\n"
    await message.reply(msg)

# --- 2. MODERATION ---

@bot.on_message(filters.command("ban") & filters.private)
async def ban_handler(client, message):
    if not await check_power(message.from_user.id, 'ban'): return
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        return await message.reply("❌ Usage: `/ban <user_id> <reason>`")
    user_id = int(args[1])
    reason = args[2] if len(args) > 2 else "No reason provided."
    await ban_user(user_id, reason)
    if user_id in ACTIVE_CLIENTS: await SessionManager.stop_userbot(user_id)
    await message.reply(f"🚫 **User Banned:** `{user_id}`\n📝 Reason: {reason}")

@bot.on_message(filters.command("unban") & filters.private)
async def unban_handler(client, message):
    if not await check_power(message.from_user.id, 'ban'): return
    args = message.text.split()
    if len(args) != 2: return await message.reply("❌ Usage: `/unban <user_id>`")
    user_id = int(args[1])
    await unban_user(user_id)
    await message.reply(f"✅ **User Unbanned:** `{user_id}`")

@bot.on_message(filters.command("logout") & filters.private)
async def logout_handler(client, message):
    if not await is_staff(message.from_user.id): return
    args = message.text.split()
    if len(args) != 2: return await message.reply("❌ Usage: `/logout <user_id>`")
    user_id = int(args[1])
    if user_id in ACTIVE_CLIENTS:
        try:
            await ACTIVE_CLIENTS[user_id]["client"].log_out()
            del ACTIVE_CLIENTS[user_id]
        except: pass
    await remove_user_session(user_id)
    await message.reply(f"✅ **Logout Done:** `{user_id}` session terminated.")

# --- 3. TESTING CONTROL ---

@bot.on_message(filters.command("testmode") & filters.private)
async def toggle_test_mode(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await message.reply("❌ Usage: `/testmode <module> <on/off> [message]`")
    
    module = args[1].lower()
    mode = args[2].lower()
    custom_msg = args[3] if len(args) > 3 else None
    status = (mode == "on")
    
    from database import set_module_testing, db
    await set_module_testing(module, status)
    
    status_text = "🧪 LOCKED (Internal Testing)" if status else "🌍 PUBLIC (Live)"
    await message.reply(f"🛡️ **Module Control Update**\n📦 **Module:** `{module.upper()}`\n📊 **Status:** `{status_text}`")
    
    if mode == "off" and custom_msg:
        status_msg = await message.reply("📢 Broadcasting update to all users...")
        done, failed = 0, 0
        cursor = db["users"].find({}, {"user_id": 1})
        broadcast_text = (
            f"🚀 **New Module Update: {module.upper()}**\n\n"
            f"{custom_msg}\n\n"
            f"👉 Use /modules to check it out!"
        )
        async for user in cursor:
            try:
                await bot.send_message(user["user_id"], broadcast_text)
                done += 1
                await asyncio.sleep(0.3)
            except:
                failed += 1
        await status_msg.edit_text(f"✅ **Update Broadcasted!**\n👤 Sent to: `{done}` users.")

# --- 4. BILLING ---

@bot.on_message(filters.command("approve") & filters.private)
async def manual_approve(client, message):
    if not await check_power(message.from_user.id, 'pay'): return
    args = message.text.split()
    if len(args) < 4:
        return await message.reply("❌ Usage: `/approve <user_id> <plan> <days> [hours] [minutes]`")
    try:
        user_id = int(args[1])
        st, _ = await get_sub_info(user_id)
        if st == "Active":
            return await message.reply("⚠️ This user already has an active plan. Cancel it first.")
        
        plan_name = args[2].replace("_", " ")
        d = int(args[3])
        h = int(args[4]) if len(args) > 4 else 0
        m = int(args[5]) if len(args) > 5 else 0
        await add_subscription(user_id, plan_type=plan_name, days=d, hours=h, minutes=m)
        await message.reply(f"✅ **Approved:** `{user_id}`\nPlan: {plan_name} for {d}d {h}h")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client, message):
    if not await check_power(message.from_user.id, 'pay'): return
    args = message.text.split()
    if len(args) != 2: return await message.reply("❌ Usage: `/cancel <user_id>`")
    user_id = int(args[1])
    await cancel_subscription(user_id)
    if user_id in ACTIVE_CLIENTS: await SessionManager.stop_userbot(user_id)
    await message.reply(f"📉 **Plan Cancelled:** `{user_id}`")

@bot.on_message(filters.command("transfer") & filters.private)
async def transfer_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 3: return await message.reply("❌ Usage: `/transfer <from_id> <to_id>`")
    f, t = int(args[1]), int(args[2])
    await transfer_subscription(f, t)
    await message.reply(f"♻️ **Transfer Done:** From `{f}` to `{t}`")

# --- 5. SYSTEM TOOLS ---

@bot.on_message(filters.command("active") & filters.private)
async def active_sessions(client, message):
    if not await is_staff(message.from_user.id): return
    if not ACTIVE_CLIENTS: return await message.reply("No active userbots.")
    msg = "🚀 **Active Sessions:**\n\n"
    for uid in list(ACTIVE_CLIENTS.keys()):
        msg += f"👤 `{uid}`\n"
    await message.reply(msg)

@bot.on_message(filters.command("stats") & filters.private)
async def bot_stats(client, message):
    if not await is_staff(message.from_user.id): return
    u_count = await users_db_proxy.count_documents({})
    s_count = await subs_db_proxy.count_documents({})
    await message.reply(
        f"📊 **Empire Global Stats**\n\n"
        f"👤 **Total Registered:** `{u_count}`\n"
        f"💎 **Active Premium:** `{s_count}`\n"
        f"📡 **Running Bots:** `{len(ACTIVE_CLIENTS)}`"
    )

@bot.on_message(filters.command("info") & filters.private)
async def user_info(client, message):
    if not await is_staff(message.from_user.id): return
    args = message.text.split()
    if len(args) != 2: return await message.reply("❌ Usage: `/info <user_id>`")
    user_id = int(args[1])
    status, time_left = await get_sub_info(user_id)
    claimed = await has_claimed_trial(user_id)
    await message.reply(f"👤 **Info:** `{user_id}`\n🎁 Trial: `{'Claimed' if claimed else 'Available'}`\n💳 Plan: `{status}`\n⏳ Left: `{time_left}`")

# --- 6. BROADCAST & BACKUP ---

@bot.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(client, message):
    if not await is_staff(message.from_user.id): return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply("❌ Usage: `/broadcast <message>`\n\nFor newlines: `/broadcast line1\nline2`")
    
    msg = args[1]
    status_msg = await message.reply("📣 Broadcasting to all users...")
    cursor = db["users"].find({}, {"user_id": 1})
    done, failed = 0, 0
    async for user in cursor:
        try:
            await bot.send_message(user["user_id"], msg)
            done += 1
            await asyncio.sleep(0.3)
        except:
            failed += 1
    await status_msg.edit_text(f"✅ **Broadcast Finished!**\n\n👤 **Sent to:** `{done}` users\n❌ **Failed:** `{failed}`")

@bot.on_message(filters.command("getdb") & filters.private)
async def get_db_backup(client, message):
    if not await is_staff(message.from_user.id): return
    status_msg = await message.reply("⏳ Exporting cloud data...")
    try:
        data = {}
        for coll in ["users", "subscriptions", "banned_users", "plans"]:
            cursor = db[coll].find({})
            data[coll] = [doc async for doc in cursor]
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, default=str, indent=2)
        await bot.send_document(message.chat.id, "backup.json", caption="📁 **Empire Cloud Backup (JSON)**")
        os.remove("backup.json")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")

# --- 7. SETTINGS ---

@bot.on_message(filters.command("toggleplan") & filters.private)
async def toggle_plan(client, message):
    if not await check_power(message.from_user.id, 'pay'): return
    args = message.text.split()
    if len(args) != 3: return await message.reply("❌ Usage: `/toggleplan <key> <on/off>`")
    key, status = args[1], args[2]
    await set_plan_status(key, status)
    await message.reply(f"✅ Plan `{key}` turned `{status}`.")

@bot.on_message(filters.command("maintenance") & filters.private)
async def maintenance_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split(maxsplit=2)
    if len(args) < 2: return await message.reply("❌ Usage: `/maintenance <on/off> [message]`")
    status = args[1].lower()
    text = args[2] if len(args) > 2 else "Under Maintenance."
    await set_maintenance(status, text)
    await message.reply(f"⚙️ Maintenance: {status.upper()}")

# --- 8. STAFF HELP ---

@bot.on_message(filters.command("sudohelp") & filters.private)
async def sudo_help(client, message):
    from database import is_staff, get_sudo_info
    if not await is_staff(message.from_user.id): return
    
    powers = await get_sudo_info(message.from_user.id)
    is_owner = (message.from_user.id == ADMIN_ID)
    
    help_msg = "🛡️ **Empire Admin Control Center**\n\n"
    help_msg += "Use `/admin` for the **Button Panel** (recommended).\n\n"
    help_msg += "**Commands:**\n"
    
    if is_owner:
        help_msg += "👑 **Owner:**\n"
        help_msg += "• `/addsudo <ID> <Ban> <Pay>`\n"
        help_msg += "• `/rmsudo <ID>`\n"
        help_msg += "• `/sudolist`\n"
        help_msg += "• `/broadcast <Msg>`\n"
        help_msg += "• `/transfer <From> <To>`\n"
        help_msg += "• `/maintenance <on/off> <msg>`\n"
        help_msg += "• `/testmode <name> on/off`\n"
        help_msg += "• `/getdb`\n\n"
    
    if is_owner or (powers and powers[0] == 1):
        help_msg += "🚫 **Bans:**\n• `/ban <ID> <Reason>`\n• `/unban <ID>`\n• `/logout <ID>`\n\n"
    
    if is_owner or (powers and powers[1] == 1):
        help_msg += "💳 **Billing:**\n• `/approve <ID> <Plan> <D> <H> <M>`\n• `/cancel <ID>`\n• `/active`\n• `/info <ID>`\n• `/stats`\n• `/toggleplan <key> <on/off>`\n"
    
    await message.reply(help_msg)

# --- 9. ACTIVE PLANS REPORT ---

@bot.on_message(filters.command(["active_plans", "activeplans"]) & filters.private)
async def active_plans_report(client, message):
    if not await is_staff(message.from_user.id): return
    status_msg = await message.reply("⏳ Generating report...")
    cursor = db["subscriptions"].find({"status": "active"})
    report = "EMPIRE ACTIVE PLANS\n" + "="*20 + "\n"
    async for sub in cursor:
        report += f"ID: {sub['user_id']} | Plan: {sub['plan']} | Expiry: {sub['expiry_date']}\n"
    with open("plans.txt", "w") as f: f.write(report)
    await bot.send_document(message.chat.id, "plans.txt", caption="📊 **Plan Report**")
    os.remove("plans.txt")
    await status_msg.delete()
