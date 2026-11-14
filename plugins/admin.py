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
    add_subscription, ban_user, unban_user, is_banned,
    transfer_subscription, cancel_subscription, get_sub_info,
    remove_user_session, has_claimed_trial, is_staff,
    get_sudo_info, set_plan_status, is_plan_available, set_maintenance,
    get_maintenance, db, get_ban_info, users_db_proxy, 
    set_module_testing, is_module_in_testing, subs_db_proxy,
    get_all_plans, update_plan_price, update_plan_days,
    toggle_plan_active, seed_default_plans, add_sudo,
    remove_sudo, list_all_sudos,
    get_active_sub, set_sub_expiry, reset_user_trial, shift_user_plan, get_plan
)

# --- HELPER: STAFF PERMISSION CHECK ---
async def check_power(user_id, perm_key):
    if user_id == ADMIN_ID: return True
    info = await get_sudo_info(user_id)
    if not info: return False
    return info.get(perm_key, 0) == 1

# ============================================================
# --- STATE TRACKING ---
# ============================================================
AWAITING_PLAN_INPUT = {}
AWAITING_SUDO_INPUT = {}
AWAITING_ADMIN_INPUT = {}  # {user_id: {"action": "...", "target_id": ...}}

# ============================================================
# --- DYNAMIC ADMIN PANEL ---
# ============================================================

