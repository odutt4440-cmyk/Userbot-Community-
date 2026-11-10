import datetime
import asyncio
import os
import json
from bot_instance import bot 
from telethon import events, Button, errors
from config import ADMIN_ID, SUDO_USERS, LOG_GROUP
from core.session_manager import ACTIVE_CLIENTS, SessionManager

# --- Sabse zaroori 15+ functions database.py se ---
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
    db, # MongoDB Object
    get_ban_info,
    users_db_proxy, 
    set_module_testing,
    is_module_in_testing,
    subs_db_proxy
)

# --- HELPER: STAFF PERMISSION CHECK ---
async def check_power(user_id, power_type):
    if user_id == ADMIN_ID: return True
    info = await get_sudo_info(user_id)
    if not info: return False
    # can_ban is index 0, can_pay is index 1
    return info[0] == 1 if power_type == 'ban' else info[1] == 1

# --- 1. SUDO MANAGEMENT (OWNER ONLY) ---

@bot.on(events.NewMessage(pattern=r'/addsudo (\d+) (\d) (\d)'))
async def add_sudo_handler(event):
    if event.sender_id != ADMIN_ID: return
    try:
        uid = int(event.pattern_match.group(1))
        can_ban = int(event.pattern_match.group(2))
        can_pay = int(event.pattern_match.group(3))
        from database import add_sudo
        await add_sudo(uid, can_ban, can_pay)
        await event.reply(f"👤 **Sudo Added:** `{uid}`\nPowers: Ban({can_ban}) | Pay({can_pay})")
    except Exception as e:
        await event.reply(f"❌ **Error:** {e}")

@bot.on(events.NewMessage(pattern=r'/rmsudo (\d+)'))
async def rm_sudo_handler(event):
    if event.sender_id != ADMIN_ID: return
    uid = int(event.pattern_match.group(1))
    from database import remove_sudo
    await remove_sudo(uid)
    await event.reply(f"❌ **Sudo Removed:** `{uid}`")

@bot.on(events.NewMessage(pattern='/sudolist'))
async def sudo_list(event):
    if event.sender_id != ADMIN_ID: return
    from database import list_all_sudos
    rows = await list_all_sudos()
    if not rows: return await event.reply("No staff found.")
    msg = "🛡️ **Empire Staff List:**\n\n"
    for r in rows:
        msg += f"👤 `{r[0]}` | Ban: {r[1]} | Pay: {r[2]}\n"
    await event.reply(msg)

# --- 2. MODERATION (BAN/UNBAN/LOGOUT) ---

@bot.on(events.NewMessage(pattern=r'/ban (\d+)(?:\s+(.*))?'))
async def ban_handler(event):
    if not await check_power(event.sender_id, 'ban'): return
    user_id = int(event.pattern_match.group(1))
    reason = event.pattern_match.group(2) or "No reason provided."
    await ban_user(user_id, reason)
    if user_id in ACTIVE_CLIENTS: await SessionManager.stop_userbot(user_id)
    await event.reply(f"🚫 **User Banned:** `{user_id}`\n📝 Reason: {reason}")

@bot.on(events.NewMessage(pattern=r'/unban (\d+)'))
async def unban_handler(event):
    if not await check_power(event.sender_id, 'ban'): return
    user_id = int(event.pattern_match.group(1))
    await unban_user(user_id)
    await event.reply(f"✅ **User Unbanned:** `{user_id}`")

@bot.on(events.NewMessage(pattern=r'/logout (\d+)'))
async def logout_handler(event):
    if not await is_staff(event.sender_id): return
    user_id = int(event.pattern_match.group(1))
    if user_id in ACTIVE_CLIENTS:
        try:
            await ACTIVE_CLIENTS[user_id]["client"].log_out()
            del ACTIVE_CLIENTS[user_id]
        except: pass
    await remove_user_session(user_id)
    await event.reply(f"✅ **Logout Done:** `{user_id}` session terminated.")

# --- 6. TESTING CONTROL (OWNER ONLY) ---

