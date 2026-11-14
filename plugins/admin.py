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
    get_maintenance,
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
    add_sudo,
    remove_sudo,
    list_all_sudos,
)

# --- HELPER: STAFF PERMISSION CHECK ---
async def check_power(user_id, power_type):
    if user_id == ADMIN_ID: return True
    info = await get_sudo_info(user_id)
    if not info: return False
    return info[0] == 1 if power_type == 'ban' else info[1] == 1

# ============================================================
# --- STATE TRACKING ---
# ============================================================
AWAITING_PLAN_INPUT = {}
AWAITING_SUDO_INPUT = {}
# Format: {user_id: {"action": "broadcast"/"approve"/"ban", ...}}
AWAITING_ADMIN_INPUT = {}

# ============================================================
# --- DYNAMIC ADMIN PANEL ---
# ============================================================

def build_sudo_panel(is_owner, can_ban, can_pay):
    buttons = []
    
    if is_owner:
        buttons.extend([
            [InlineKeyboardButton("🚫 Ban User", callback_data="panel_ban", style=ButtonStyle.DANGER),
             InlineKeyboardButton("✅ Unban User", callback_data="panel_unban", style=ButtonStyle.SUCCESS)],
            [InlineKeyboardButton("👑 Add Sudo", callback_data="panel_addsudo", style=ButtonStyle.SUCCESS),
             InlineKeyboardButton("❌ Remove Sudo", callback_data="panel_rmsudo", style=ButtonStyle.DANGER)],
            [InlineKeyboardButton("📢 Broadcast", callback_data="panel_broadcast", style=ButtonStyle.PRIMARY),
             InlineKeyboardButton("🛠️ Maintenance", callback_data="panel_maint", style=ButtonStyle.DANGER)],
            [InlineKeyboardButton("📊 Stats", callback_data="panel_stats", style=ButtonStyle.SUCCESS),
             InlineKeyboardButton("📋 Sudolist", callback_data="panel_sudolist", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton("💳 Approve Plan", callback_data="panel_approve", style=ButtonStyle.SUCCESS),
             InlineKeyboardButton("📉 Cancel Plan", callback_data="panel_cancel", style=ButtonStyle.DANGER)],
            [InlineKeyboardButton("👤 User Info", callback_data="panel_info", style=ButtonStyle.PRIMARY),
             InlineKeyboardButton("📡 Active Bots", callback_data="panel_active", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton("💰 Update Pricing", callback_data="panel_pricing", style=ButtonStyle.SUCCESS),
             InlineKeyboardButton("🔄 Reset Plans", callback_data="panel_reset_plans", style=ButtonStyle.DANGER)],
        ])
    else:
        if can_ban:
            buttons.append([
                InlineKeyboardButton("🚫 Ban User", callback_data="panel_ban", style=ButtonStyle.DANGER),
                InlineKeyboardButton("✅ Unban User", callback_data="panel_unban", style=ButtonStyle.SUCCESS)
            ])
            buttons.append([InlineKeyboardButton("📡 Active Bots", callback_data="panel_active", style=ButtonStyle.PRIMARY)])
            
        if can_pay:
            buttons.append([
                InlineKeyboardButton("💳 Approve Plan", callback_data="panel_approve", style=ButtonStyle.SUCCESS),
                InlineKeyboardButton("📉 Cancel Plan", callback_data="panel_cancel", style=ButtonStyle.DANGER)
            ])
            buttons.append([InlineKeyboardButton("💰 Update Pricing", callback_data="panel_pricing", style=ButtonStyle.SUCCESS)])
            
        buttons.append([
            InlineKeyboardButton("📊 Stats", callback_data="panel_stats", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("👤 User Info", callback_data="panel_info", style=ButtonStyle.PRIMARY)
        ])

    buttons.append([InlineKeyboardButton("❌ Close Panel", callback_data="panel_close", style=ButtonStyle.DANGER)])
    return InlineKeyboardMarkup(buttons)

# 1. Command handler
@bot.on_message(filters.command("admin") & filters.private)
async def sudo_panel_command(client, message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        is_owner, can_ban, can_pay = True, True, True
    else:
        info = await get_sudo_info(user_id)
        if not info:
            return await message.reply("🚫 This command is restricted to admins and sudo users only.")
        is_owner = False
        can_ban = info[0] == 1
        can_pay = info[1] == 1
    
    await message.reply(
        "🛡️ **SUDO ADMIN PANEL**\n\n"
        "Select a command below:",
        reply_markup=build_sudo_panel(is_owner, can_ban, can_pay)
    )

# 2. Start Menu Button Handler
@bot.on_callback_query(filters.regex("^admin_panel_main$"))
async def start_menu_admin_panel(client, query):
    user_id = query.from_user.id
    
    if user_id == ADMIN_ID:
        is_owner, can_ban, can_pay = True, True, True
    else:
        info = await get_sudo_info(user_id)
        if not info:
            return await query.answer("Access denied.", show_alert=True)
        is_owner = False
        can_ban = info[0] == 1
        can_pay = info[1] == 1
    
    await query.message.edit_text(
        "🛡️ **SUDO ADMIN PANEL**\n\n"
        "Select a command below:",
        reply_markup=build_sudo_panel(is_owner, can_ban, can_pay)
    )
    await query.answer()

# 3. Main Panel Callbacks
@bot.on_callback_query(filters.regex(r"^panel_"))
async def sudo_panel_callback(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID and not await is_staff(user_id):
        return await query.answer("Access denied.", show_alert=True)
    
    action = query.data.replace("panel_", "")
    
    if action == "close":
        return await query.message.delete()
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])

    # --- BUTTON BASED ACTIONS ---
    if action == "maint":
        is_maint, maint_text = await get_maintenance()
        status = "🟢 ON" if is_maint else "🔴 OFF"
        
        await query.message.edit_text(
            f"🛠️ **Maintenance Mode**\n\n"
            f"Current Status: **{status}**\n\n"
            f"Toggle the buttons below to change the bot's status instantly.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Turn ON (Lock Bot)", callback_data="maint_on", style=ButtonStyle.DANGER)],
                [InlineKeyboardButton("Turn OFF (Open Bot)", callback_data="maint_off", style=ButtonStyle.SUCCESS)],
                [InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]
            ])
        )
        return await query.answer()

    elif action == "broadcast":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "broadcast"}
        await query.message.edit_text(
            "📢 **Broadcast**\n\n"
            "Please send the message you want to broadcast to all users:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    elif action == "addsudo":
        AWAITING_SUDO_INPUT[user_id] = {"target_id": None, "can_ban": False, "can_pay": False}
        await query.message.edit_text(
            "👑 **ADD SUDO USER**\n\n"
            "Please send the **User ID** of the person you want to make Sudo:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    elif action == "pricing":
        plans = await get_all_plans()
        if not plans:
            return await query.message.edit_text("⚠️ No plans in database.", reply_markup=back_btn)
            
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
        
        return await query.message.edit_text(
            "💰 **UPDATE PRICING**\n\nSelect a plan to change its price:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif action == "stats":
        u_count = await users_db_proxy.count_documents({})
        s_count = await subs_db_proxy.count_documents({})
        return await query.message.edit_text(
            f"📊 **Empire Global Stats**\n\n"
            f"👤 **Total Registered:** `{u_count}`\n"
            f"💎 **Active Premium:** `{s_count}`\n"
            f"📡 **Running Bots:** `{len(ACTIVE_CLIENTS)}`",
            reply_markup=back_btn
        )
    elif action == "sudolist":
        rows = await list_all_sudos()
        if not rows:
            text = "📋 No sudo users found."
        else:
            text = "📋 **SUDO LIST**\n\n"
            for r in rows:
                text += f"• `{r[0]}` | Ban: {r[1]} | Pay: {r[2]}\n"
        return await query.message.edit_text(text, reply_markup=back_btn)
    elif action == "active":
        if not ACTIVE_CLIENTS:
            text = "📡 No active userbots."
        else:
            text = "📡 **Active Sessions:**\n\n"
            for uid in list(ACTIVE_CLIENTS.keys()):
                text += f"👤 `{uid}`\n"
        return await query.message.edit_text(text, reply_markup=back_btn)
    elif action == "reset_plans":
        await seed_default_plans()
        return await query.message.edit_text(
            "✅ **Plans Reset**\n\nAll 8 default plans have been re-seeded into the database.",
            reply_markup=back_btn
        )
    elif action == "back":
        AWAITING_SUDO_INPUT.pop(user_id, None)
        AWAITING_PLAN_INPUT.pop(user_id, None)
        AWAITING_ADMIN_INPUT.pop(user_id, None)
        
        if user_id == ADMIN_ID:
            is_owner, can_ban, can_pay = True, True, True
        else:
            info = await get_sudo_info(user_id)
            is_owner = False
            can_ban = info[0] == 1 if info else False
            can_pay = info[1] == 1 if info else False
            
        return await query.message.edit_text(
            "🛡️ **SUDO ADMIN PANEL**\n\nSelect a command below:", 
            reply_markup=build_sudo_panel(is_owner, can_ban, can_pay)
        )
    else:
        # Static hints for remaining commands
        hints = {
            "ban": "🚫 **Ban User**\n\nSend: /ban user_id reason",
            "unban": "✅ **Unban User**\n\nSend: /unban user_id",
            "rmsudo": "❌ **Remove Sudo**\n\nSend: /rmsudo user_id",
            "approve": "💳 **Approve Plan**\n\nSend: /approve user_id plan days hours minutes",
            "cancel": "📉 **Cancel Plan**\n\nSend: /cancel user_id",
            "info": "👤 **User Info**\n\nSend: /info user_id",
        }
        hint = hints.get(action, "❓ Unknown action.")
        return await query.message.edit_text(hint, reply_markup=back_btn)

# --- Maintenance Quick Toggles ---
@bot.on_callback_query(filters.regex("^maint_on$"))
async def maint_on_handler(client, query):
    await set_maintenance("on", "Bot is under maintenance. Please wait.")
    await query.message.edit_text(
        "✅ **Maintenance Mode ON**\n\nBot is now locked for all users.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_maint", style=ButtonStyle.PRIMARY)]])
    )
    await query.answer()