def build_sudo_panel(is_owner, perms):
    def has(p): return is_owner or perms.get(p, 0) == 1
    
    buttons = []
    row1 = []
    if has("ban"): row1.append(InlineKeyboardButton("🚫 Ban", callback_data="panel_ban", style=ButtonStyle.DANGER))
    if has("unban"): row1.append(InlineKeyboardButton("✅ Unban", callback_data="panel_unban", style=ButtonStyle.SUCCESS))
    if row1: buttons.append(row1)

    row2 = []
    if has("approve"): row2.append(InlineKeyboardButton("💳 Approve Plan", callback_data="panel_approve", style=ButtonStyle.SUCCESS))
    if has("cancel"): row2.append(InlineKeyboardButton("📉 Cancel Plan", callback_data="panel_cancel", style=ButtonStyle.DANGER))
    if row2: buttons.append(row2)

    row3 = []
    if has("shift"): row3.append(InlineKeyboardButton("🔄 Shift Plan", callback_data="panel_shift_plan", style=ButtonStyle.SUCCESS))
    if has("days"): row3.append(InlineKeyboardButton("⏳ Manage Days", callback_data="panel_manage_days", style=ButtonStyle.SUCCESS))
    if row3: buttons.append(row3)

    row4 = []
    if has("trial"): row4.append(InlineKeyboardButton("🔁 Reset Trial", callback_data="panel_reset_trial", style=ButtonStyle.PRIMARY))
    if has("pricing"): row4.append(InlineKeyboardButton("💰 Update Pricing", callback_data="panel_pricing", style=ButtonStyle.SUCCESS))
    if row4: buttons.append(row4)

    row5 = []
    if has("broadcast"): row5.append(InlineKeyboardButton("📢 Broadcast", callback_data="panel_broadcast", style=ButtonStyle.PRIMARY))
    if has("maintenance"): row5.append(InlineKeyboardButton("🛠️ Maintenance", callback_data="panel_maint", style=ButtonStyle.DANGER))
    if row5: buttons.append(row5)

    row6 = []
    if has("stats"): row6.append(InlineKeyboardButton("📊 Stats", callback_data="panel_stats", style=ButtonStyle.SUCCESS))
    if has("sudolist"): row6.append(InlineKeyboardButton("📋 Sudo List", callback_data="panel_sudolist", style=ButtonStyle.PRIMARY))
    if row6: buttons.append(row6)

    row7 = []
    if has("info"): row7.append(InlineKeyboardButton("👤 User Info", callback_data="panel_info", style=ButtonStyle.PRIMARY))
    if has("active"): row7.append(InlineKeyboardButton("📡 Active Bots", callback_data="panel_active", style=ButtonStyle.PRIMARY))
    if row7: buttons.append(row7)

    # 🔥 NEW: Plan Enquiry Button
    row8 = []
    if has("info") or is_owner:
        row8.append(InlineKeyboardButton("🔍 Plan Enquiry", callback_data="panel_plan_enquiry", style=ButtonStyle.PRIMARY))
    if row8: buttons.append(row8)

    if is_owner:
        buttons.append([
            InlineKeyboardButton("👑 Add Sudo", callback_data="panel_addsudo", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("❌ Remove Sudo", callback_data="panel_rmsudo", style=ButtonStyle.DANGER)
        ])
        buttons.append([InlineKeyboardButton("🔄 Reset Plans", callback_data="panel_reset_plans", style=ButtonStyle.DANGER)])

    buttons.append([InlineKeyboardButton("❌ Close Panel", callback_data="panel_close", style=ButtonStyle.DANGER)])
    return InlineKeyboardMarkup(buttons)

# 1. Command handler
@bot.on_message(filters.command("admin") & filters.private)
async def sudo_panel_command(client, message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        is_owner, perms = True, {}
    else:
        perms = await get_sudo_info(user_id)
        if perms is None:
            return await message.reply("🚫 This command is restricted to admins and sudo users only.")
        is_owner = False
    
    await message.reply(
        "🛡️ **SUDO ADMIN PANEL**\n\nSelect a command below:",
        reply_markup=build_sudo_panel(is_owner, perms)
    )

# 2. Start Menu Button Handler
@bot.on_callback_query(filters.regex("^admin_panel_main$"))
async def start_menu_admin_panel(client, query):
    user_id = query.from_user.id
    
    if user_id == ADMIN_ID:
        is_owner, perms = True, {}
    else:
        perms = await get_sudo_info(user_id)
        if perms is None:
            return await query.answer("Access denied.", show_alert=True)
        is_owner = False
    
    await query.message.edit_text(
        "🛡️ **SUDO ADMIN PANEL**\n\nSelect a command below:",
        reply_markup=build_sudo_panel(is_owner, perms)
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

    # ==================== MAINTENANCE ====================
    if action == "maint":
        is_maint, maint_text = await get_maintenance()
        status = "🟢 ON" if is_maint else "🔴 OFF"
        reason = f"\n📝 **Current Reason:** `{maint_text}`" if is_maint else ""
        
        await query.message.edit_text(
            f"🛠️ **Maintenance Mode**\n\n"
            f"Current Status: **{status}**{reason}\n\n"
            f"Toggle the buttons below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 Turn ON (with reason)", callback_data="maint_on", style=ButtonStyle.DANGER)],
                [InlineKeyboardButton("🔴 Turn OFF (open bot)", callback_data="maint_off", style=ButtonStyle.SUCCESS)],
                [InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]
            ])
        )
        return await query.answer()

    # ==================== BROADCAST ====================
    elif action == "broadcast":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "broadcast"}
        await query.message.edit_text(
            "📢 **Broadcast**\n\n"
            "Please send the message you want to broadcast to all users:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    # ==================== ADD SUDO ====================
    elif action == "addsudo":
        AWAITING_SUDO_INPUT[user_id] = {"target_id": None, "perms": {}}
        await query.message.edit_text(
            "👑 **ADD SUDO USER**\n\n"
            "Please send the **User ID** of the person you want to make Sudo:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    # 🔥 ==================== REMOVE SUDO (NEW BUTTON FLOW) ====================
    elif action == "rmsudo":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "rmsudo_wait_id"}
        await query.message.edit_text(
            "❌ **REMOVE SUDO**\n\n"
            "Send the **User ID** you want to remove from Sudo:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    # ==================== PRICING ====================
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

    # ==================== STATS ====================
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

    # ==================== SUDO LIST ====================
    elif action == "sudolist":
        rows = await list_all_sudos()
        if not rows:
            text = "📋 No sudo users found."
        else:
            text = "📋 **SUDO LIST**\n\n"
            for r in rows:
                on_perms = len([v for v in r[1].values() if v == 1])
                text += f"• `{r[0]}` | Perms: {on_perms}\n"
        return await query.message.edit_text(text, reply_markup=back_btn)

    # ==================== ACTIVE BOTS ====================
    elif action == "active":
        if not ACTIVE_CLIENTS:
            text = "📡 No active userbots."
        else:
            text = "📡 **Active Sessions:**\n\n"
            for uid in list(ACTIVE_CLIENTS.keys()):
                text += f"👤 `{uid}`\n"
        return await query.message.edit_text(text, reply_markup=back_btn)

    # ==================== RESET PLANS ====================
    elif action == "reset_plans":
        await seed_default_plans()
        return await query.message.edit_text(
            "✅ **Plans Reset**\n\nAll 8 default plans have been re-seeded into the database.",
            reply_markup=back_btn
        )

    # ==================== SHIFT PLAN ====================
    elif action == "shift_plan":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "shift_plan_wait_id"}
        await query.message.edit_text("🔄 **Shift Plan**\n\nSend the **User ID** whose plan you want to shift:", reply_markup=back_btn)
        return await query.answer()
        
    # ==================== MANAGE DAYS ====================
    elif action == "manage_days":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "manage_days_wait_id"}
        await query.message.edit_text("⏳ **Manage Days**\n\nSend the **User ID** to manage their subscription days:", reply_markup=back_btn)
        return await query.answer()
        
    # ==================== RESET TRIAL ====================
    elif action == "reset_trial":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "reset_trial_wait_id"}
        await query.message.edit_text("🔁 **Reset Trial**\n\nSend the **User ID** to reset their trial history:", reply_markup=back_btn)
        return await query.answer()

    # 🔥 ==================== PLAN ENQUIRY (NEW) ====================
    elif action == "plan_enquiry":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "plan_enquiry_wait_id"}
        await query.message.edit_text(
            "🔍 **PLAN ENQUIRY**\n\n"
            "Send the **User ID** whose plan you want to check:",
            reply_markup=back_btn
        )
        return await query.answer()

    # 🔥 ==================== BAN (NEW BUTTON FLOW) ====================
    elif action == "ban":
        if not await check_power(user_id, 'ban'):
            return await query.answer("⚠️ You don't have Ban permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "ban_wait_id"}
        await query.message.edit_text(
            "🚫 **BAN USER**\n\n"
            "Send the **User ID** you want to ban:",
            reply_markup=back_btn
        )
        return await query.answer()

    # 🔥 ==================== UNBAN (NEW BUTTON FLOW) ====================
    elif action == "unban":
        if not await check_power(user_id, 'unban'):
            return await query.answer("⚠️ You don't have Unban permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "unban_wait_id"}
        await query.message.edit_text(
            "✅ **UNBAN USER**\n\n"
            "Send the **User ID** you want to unban:",
            reply_markup=back_btn
        )
        return await query.answer()

    # 🔥 ==================== APPROVE PLAN (NEW BUTTON FLOW) ====================
    elif action == "approve":
        if not await check_power(user_id, 'approve'):
            return await query.answer("⚠️ You don't have Approve permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "approve_wait_id"}
        await query.message.edit_text(
            "💳 **APPROVE PLAN**\n\n"
            "Send the **User ID** whose payment you want to approve:",
            reply_markup=back_btn
        )
        return await query.answer()

    # 🔥 ==================== CANCEL PLAN (NEW BUTTON FLOW) ====================
    elif action == "cancel":
        if not await check_power(user_id, 'cancel'):
            return await query.answer("⚠️ You don't have Cancel permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "cancel_wait_id"}
        await query.message.edit_text(
            "📉 **CANCEL PLAN**\n\n"
            "Send the **User ID** whose plan you want to cancel:",
            reply_markup=back_btn
        )
        return await query.answer()

    # 🔥 ==================== USER INFO (NEW BUTTON FLOW) ====================
    elif action == "info":
        if not await check_power(user_id, 'info'):
            return await query.answer("⚠️ You don't have Info permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "info_wait_id"}
        await query.message.edit_text(
            "👤 **USER INFO**\n\n"
            "Send the **User ID** whose info you want to check:",
            reply_markup=back_btn
        )
        return await query.answer()

    elif action == "back":
        AWAITING_SUDO_INPUT.pop(user_id, None)
        AWAITING_PLAN_INPUT.pop(user_id, None)
        AWAITING_ADMIN_INPUT.pop(user_id, None)
        
        if user_id == ADMIN_ID:
            is_owner, perms = True, {}
        else:
            perms = await get_sudo_info(user_id)
            is_owner = False
            
        return await query.message.edit_text(
            "🛡️ **SUDO ADMIN PANEL**\n\nSelect a command below:", 
            reply_markup=build_sudo_panel(is_owner, perms)
        )

# --- Maintenance Quick Toggles (UPDATED with reason) ---
@bot.on_callback_query(filters.regex("^maint_on$"))
async def maint_on_handler(client, query):
    user_id = query.from_user.id
    AWAITING_ADMIN_INPUT[user_id] = {"action": "maint_wait_reason"}
    await query.message.edit_text(
        "📝 **MAINTENANCE ON**\n\n"
        "Please send the **reason** to show to users during maintenance:\n\n"
        "Example: `Adding new modules, back in 30 min!`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_maint", style=ButtonStyle.DANGER)]])
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
# --- SHIFT PLAN & MANAGE DAYS (CALLBACKS) ---
# ============================================================

@bot.on_callback_query(filters.regex(r"^do_shift_(\w+)$"))
async def do_shift_plan(client, query):
    user_id = query.from_user.id
    if user_id not in AWAITING_ADMIN_INPUT: return await query.answer("Session expired.", show_alert=True)
    
    plan_key = query.matches[0].group(1)
    target_id = AWAITING_ADMIN_INPUT[user_id]["target_id"]
    
    plan = await get_plan(plan_key)
    if not plan: return await query.answer("Invalid plan.")
    
    new_expiry = datetime.datetime.now() + datetime.timedelta(days=plan['days'])
    await shift_user_plan(target_id, plan['name'], new_expiry)
    del AWAITING_ADMIN_INPUT[user_id]
    
    await query.message.edit_text(
        f"✅ **Plan Shifted Successfully!**\n\n"
        f"👤 **User:** `{target_id}`\n"
        f"💎 **New Plan:** `{plan['name']}`\n"
        f"⏳ **Expiry:** `{new_expiry.strftime('%Y-%m-%d %H:%M')}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
    )
    await query.answer()

@bot.on_callback_query(filters.regex(r"^mday_(add|deduct)$"))
async def manage_days_action(client, query):
    user_id = query.from_user.id
    if user_id not in AWAITING_ADMIN_INPUT: return await query.answer("Session expired.", show_alert=True)
    
    action_type = query.matches[0].group(1)
    AWAITING_ADMIN_INPUT[user_id]["action"] = f"manage_days_wait_amount_{action_type}"
    
    await query.message.edit_text(
        f"Please send the **number of days** to {action_type.upper()}:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")]])
    )
    await query.answer()