# Usage: /testmode wordseek off Update is Done!
@bot.on(events.NewMessage(pattern=r'(?i)^/testmode (\w+) (on|off)(?:\s+(.*))?'))
async def toggle_test_mode(event):
    if event.sender_id != ADMIN_ID: return
    
    module = event.pattern_match.group(1).lower()
    mode = event.pattern_match.group(2).lower()
    custom_msg = event.pattern_match.group(3) # Optional Message
    status = (mode == "on")
    
    from database import set_module_testing, db
    await set_module_testing(module, status)
    
    # UI Info
    status_text = "🧪 LOCKED (Internal Testing)" if status else "🌍 PUBLIC (Live)"
    await event.reply(f"🛡️ **Module Control Update**\n📦 **Module:** `{module.upper()}`\n📊 **Status:** `{status_text}`")

    
    # 🔥 AUTO-BROADCAST LOGIC (Fixed for normal text)
    if mode == "off" and custom_msg:
        status_msg = await event.respond("📢 **Broadcasting update to all users...**")
        done, failed = 0, 0
        
        cursor = db["users"].find({}, {"user_id": 1})
        
        # --- Clean Professional Formatting ---
        broadcast_text = (
            f"🚀 **New Module Update: {module.upper()}**\n\n"
            f"{custom_msg}\n\n" # 🔥 Backticks hata diye hain
            f"👉 Use /modules to check it out!"
        )
        
        async for user in cursor:
            try:
                await bot.send_message(user["user_id"], broadcast_text, link_preview=False)
                done += 1
                await asyncio.sleep(0.3)
            except:
                failed += 1
        
        await status_msg.edit(f"✅ **Update Broadcasted!**\n👤 Sent to: `{done}` users.")

# --- 3. BILLING (APPROVE/CANCEL/TRANSFER) ---

@bot.on(events.NewMessage(pattern=r'/approve (\d+) (\w+) (\d+)(?: (\d+))?(?: (\d+))?'))
async def manual_approve(event):
    if not await check_power(event.sender_id, 'pay'): return
    try:
        user_id = int(event.pattern_match.group(1))
        # Status Check
        st, _ = await get_sub_info(user_id)
        if st == "Active":
            return await event.reply("⚠️ This user already has a plan. Cancel it first.")
        
        plan_name = event.pattern_match.group(2).replace("_", " ")
        d = int(event.pattern_match.group(3))
        h = int(event.pattern_match.group(4) or 0)
        m = int(event.pattern_match.group(5) or 0)
        await add_subscription(user_id, plan_type=plan_name, days=d, hours=h, minutes=m)
        await event.reply(f"✅ **Approved:** `{user_id}`\nPlan: {plan_name} for {d}d {h}h")
    except Exception as e:
        await event.reply(f"❌ Error: {e}")

@bot.on(events.NewMessage(pattern=r'/cancel (\d+)'))
async def cancel_handler(event):
    if not await check_power(event.sender_id, 'pay'): return
    user_id = int(event.pattern_match.group(1))
    await cancel_subscription(user_id)
    if user_id in ACTIVE_CLIENTS: await SessionManager.stop_userbot(user_id)
    await event.reply(f"📉 **Plan Cancelled:** `{user_id}`")

@bot.on(events.NewMessage(pattern=r'/transfer (\d+) (\d+)'))
async def transfer_handler(event):
    if event.sender_id != ADMIN_ID: return
    f, t = int(event.pattern_match.group(1)), int(event.pattern_match.group(2))
    await transfer_subscription(f, t)
    await event.reply(f"♻️ **Transfer Done:** From `{f}` to `{t}`")

# --- 4. SYSTEM TOOLS (Staff Access) ---

@bot.on(events.NewMessage(pattern='/active'))
async def active_sessions(event):
    if not await is_staff(event.sender_id): return
    if not ACTIVE_CLIENTS: return await event.reply("No active userbots.")
    msg = "🚀 **Active Sessions:**\n\n"
    for uid in list(ACTIVE_CLIENTS.keys()):
        msg += f"👤 `{uid}`\n"
    await event.reply(msg)