@bot.on_callback_query(filters.regex("^maint_off$"))
async def maint_off_handler(client, query):
    await set_maintenance("off", "")
    await query.message.edit_text(
        "✅ **Maintenance Mode OFF**\n\nBot is now accessible to everyone.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_maint", style=ButtonStyle.PRIMARY)]])
    )
    await query.answer()

# ============================================================
# --- SUDO TOGGLE & SAVE LOGIC ---
# ============================================================

@bot.on_callback_query(filters.regex("^sudo_toggle_ban$"))
async def toggle_ban_power(client, query):
    user_id = query.from_user.id
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id]["target_id"]:
        AWAITING_SUDO_INPUT[user_id]["can_ban"] = not AWAITING_SUDO_INPUT[user_id]["can_ban"]
        
        ban_status = "✅ ON" if AWAITING_SUDO_INPUT[user_id]["can_ban"] else "❌ OFF"
        pay_status = "✅ ON" if AWAITING_SUDO_INPUT[user_id]["can_pay"] else "❌ OFF"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Ban Power: {ban_status}", callback_data="sudo_toggle_ban", style=ButtonStyle.SUCCESS if AWAITING_SUDO_INPUT[user_id]["can_ban"] else ButtonStyle.DANGER)],
            [InlineKeyboardButton(f"Pay Power: {pay_status}", callback_data="sudo_toggle_pay", style=ButtonStyle.SUCCESS if AWAITING_SUDO_INPUT[user_id]["can_pay"] else ButtonStyle.DANGER)],
            [InlineKeyboardButton("💾 Save Sudo", callback_data="sudo_save", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]
        ])
        await query.message.edit_reply_markup(reply_markup=buttons)
    await query.answer()