# 🔥 Approve Flow: Plan selection callback
@bot.on_callback_query(filters.regex(r"^appr_sel_(\w+)$"))
async def approve_plan_selected(client, query):
    user_id = query.from_user.id
    if user_id not in AWAITING_ADMIN_INPUT: return await query.answer("Session expired.", show_alert=True)
    
    plan_key = query.matches[0].group(1)
    target_id = AWAITING_ADMIN_INPUT[user_id]["target_id"]
    
    plan = await get_plan(plan_key)
    if not plan: return await query.answer("Invalid plan.")
    
    expiry = await add_subscription(target_id, plan_type=plan['name'], days=plan['days'])
    del AWAITING_ADMIN_INPUT[user_id]
    
    await query.message.edit_text(
        f"✅ **Plan Approved!**\n\n"
        f"👤 **User:** `{target_id}`\n"
        f"💎 **Plan:** `{plan['name']}`\n"
        f"⏳ **Days:** `{plan['days']}`\n"
        f"📅 **Expiry:** `{expiry.strftime('%Y-%m-%d %H:%M')}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back")]])
    )
    
    try:
        await bot.send_message(
            target_id,
            f"🎉 **Premium Activated: {plan['name']}**\n\n"
            f"Access granted for **{plan['days']} days**.\n\n"
            "Go to /modules and start your bot now!"
        )
    except: pass
    await query.answer()