# --- 7. GLOBAL STATS (Fixed for MongoDB Proxy) ---
@bot.on(events.NewMessage(pattern='/stats'))
async def bot_stats(event):
    if not await is_staff(event.sender_id): return
    
    # Proxy objects use karke async count mangenge
    u_count = await users_db_proxy.count_documents({})
    s_count = await subs_db_proxy.count_documents({})
    
    await event.reply(
        f"📊 **Empire Global Stats**\n\n"
        f"👤 **Total Registered:** `{u_count}`\n"
        f"💎 **Active Premium:** `{s_count}`\n"
        f"📡 **Running Bots:** `{len(ACTIVE_CLIENTS)}`"
    )

@bot.on(events.NewMessage(pattern=r'/info (\d+)'))
async def user_info(event):
    if not await is_staff(event.sender_id): return
    user_id = int(event.pattern_match.group(1))
    status, time_left = await get_sub_info(user_id)
    claimed = await has_claimed_trial(user_id)
    await event.reply(f"👤 **Info:** `{user_id}`\n🎁 Trial: `{'Claimed' if claimed else 'Available'}`\n💳 Plan: `{status}`\n⏳ Left: `{time_left}`")

# --- 5. BROADCAST & BACKUP ---
@bot.on(events.NewMessage(pattern=r'(?i)^/broadcast(?:\s+([\s\S]+))?'))
async def broadcast_handler(event):
    if not await is_staff(event.sender_id): return
    
    # 🔥 FIX: [\s\S]+ use kiya hai taaki poora paragraph (newlines ke sath) capture ho
    msg = event.pattern_match.group(1)
    
    if not msg:
        return await event.reply("❌ **Usage:** `/broadcast Hello everyone\nThis is a new line.`")

    status_msg = await event.reply("📣 **Broadcasting to all users...**")
    
    # Database se users ki list uthao
    cursor = db["users"].find({}, {"user_id": 1})
    done, failed = 0, 0
    
    async for user in cursor:
        try:
            # Formatting (Bold, Links, Emojis) as-it-is bhejega
            await bot.send_message(user["user_id"], msg, link_preview=False)
            done += 1
            # Rate limit protection
            await asyncio.sleep(0.3) 
        except:
            failed += 1
            
    await status_msg.edit(f"✅ **Broadcast Finished!**\n\n👤 **Sent to:** `{done}` users\n❌ **Failed:** `{failed}`")

@bot.on(events.NewMessage(pattern='/getdb'))
async def get_db_backup(event):
    if not await is_staff(event.sender_id): return
    status_msg = await event.reply("⏳ **Exporting Cloud Data...**")
    try:
        # Mongo data ko JSON file me convert karke bhejenge
        data = {}
        for coll in ["users", "subscriptions", "banned_users"]:
            cursor = db[coll].find({})
            data[coll] = [doc async for doc in cursor]
        
        with open("backup.json", "w", encoding="utf-8") as f:
            json.dump(data, f, default=str, indent=2)
            
        await bot.send_file(event.chat_id, "backup.json", caption="📁 **Empire Cloud Backup (JSON)**")
        os.remove("backup.json")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit(f"❌ Error: {e}")

# --- 6. SETTINGS (Maintenance & Toggles) ---

@bot.on(events.NewMessage(pattern=r'/toggleplan (\w+) (on|off)'))
async def toggle_plan(event):
    if not await check_power(event.sender_id, 'pay'): return
    key, status = event.pattern_match.group(1), event.pattern_match.group(2)
    await set_plan_status(key, status)
    await event.reply(f"✅ Plan `{key}` turned `{status}`.")

@bot.on(events.NewMessage(pattern=r'/maintenance (on|off)(?:\s+(.*))?'))
async def maintenance_handler(event):
    if event.sender_id != ADMIN_ID: return
    status = event.pattern_match.group(1).lower()
    text = event.pattern_match.group(2) or "Under Maintenance."
    await set_maintenance(status, text)
    await event.reply(f"⚙️ Maintenance: {status.upper()}")