@bot.on_callback_query(filters.regex("^sudo_toggle_pay$"))
async def toggle_pay_power(client, query):
    user_id = query.from_user.id
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id]["target_id"]:
        AWAITING_SUDO_INPUT[user_id]["can_pay"] = not AWAITING_SUDO_INPUT[user_id]["can_pay"]
        
        ban_status = "✅ ON" if AWAITING_SUDO_INPUT[user_id]["can_ban"] else "❌ OFF"
        pay_status = "✅ ON" if AWAITING_SUDO_INPUT[user_id]["can_pay"] else "❌ OFF"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Ban Power: {ban_status}", callback_data="sudo_toggle_ban", style=ButtonStyle.SUCCESS if AWAITING_SUDO_INPUT[user_id]["can_ban"] else ButtonStyle.DANGER)],
            [InlineKeyboardButton(f"Pay Power: {pay_status}", callback_data="sudo_toggle_pay", style=ButtonStyle.SUCCESS if AWAITING_SUDO_INPUT[user_id]["can_pay"] else ButtonStyle.DANGER)],
            [InlineKeyboardButton("💾 Save Sudo", callback_data="sudo_save", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]
        ])
        await query.message.edit_reply_markup(reply_markup=buttons)
    await query.answer()

@bot.on_callback_query(filters.regex("^sudo_save$"))
async def save_sudo_user(client, query):
    user_id = query.from_user.id
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id]["target_id"]:
        data = AWAITING_SUDO_INPUT[user_id]
        target_id = data["target_id"]
        can_ban = 1 if data["can_ban"] else 0
        can_pay = 1 if data["can_pay"] else 0
        
        await add_sudo(target_id, can_ban, can_pay)
        del AWAITING_SUDO_INPUT[user_id]
        
        await query.message.edit_text(
            f"✅ **Sudo Saved Successfully!**\n\n"
            f"👤 **User ID:** `{target_id}`\n"
            f"🚫 **Ban Power:** `{'ON' if can_ban else 'OFF'}`\n"
            f"💳 **Pay Power:** `{'ON' if can_pay else 'OFF'}`\n\n"
            f"This user can now access the Admin Panel.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
        )
    await query.answer()