# 🔥 Confirm Cancel Plan
@bot.on_callback_query(filters.regex(r"^do_cancel_(\d+)$"))
async def do_cancel_plan(client, query):
    user_id = query.from_user.id
    target_id = int(query.matches[0].group(1))
    
    await cancel_subscription(target_id)
    if target_id in ACTIVE_CLIENTS: 
        await SessionManager.stop_userbot(target_id)
    
    AWAITING_ADMIN_INPUT.pop(user_id, None)
    await query.message.edit_text(
        f"📉 **Plan Cancelled**\n\n👤 **User:** `{target_id}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back")]])
    )
    await query.answer()

# 🔥 Confirm Remove Sudo
@bot.on_callback_query(filters.regex(r"^do_rmsudo_(\d+)$"))
async def do_remove_sudo(client, query):
    user_id = query.from_user.id
    target_id = int(query.matches[0].group(1))
    
    await remove_sudo(target_id)
    AWAITING_ADMIN_INPUT.pop(user_id, None)
    
    await query.message.edit_text(
        f"❌ **Sudo Removed Successfully!**\n\n👤 **User:** `{target_id}`\n\n"
        f"This user no longer has admin panel access.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back")]])
    )
    await query.answer()

# ============================================================
# --- GRANULAR SUDO TOGGLE SYSTEM ---
# ============================================================