# --- STAFF HELP CENTER (Owner & Sudo Only) ---
@bot.on(events.NewMessage(pattern=r'(?i)^/sudohelp'))
async def sudo_help(event):
    # 🛡️ Staff Check
    from database import is_staff, get_sudo_info
    if not await is_staff(event.sender_id):
        return 

    # Powers fetch karo commands dikhane ke liye
    powers = await get_sudo_info(event.sender_id)
    is_owner = (event.sender_id == ADMIN_ID)

    help_msg = "🛡️ **Empire Admin Control Center**\n\n"
    help_msg += "Welcome to the professional management suite. Below are the commands you can use based on your power level.\n\n"

    # --- OWNER SECTION ---
    if is_owner:
        help_msg += "👑 **Owner Privileges (Exclusive):**\n"
        help_msg += "• `/addsudo <ID> <Ban> <Pay>` - Add new staff\n"
        help_msg += "  👉 _Ex: /addsudo 1234567 1 1_ (Full Power)\n"
        help_msg += "• `/rmsudo <ID>` - Remove a staff member\n"
        help_msg += "  👉 _Ex: /rmsudo 1234567_\n"
        help_msg += "• `/sudolist` - View current staff members\n"
        help_msg += "• `/broadcast <Msg>` - Message all bot users\n"
        help_msg += "  👉 _Ex: /broadcast Bot updated!_\n"
        help_msg += "• `/transfer <FromID> <ToID>` - Move subscription\n"
        help_msg += "  👉 _Ex: /transfer 111 222_\n"
        help_msg += "• `/reset_trial <ID>` - Allow trial again\n"
        help_msg += "• `/maintenance <on/off> <msg>` - Master Switch\n"
        help_msg += "• `/testmode <name> on/off` - Toggle Admin Lock\n" 
        help_msg += "• `/getdb` - Download Cloud JSON Backup\n\n"

    # --- BAN MANAGEMENT ---
    if is_owner or (powers and powers[0] == 1): # can_ban power
        help_msg += "🚫 **Security & Bans:**\n"
        help_msg += "• `/ban <ID> <Reason>` - Block with reason\n"
        help_msg += "  👉 _Ex: /ban 1234567_Spamming_\n"
        help_msg += "• `/unban <ID>` - Restore user access\n"
        help_msg += "• `/logout <ID>` - Force session termination\n\n"

    # --- FINANCIAL & SYSTEM TOOLS ---
    if is_owner or (powers and powers[1] == 1): # can_pay power
        help_msg += "💳 **Management & Billing:**\n"
        help_msg += "• `/approve <ID> <Plan> <D> <H> <M>` - Add manual time\n"
        help_msg += "  👉 _Ex: /approve 123 Ultra_Standard 30 0 0_\n"
        help_msg += "• `/cancel <ID>` - Terminate premium plan\n"
        help_msg += "• `/active` - List currently running userbots\n"
        help_msg += "• `/active_plans` - Generate all users report file\n"
        help_msg += "• `/info <ID>` - Check profile & expiry info\n"
        help_msg += "• `/stats` - View global bot statistics\n"
        help_msg += "• `/toggleplan <key> <on/off>` - Enable/Disable a plan\n"
        help_msg += "  👉 _Ex: /toggleplan u_std_15 off_\n"

    await event.reply(help_msg)

# --- 8. ACTIVE PLANS REPORT ---

@bot.on(events.NewMessage(pattern=r'(?i)^/active_?plans'))
async def active_plans_report(event):
    if not await is_staff(event.sender_id): return
    status_msg = await event.reply("⏳ Generating Report...")
    cursor = db["subscriptions"].find({"status": "active"})
    report = "EMPIRE ACTIVE PLANS\n" + "="*20 + "\n"
    async for sub in cursor:
        report += f"ID: {sub['user_id']} | Plan: {sub['plan']} | Expiry: {sub['expiry_date']}\n"
    
    with open("plans.txt", "w") as f: f.write(report)
    await bot.send_file(event.chat_id, "plans.txt", caption="📊 **Plan Report**")
    os.remove("plans.txt")
    await status_msg.delete()