# --- Pricing plan selection ---
@bot.on_callback_query(filters.regex(r"^price_sel_(\w+)$"))
async def price_plan_selected(client, query):
    if query.from_user.id != ADMIN_ID and not await check_power(query.from_user.id, 'pay'):
        return await query.answer("Access denied. 'Pay' power required.", show_alert=True)
    
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

# ============================================================
# --- SINGLE TEXT INPUT HANDLER ---
# ============================================================

@bot.on_message(filters.private & filters.text & ~filters.photo & ~filters.command(["start", "admin", "plan", "modules", "help", "commands"]), group=0)
async def handle_admin_inputs(client, message):
    user_id = message.from_user.id
    
    # 1. Handle Sudo User ID Input
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id]["target_id"] is None:
        if message.text.startswith('/'): return
        try:
            target_id = int(message.text.strip())
        except:
            return await message.reply("❌ Invalid ID. Please send a numeric Telegram ID.")
        
        AWAITING_SUDO_INPUT[user_id]["target_id"] = target_id
        
        ban_status = "✅ ON" if AWAITING_SUDO_INPUT[user_id]["can_ban"] else "❌ OFF"
        pay_status = "✅ ON" if AWAITING_SUDO_INPUT[user_id]["can_pay"] else "❌ OFF"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Ban Power: {ban_status}", callback_data="sudo_toggle_ban", style=ButtonStyle.SUCCESS if AWAITING_SUDO_INPUT[user_id]["can_ban"] else ButtonStyle.DANGER)],
            [InlineKeyboardButton(f"Pay Power: {pay_status}", callback_data="sudo_toggle_pay", style=ButtonStyle.SUCCESS if AWAITING_SUDO_INPUT[user_id]["can_pay"] else ButtonStyle.DANGER)],
            [InlineKeyboardButton("💾 Save Sudo", callback_data="sudo_save", style=ButtonStyle.PRIMARY)],
            [InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]
        ])
        
        await message.reply(
            f"👤 **Target User ID:** `{target_id}`\n\n"
            "Toggle the powers you want to give to this user, then click Save:",
            reply_markup=buttons
        )
        return

    # 2. Handle Broadcast Input
    if user_id in AWAITING_ADMIN_INPUT and AWAITING_ADMIN_INPUT[user_id].get("action") == "broadcast":
        msg = message.text
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
        
        # Safe deletion to prevent KeyError
        if user_id in AWAITING_ADMIN_INPUT:
            del AWAITING_ADMIN_INPUT[user_id]
            
        await status_msg.edit_text(
            f"✅ **Broadcast Finished!**\n\n👤 **Sent to:** `{done}` users\n❌ **Failed:** `{failed}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
        )
        return

    # 3. Handle Price Input
    if user_id in AWAITING_PLAN_INPUT:
        state = AWAITING_PLAN_INPUT[user_id]
        if state["action"] != "price": return
        
        try:
            new_price = int(message.text.strip())
            if new_price < 1: raise ValueError
        except:
            return await message.reply("❌ Invalid input. Please send a positive number.")
        
        plan_key = state["plan_key"]
        success = await update_plan_price(plan_key, new_price)
        del AWAITING_PLAN_INPUT[user_id]
        
        if success:
            await message.reply(
                f"✅ **Price Updated!**\n\nPlan: `{plan_key}`\nNew Price: **₹{new_price}**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Pricing", callback_data="panel_pricing", style=ButtonStyle.PRIMARY)]])
            )
        else:
            await message.reply("⚠️ Failed to update. Plan key not found.")
        return

# ============================================================
# --- 1. SUDO MANAGEMENT COMMANDS (Owner Only) ---
# ============================================================

@bot.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 4:
        return await message.reply("❌ Usage: `/addsudo <user_id> <can_ban 0/1> <can_pay 0/1>`")
    try:
        uid = int(args[1])
        await add_sudo(uid, int(args[2]), int(args[3]))
        await message.reply(f"👤 **Sudo Added:** `{uid}`")
    except Exception as e:
        await message.reply(f"❌ **Error:** {e}")

@bot.on_message(filters.command("rmsudo") & filters.private)
async def rm_sudo_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 2:
        return await message.reply("❌ Usage: `/rmsudo <user_id>`")
    await remove_sudo(int(args[1]))
    await message.reply(f"❌ **Sudo Removed:** `{args[1]}`")

@bot.on_message(filters.command("sudolist") & filters.private)
async def sudo_list(client, message):
    if message.from_user.id != ADMIN_ID: return
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
        return await message.reply("❌ Usage: `/broadcast <message>`")
    
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