TOGGLE_PERMS = [
    ("ban", "🚫 Ban User"), ("unban", "✅ Unban User"),
    ("approve", "💳 Approve Plan"), ("cancel", "📉 Cancel Plan"),
    ("shift", "🔄 Shift Plan"), ("days", "⏳ Manage Days"),
    ("trial", "🔁 Reset Trial"), ("pricing", "💰 Update Pricing"),
    ("broadcast", "📢 Broadcast"), ("maintenance", "🛠️ Maintenance"),
    ("stats", "📊 Stats"), ("sudolist", "📋 Sudo List"),
    ("active", "📡 Active Bots"), ("info", "👤 User Info")
]

def build_toggle_menu(user_id):
    perms = AWAITING_SUDO_INPUT[user_id]["perms"]
    buttons = []
    row = []
    for key, label in TOGGLE_PERMS:
        status = "✅" if perms.get(key) else "❌"
        row.append(InlineKeyboardButton(f"{status} {label}", callback_data=f"sudo_toggle_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    
    buttons.append([InlineKeyboardButton("💾 Save Sudo", callback_data="sudo_save", style=ButtonStyle.PRIMARY)])
    buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)])
    return InlineKeyboardMarkup(buttons)

@bot.on_callback_query(filters.regex(r"^sudo_toggle_(\w+)$"))
async def toggle_sudo_power(client, query):
    user_id = query.from_user.id
    perm_key = query.matches[0].group(1)
    
    if user_id in AWAITING_SUDO_INPUT and "perms" in AWAITING_SUDO_INPUT[user_id]:
        perms = AWAITING_SUDO_INPUT[user_id]["perms"]
        perms[perm_key] = 1 if not perms.get(perm_key) else 0
        await query.message.edit_reply_markup(reply_markup=build_toggle_menu(user_id))
    await query.answer()

@bot.on_callback_query(filters.regex("^sudo_save$"))
async def save_sudo_user(client, query):
    user_id = query.from_user.id
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id]["target_id"]:
        data = AWAITING_SUDO_INPUT[user_id]
        target_id = data["target_id"]
        perms = data["perms"]
        
        await add_sudo(target_id, perms)
        del AWAITING_SUDO_INPUT[user_id]
        
        on_perms = len([v for v in perms.values() if v == 1])
        await query.message.edit_text(
            f"✅ **Sudo Saved Successfully!**\n\n"
            f"👤 **User ID:** `{target_id}`\n"
            f"🔓 **Active Permissions:** `{on_perms}`\n\n"
            f"This user will now see an Admin Panel based on these permissions.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
        )
    await query.answer()

# --- Pricing plan selection ---
@bot.on_callback_query(filters.regex(r"^price_sel_(\w+)$"))
async def price_plan_selected(client, query):
    if query.from_user.id != ADMIN_ID and not await check_power(query.from_user.id, 'pricing'):
        return await query.answer("Access denied. 'Pricing' power required.", show_alert=True)
    
    plan_key = query.matches[0].group(1)
    AWAITING_PLAN_INPUT[query.from_user.id] = {"action": "price", "plan_key": plan_key}
    
    await query.message.edit_text(
        f"💰 **Update Price: `{plan_key}`**\n\n"
        f"Please send the **new price in INR** (numbers only):\nExample: `20`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="panel_pricing", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# ============================================================
# --- SINGLE TEXT INPUT HANDLER (ALL FLOWS) ---
# ============================================================
@bot.on_message(filters.private & filters.text & ~filters.photo & ~filters.command(["start", "admin", "plan", "modules", "help", "commands"]), group=0)
async def handle_admin_inputs(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # ============ 1. HANDLE SUDO USER ID INPUT ============
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id].get("target_id") is None:
        if text.startswith('/'): return
        try:
            target_id = int(text)
        except:
            return await message.reply("❌ Invalid ID. Please send a numeric Telegram ID.")
        
        AWAITING_SUDO_INPUT[user_id]["target_id"] = target_id
        
        await message.reply(
            f"👤 **Target User ID:** `{target_id}`\n\n"
            "Toggle the permissions you want to give to this user, then click Save:\n"
            "✅ = ON | ❌ = OFF",
            reply_markup=build_toggle_menu(user_id)
        )
        return

    # ============ 2. HANDLE ADMIN FLOWS ============
    if user_id in AWAITING_ADMIN_INPUT:
        state = AWAITING_ADMIN_INPUT[user_id]
        action = state.get("action")

        # -------- BROADCAST --------
        if action == "broadcast":
            msg = text
            status_msg = await message.reply("📣 Broadcasting to all users...")
            cursor = db["users"].find({}, {"user_id": 1})
            done, failed = 0, 0
            async for user in cursor:
                try:
                    await bot.send_message(user["user_id"], msg)
                    done += 1
                    await asyncio.sleep(0.3)
                except: failed += 1
            
            del AWAITING_ADMIN_INPUT[user_id]
            await status_msg.edit_text(
                f"✅ **Broadcast Finished!**\n\n👤 **Sent to:** `{done}` users\n❌ **Failed:** `{failed}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- MAINTENANCE REASON --------
        elif action == "maint_wait_reason":
            await set_maintenance("on", text)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"✅ **Maintenance Mode ON**\n\n"
                f"📝 **Reason shown to users:**\n`{text}`\n\n"
                f"Bot is now locked for all non-admin users.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- BAN: WAIT FOR ID --------
        elif action == "ban_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            state["target_id"] = target_id
            state["action"] = "ban_wait_reason"
            await message.reply(
                f"👤 **User to Ban:** `{target_id}`\n\n"
                f"Now send the **reason** for banning this user:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
            )
            return

        # -------- BAN: WAIT FOR REASON --------
        elif action == "ban_wait_reason":
            target_id = state["target_id"]
            reason = text
            
            await ban_user(target_id, reason)
            if target_id in ACTIVE_CLIENTS: 
                await SessionManager.stop_userbot(target_id)
            
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"🚫 **User Banned Successfully!**\n\n"
                f"👤 **User:** `{target_id}`\n"
                f"📝 **Reason:** {reason}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- UNBAN --------
        elif action == "unban_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            ban_info = await get_ban_info(target_id)
            if not ban_info:
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"ℹ️ **User `{target_id}` is not banned.**\n\nNo action taken.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            
            await unban_user(target_id)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"✅ **User Unbanned Successfully!**\n\n"
                f"👤 **User:** `{target_id}`\n"
                f"📝 **Previous Reason:** {ban_info[1]}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- REMOVE SUDO --------
        elif action == "rmsudo_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            info = await get_sudo_info(target_id)
            if info is None:
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"ℹ️ **User `{target_id}` is not a Sudo user.**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            
            on_perms = len([v for v in info.values() if v == 1])
            state["target_id"] = target_id
            
            await message.reply(
                f"👤 **Target Sudo:** `{target_id}`\n"
                f"🔓 **Active Permissions:** `{on_perms}`\n\n"
                f"Are you sure you want to remove this user from Sudo?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, Remove", callback_data=f"do_rmsudo_{target_id}", style=ButtonStyle.DANGER)],
                    [InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]
                ])
            )
            return

        # -------- PLAN ENQUIRY --------
        elif action == "plan_enquiry_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            # Get user data
            status, time_left = await get_sub_info(target_id)
            sub = await get_active_sub(target_id)
            claimed = await has_claimed_trial(target_id)
            is_banned_status = await is_banned(target_id)
            sudo_info = await get_sudo_info(target_id)
            
            plan_name = sub.get('plan', 'None') if sub else 'None'
            expiry_str = sub['expiry_date'].strftime('%Y-%m-%d %H:%M') if sub else 'N/A'
            
            # Time left calculation
            if status == "Active" and time_left:
                days = time_left.days
                hours, rem = divmod(time_left.seconds, 3600)
                mins, _ = divmod(rem, 60)
                time_left_str = f"{days}d {hours}h {mins}m"
            else:
                time_left_str = "N/A"
            
            del AWAITING_ADMIN_INPUT[user_id]
            
            await message.reply(
                f"🔍 **PLAN ENQUIRY**\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User ID:** `{target_id}`\n"
                f"💎 **Plan:** `{plan_name}`\n"
                f"📊 **Status:** `{status}`\n"
                f"⏳ **Time Left:** `{time_left_str}`\n"
                f"📅 **Expiry Date:** `{expiry_str}`\n"
                f"🎁 **Trial:** `{'Claimed' if claimed else 'Available'}`\n"
                f"🚫 **Banned:** `{'Yes' if is_banned_status else 'No'}`\n"
                f"🛡️ **Sudo:** `{'Yes' if sudo_info else 'No'}`\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- USER INFO --------
        elif action == "info_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            status, time_left = await get_sub_info(target_id)
            claimed = await has_claimed_trial(target_id)
            del AWAITING_ADMIN_INPUT[user_id]
            
            await message.reply(
                f"👤 **Info:** `{target_id}`\n"
                f"🎁 Trial: `{'Claimed' if claimed else 'Available'}`\n"
                f"💳 Plan: `{status}`\n"
                f"⏳ Left: `{time_left}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="panel_back")]])
            )
            return

        # -------- APPROVE: WAIT FOR ID --------
        elif action == "approve_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            status, _ = await get_sub_info(target_id)
            if status == "Active":
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"⚠️ **User `{target_id}` already has an active plan!**\n\n"
                    f"Cancel it first or use Shift Plan.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            
            state["target_id"] = target_id
            
            plans = await get_all_plans()
            buttons = []
            row = []
            for p in plans:
                row.append(InlineKeyboardButton(
                    f"{p['name']} ({p['days']}d) ₹{p['price']}", 
                    callback_data=f"appr_sel_{p['plan_key']}"
                ))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
            buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")])
            
            await message.reply(
                f"👤 **User:** `{target_id}`\n\n"
                f"Select the **Plan** to approve:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # -------- CANCEL: WAIT FOR ID --------
        elif action == "cancel_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            status, _ = await get_sub_info(target_id)
            if status != "Active":
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"ℹ️ **User `{target_id}` has no active plan.**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            
            state["target_id"] = target_id
            await message.reply(
                f"👤 **User:** `{target_id}`\n"
                f"💳 **Current Plan:** `{status}`\n\n"
                f"Are you sure you want to cancel?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, Cancel", callback_data=f"do_cancel_{target_id}", style=ButtonStyle.DANGER)],
                    [InlineKeyboardButton("🔙 No", callback_data="panel_back", style=ButtonStyle.PRIMARY)]
                ])
            )
            return

        # -------- SHIFT PLAN: WAIT FOR ID --------
        elif action == "shift_plan_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            sub = await get_active_sub(target_id)
            current_plan = sub['plan'] if sub else "None"
            state["target_id"] = target_id
            state["action"] = "none"
            
            plans = await get_all_plans()
            buttons = []
            row = []
            for p in plans:
                row.append(InlineKeyboardButton(f"{p['name']} ({p['days']}d)", callback_data=f"do_shift_{p['plan_key']}", style=ButtonStyle.PRIMARY))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)
            buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")])

            await message.reply(
                f"👤 User: `{target_id}`\nCurrent Plan: `{current_plan}`\n\nSelect the **New Plan** to shift to:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
            
        # -------- MANAGE DAYS: WAIT FOR ID --------
        elif action == "manage_days_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            sub = await get_active_sub(target_id)
            if not sub: return await message.reply("❌ User has no active plan.")
            
            state["target_id"] = target_id
            state["action"] = "none"
            
            rem = sub["expiry_date"] - datetime.datetime.now()
            days_left = rem.days
            
            await message.reply(
                f"👤 **User:** `{target_id}`\n"
                f"💎 **Plan:** `{sub['plan']}`\n"
                f"⏳ **Days Left:** `{days_left}`\n\n"
                f"Select an action:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Days", callback_data="mday_add", style=ButtonStyle.SUCCESS),
                     InlineKeyboardButton("➖ Deduct Days", callback_data="mday_deduct", style=ButtonStyle.DANGER)],
                    [InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")]
                ])
            )
            return
            
        elif action.startswith("manage_days_wait_amount_"):
            try: days = int(text)
            except: return await message.reply("❌ Invalid number.")
            
            target_id = state["target_id"]
            is_add = action.endswith("_add")
            sub = await get_active_sub(target_id)
            
            if not sub: return await message.reply("❌ User has no active plan.")
            
            if is_add:
                new_expiry = sub["expiry_date"] + datetime.timedelta(days=days)
            else:
                new_expiry = sub["expiry_date"] - datetime.timedelta(days=days)
                
            await set_sub_expiry(target_id, new_expiry)
            del AWAITING_ADMIN_INPUT[user_id]
            
            await message.reply(
                f"✅ **Days {'Added' if is_add else 'Deducted'} Successfully!**\n\n"
                f"👤 **User:** `{target_id}`\n"
                f"📅 **New Expiry:** `{new_expiry.strftime('%Y-%m-%d %H:%M')}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
            )
            return

        # -------- RESET TRIAL --------
        elif action == "reset_trial_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            
            await reset_user_trial(target_id)
            del AWAITING_ADMIN_INPUT[user_id]
            
            await message.reply(
                f"✅ **Trial Reset Successfully!**\n\n"
                f"👤 **User:** `{target_id}`\n"
                f"They can now claim the free trial again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
            )
            return

    # ============ 3. HANDLE PRICE INPUT ============
    if user_id in AWAITING_PLAN_INPUT:
        state = AWAITING_PLAN_INPUT[user_id]
        if state["action"] != "price": return
        
        try:
            new_price = int(text)
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
# --- SUDO MANAGEMENT COMMANDS (BACKUP - Owner Only) ---
# ============================================================

@bot.on_message(filters.command("addsudo") & filters.private)
async def add_sudo_handler(client, message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 3:
        return await message.reply("❌ Usage: `/addsudo <user_id> <json_perms>`")
    try:
        uid = int(args[1])
        perms = json.loads(args[2])
        await add_sudo(uid, perms)
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
        on_perms = len([v for v in r[1].values() if v == 1])
        msg += f"👤 `{r[0]}` | Perms: {on_perms}\n"
    await message.reply(msg)

# ============================================================
# --- OTHER COMMANDS (backup) ---
# ============================================================

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
    if not await check_power(message.from_user.id, 'unban'): return
    args = message.text.split()
    if len(args) != 2: return await message.reply("❌ Usage: `/unban <user_id>`")
    user_id = int(args[1])
    await unban_user(user_id)
    await message.reply(f"✅ **User Unbanned:** `{user_id}`")

@bot.on_message(filters.command("logout") & filters.private)
async def logout_handler(client, message):
    if not await check_power(message.from_user.id, 'ban'): return
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

@bot.on_message(filters.command("approve") & filters.private)
async def manual_approve(client, message):
    if not await check_power(message.from_user.id, 'approve'): return
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
    if not await check_power(message.from_user.id, 'cancel'): return
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

@bot.on_message(filters.command("active") & filters.private)
async def active_sessions(client, message):
    if not await check_power(message.from_user.id, 'active'): return
    if not ACTIVE_CLIENTS: return await message.reply("No active userbots.")
    msg = "🚀 **Active Sessions:**\n\n"
    for uid in list(ACTIVE_CLIENTS.keys()):
        msg += f"👤 `{uid}`\n"
    await message.reply(msg)

@bot.on_message(filters.command("stats") & filters.private)
async def bot_stats(client, message):
    if not await check_power(message.from_user.id, 'stats'): return
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
    if not await check_power(message.from_user.id, 'info'): return
    args = message.text.split()
    if len(args) != 2: return await message.reply("❌ Usage: `/info <user_id>`")
    user_id = int(args[1])
    status, time_left = await get_sub_info(user_id)
    claimed = await has_claimed_trial(user_id)
    await message.reply(f"👤 **Info:** `{user_id}`\n🎁 Trial: `{'Claimed' if claimed else 'Available'}`\n💳 Plan: `{status}`\n⏳ Left: `{time_left}`")

@bot.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(client, message):
    if not await check_power(message.from_user.id, 'broadcast'): return
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
    if message.from_user.id != ADMIN_ID: return
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

@bot.on_message(filters.command("toggleplan") & filters.private)
async def toggle_plan(client, message):
    if not await check_power(message.from_user.id, 'pricing'): return
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

@bot.on_message(filters.command("sudohelp") & filters.private)
async def sudo_help(client, message):
    if not await is_staff(message.from_user.id): return
    
    powers = await get_sudo_info(message.from_user.id)
    is_owner = (message.from_user.id == ADMIN_ID)
    
    help_msg = "🛡️ **Empire Admin Control Center**\n\n"
    help_msg += "Use `/admin` for the **Button Panel** (recommended).\n\n"
    help_msg += "**Commands (backup):**\n"
    
    if is_owner:
        help_msg += "👑 **Owner:**\n"
        help_msg += "• `/addsudo <ID> <JSON>`\n"
        help_msg += "• `/rmsudo <ID>`\n"
        help_msg += "• `/sudolist`\n"
        help_msg += "• `/transfer <From> <To>`\n"
        help_msg += "• `/maintenance <on/off> <msg>`\n"
        help_msg += "• `/testmode <name> on/off`\n"
        help_msg += "• `/getdb`\n\n"
    
    await message.reply(help_msg)

@bot.on_message(filters.command(["active_plans", "activeplans"]) & filters.private)
async def active_plans_report(client, message):
    if not await check_power(message.from_user.id, 'stats'): return
    status_msg = await message.reply("⏳ Generating report...")
    cursor = db["subscriptions"].find({"status": "active"})
    report = "EMPIRE ACTIVE PLANS\n" + "="*20 + "\n"
    async for sub in cursor:
        report += f"ID: {sub['user_id']} | Plan: {sub['plan']} | Expiry: {sub['expiry_date']}\n"
    with open("plans.txt", "w") as f: f.write(report)
    await bot.send_document(message.chat.id, "plans.txt", caption="📊 **Plan Report**")
    os.remove("plans.txt")
    await status_msg.delete()
