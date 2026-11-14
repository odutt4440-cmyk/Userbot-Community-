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
AWAITING_ADMIN_INPUT = {}

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

    row8 = []
    if has("info"): row8.append(InlineKeyboardButton("🔍 Plan Enquiry", callback_data="panel_plan_enquiry", style=ButtonStyle.PRIMARY))
    if has("ban"): row8.append(InlineKeyboardButton("🚪 Logout User", callback_data="panel_logout", style=ButtonStyle.DANGER))
    if row8: buttons.append(row8)

    if is_owner:
        buttons.append([
            InlineKeyboardButton("👑 Add Sudo", callback_data="panel_addsudo", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("❌ Remove Sudo", callback_data="panel_rmsudo", style=ButtonStyle.DANGER)
        ])
        buttons.append([
            InlineKeyboardButton("🔄 Reset Plans", callback_data="panel_reset_plans", style=ButtonStyle.DANGER),
            InlineKeyboardButton("🔀 Toggle Plan", callback_data="panel_toggle_plan", style=ButtonStyle.PRIMARY)
        ])
        buttons.append([
            InlineKeyboardButton("🧪 Test Mode", callback_data="panel_testmode", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("♻️ Transfer Plan", callback_data="panel_transfer", style=ButtonStyle.PRIMARY)
        ])
        buttons.append([
            InlineKeyboardButton("💾 DB Backup", callback_data="panel_getdb", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("📊 Active Plans", callback_data="panel_active_plans", style=ButtonStyle.PRIMARY)
        ])

    buttons.append([
        InlineKeyboardButton("❓ Help", callback_data="panel_sudohelp", style=ButtonStyle.PRIMARY),
        InlineKeyboardButton("❌ Close", callback_data="panel_close", style=ButtonStyle.DANGER)
    ])
    return InlineKeyboardMarkup(buttons)

# ============================================================
# --- ONLY COMMAND: /admin (entry point) ---
# ============================================================
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

# Start menu button handler
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

# ============================================================
# --- MAIN PANEL CALLBACK (ALL BUTTONS) ---
# ============================================================
@bot.on_callback_query(filters.regex(r"^panel_"))
async def sudo_panel_callback(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID and not await is_staff(user_id):
        return await query.answer("Access denied.", show_alert=True)
    
    is_owner = (user_id == ADMIN_ID)
    perms = {} if is_owner else (await get_sudo_info(user_id) or {})
    def has(p): return is_owner or perms.get(p, 0) == 1
    
    action = query.data.replace("panel_", "")
    
    if action == "close":
        return await query.message.delete()
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])

    # ========== MAINTENANCE ==========
    if action == "maint":
        is_maint, maint_text = await get_maintenance()
        status = "🟢 ON" if is_maint else "🔴 OFF"
        reason = f"\n📝 **Current Reason:** `{maint_text}`" if is_maint else ""
        
        await query.message.edit_text(
            f"🛠️ **Maintenance Mode**\n\nCurrent Status: **{status}**{reason}\n\nToggle below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🟢 Turn ON (with reason)", callback_data="maint_on", style=ButtonStyle.DANGER)],
                [InlineKeyboardButton("🔴 Turn OFF (open bot)", callback_data="maint_off", style=ButtonStyle.SUCCESS)],
                [InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]
            ])
        )
        return await query.answer()

    # ========== BROADCAST ==========
    elif action == "broadcast":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "broadcast"}
        await query.message.edit_text(
            "📢 **Broadcast**\n\nSend the message to broadcast to all users:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    # ========== ADD SUDO ==========
    elif action == "addsudo":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        AWAITING_SUDO_INPUT[user_id] = {"target_id": None, "perms": {}}
        await query.message.edit_text(
            "👑 **ADD SUDO USER**\n\nSend the **User ID** to make Sudo:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
        )
        return await query.answer()

    # ========== REMOVE SUDO ==========
    elif action == "rmsudo":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "rmsudo_wait_id"}
        await query.message.edit_text(
            "❌ **REMOVE SUDO**\n\nSend the **User ID** to remove from Sudo:",
            reply_markup=back_btn
        )
        return await query.answer()

    # ========== PRICING ==========
    elif action == "pricing":
        plans = await get_all_plans()
        if not plans: return await query.message.edit_text("⚠️ No plans.", reply_markup=back_btn)
        buttons = []
        row = []
        for p in plans:
            row.append(InlineKeyboardButton(f"{p['plan_key']} - ₹{p['price']}", callback_data=f"price_sel_{p['plan_key']}", style=ButtonStyle.PRIMARY))
            if len(row) == 2:
                buttons.append(row); row = []
        if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)])
        return await query.message.edit_text("💰 **UPDATE PRICING**\n\nSelect a plan:", reply_markup=InlineKeyboardMarkup(buttons))

    # ========== STATS ==========
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

    # ========== SUDO LIST ==========
    elif action == "sudolist":
        rows = await list_all_sudos()
        text = "📋 **SUDO LIST**\n\n" if rows else "📋 No sudo users found."
        if rows:
            for r in rows:
                on_perms = len([v for v in r[1].values() if v == 1])
                text += f"• `{r[0]}` | Perms: {on_perms}\n"
        return await query.message.edit_text(text, reply_markup=back_btn)

    # ========== ACTIVE BOTS ==========
    elif action == "active":
        text = "📡 **Active Sessions:**\n\n" if ACTIVE_CLIENTS else "📡 No active userbots."
        if ACTIVE_CLIENTS:
            for uid in list(ACTIVE_CLIENTS.keys()): text += f"👤 `{uid}`\n"
        return await query.message.edit_text(text, reply_markup=back_btn)

    # ========== RESET PLANS ==========
    elif action == "reset_plans":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        await seed_default_plans()
        return await query.message.edit_text("✅ **Plans Reset**\n\nAll 8 default plans re-seeded.", reply_markup=back_btn)

    # ========== TOGGLE PLAN ==========
    elif action == "toggle_plan":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        plans = await get_all_plans()
        buttons = []
        for p in plans:
            status = "🟢" if p.get("active", True) else "🔴"
            buttons.append([InlineKeyboardButton(f"{status} {p['plan_key']} - {p['name']}", callback_data=f"togp_{p['plan_key']}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="panel_back")])
        return await query.message.edit_text(
            "🔀 **TOGGLE PLANS**\n\nClick a plan to enable/disable:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    # ========== TEST MODE ==========
    elif action == "testmode":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "testmode_wait_module"}
        await query.message.edit_text(
            "🧪 **TEST MODE**\n\nSend the **module name** (e.g., `whisper`, `tagall`):",
            reply_markup=back_btn
        )
        return await query.answer()

    # ========== TRANSFER PLAN ==========
    elif action == "transfer":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "transfer_wait_from"}
        await query.message.edit_text(
            "♻️ **TRANSFER PLAN**\n\nSend the **FROM user ID**:",
            reply_markup=back_btn
        )
        return await query.answer()

    # ========== DB BACKUP ==========
    elif action == "getdb":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        await query.answer("Exporting...")
        try:
            data = {}
            for coll in ["users", "subscriptions", "banned_users", "plans"]:
                cursor = db[coll].find({})
                data[coll] = [doc async for doc in cursor]
            with open("backup.json", "w", encoding="utf-8") as f:
                json.dump(data, f, default=str, indent=2)
            await bot.send_document(query.message.chat.id, "backup.json", caption="📁 **Cloud Backup**")
            os.remove("backup.json")
            await query.message.edit_text("✅ **Backup sent above.**", reply_markup=back_btn)
        except Exception as e:
            await query.message.edit_text(f"❌ Error: {e}", reply_markup=back_btn)
        return

    # ========== ACTIVE PLANS REPORT ==========
    elif action == "active_plans":
        if not is_owner: return await query.answer("Owner only.", show_alert=True)
        await query.answer("Generating...")
        cursor = db["subscriptions"].find({"status": "active"})
        report = "EMPIRE ACTIVE PLANS\n" + "="*20 + "\n"
        async for sub in cursor:
            report += f"ID: {sub['user_id']} | Plan: {sub['plan']} | Expiry: {sub['expiry_date']}\n"
        with open("plans.txt", "w") as f: f.write(report)
        await bot.send_document(query.message.chat.id, "plans.txt", caption="📊 **Plan Report**")
        os.remove("plans.txt")
        await query.message.edit_text("✅ **Report sent above.**", reply_markup=back_btn)
        return

    # ========== SUDO HELP ==========
    elif action == "sudohelp":
        help_text = (
            "🛡️ **ADMIN PANEL GUIDE**\n\n"
            "**All actions via buttons. No commands needed!**\n\n"
            "• 🚫 **Ban/Unban** — Ban user with reason\n"
            "• 💳 **Approve/Cancel** — Manage user plans\n"
            "• 🔄 **Shift/Manage Days** — Change plan duration\n"
            "• 🔁 **Reset Trial** — User can claim trial again\n"
            "• 💰 **Pricing** — Update plan prices\n"
            "• 📢 **Broadcast** — Send message to all\n"
            "• 🛠️ **Maintenance** — Lock bot with reason\n"
            "• 📊 **Stats** — Bot statistics\n"
            "• 👤 **User Info** — Check user details\n"
            "• 🔍 **Plan Enquiry** — Detailed plan check\n"
            "• 🚪 **Logout** — End user session\n\n"
            f"👑 **Owner Extra:** Add/Remove Sudo, Reset Plans, Toggle Plan, Test Mode, Transfer, DB Backup, Active Plans"
        )
        return await query.message.edit_text(help_text, reply_markup=back_btn)

    # ========== SHIFT PLAN ==========
    elif action == "shift_plan":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "shift_plan_wait_id"}
        await query.message.edit_text("🔄 **Shift Plan**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()
        
    # ========== MANAGE DAYS ==========
    elif action == "manage_days":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "manage_days_wait_id"}
        await query.message.edit_text("⏳ **Manage Days**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()
        
    # ========== RESET TRIAL ==========
    elif action == "reset_trial":
        AWAITING_ADMIN_INPUT[user_id] = {"action": "reset_trial_wait_id"}
        await query.message.edit_text("🔁 **Reset Trial**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()

    # ========== PLAN ENQUIRY ==========
    elif action == "plan_enquiry":
        if not has("info"): return await query.answer("No Info permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "plan_enquiry_wait_id"}
        await query.message.edit_text("🔍 **PLAN ENQUIRY**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()

    # ========== BAN ==========
    elif action == "ban":
        if not has("ban"): return await query.answer("No Ban permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "ban_wait_id"}
        await query.message.edit_text("🚫 **BAN USER**\n\nSend the **User ID** to ban:", reply_markup=back_btn)
        return await query.answer()

    # ========== UNBAN ==========
    elif action == "unban":
        if not has("unban"): return await query.answer("No Unban permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "unban_wait_id"}
        await query.message.edit_text("✅ **UNBAN USER**\n\nSend the **User ID** to unban:", reply_markup=back_btn)
        return await query.answer()

    # ========== APPROVE ==========
    elif action == "approve":
        if not has("approve"): return await query.answer("No Approve permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "approve_wait_id"}
        await query.message.edit_text("💳 **APPROVE PLAN**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()

    # ========== CANCEL ==========
    elif action == "cancel":
        if not has("cancel"): return await query.answer("No Cancel permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "cancel_wait_id"}
        await query.message.edit_text("📉 **CANCEL PLAN**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()

    # ========== USER INFO ==========
    elif action == "info":
        if not has("info"): return await query.answer("No Info permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "info_wait_id"}
        await query.message.edit_text("👤 **USER INFO**\n\nSend the **User ID**:", reply_markup=back_btn)
        return await query.answer()

    # ========== LOGOUT USER ==========
    elif action == "logout":
        if not has("ban"): return await query.answer("No Ban permission.", show_alert=True)
        AWAITING_ADMIN_INPUT[user_id] = {"action": "logout_wait_id"}
        await query.message.edit_text("🚪 **LOGOUT USER**\n\nSend the **User ID** to logout their session:", reply_markup=back_btn)
        return await query.answer()

    # ========== BACK ==========
    elif action == "back":
        AWAITING_SUDO_INPUT.pop(user_id, None)
        AWAITING_PLAN_INPUT.pop(user_id, None)
        AWAITING_ADMIN_INPUT.pop(user_id, None)
        
        if is_owner:
            is_o, perms_ = True, {}
        else:
            perms_ = await get_sudo_info(user_id)
            is_o = False
            
        return await query.message.edit_text(
            "🛡️ **SUDO ADMIN PANEL**\n\nSelect a command below:", 
            reply_markup=build_sudo_panel(is_o, perms_)
        )

# ============================================================
# --- MAINTENANCE TOGGLES ---
# ============================================================
@bot.on_callback_query(filters.regex("^maint_on$"))
async def maint_on_handler(client, query):
    user_id = query.from_user.id
    AWAITING_ADMIN_INPUT[user_id] = {"action": "maint_wait_reason"}
    await query.message.edit_text(
        "📝 **MAINTENANCE ON**\n\nSend the **reason** to show to users:\n\nExample: `Adding new modules, back in 30 min!`",
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
# --- TEST MODE CALLBACKS ---
# ============================================================
@bot.on_callback_query(filters.regex("^testmode_on$"))
async def testmode_on_cb(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return await query.answer("Owner only.", show_alert=True)
    if user_id not in AWAITING_ADMIN_INPUT: return await query.answer("Session expired.", show_alert=True)
    module = AWAITING_ADMIN_INPUT[user_id].get("module")
    if not module: return await query.answer("No module set.", show_alert=True)
    await set_module_testing(module, True)
    del AWAITING_ADMIN_INPUT[user_id]
    await query.message.edit_text(
        f"🧪 **Module Locked:** `{module.upper()}`\n\nNow in internal testing mode.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
    )
    await query.answer()

@bot.on_callback_query(filters.regex("^testmode_off$"))
async def testmode_off_cb(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return await query.answer("Owner only.", show_alert=True)
    if user_id not in AWAITING_ADMIN_INPUT: return await query.answer("Session expired.", show_alert=True)
    AWAITING_ADMIN_INPUT[user_id]["action"] = "testmode_wait_msg"
    await query.message.edit_text(
        "📢 **Broadcast Update?**\n\n"
        "Send a message to broadcast, or type `skip` to unlock without broadcast:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")]])
    )
    await query.answer()

# ============================================================
# --- TOGGLE PLAN CALLBACK ---
# ============================================================
@bot.on_callback_query(filters.regex(r"^togp_(\w+)$"))
async def toggle_plan_cb(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return await query.answer("Owner only.", show_alert=True)
    plan_key = query.matches[0].group(1)
    plan = await get_plan(plan_key)
    if not plan: return await query.answer("Invalid plan.", show_alert=True)
    
    new_status = not plan.get("active", True)
    await toggle_plan_active(plan_key, new_status)
    await query.answer(f"Plan {plan_key} → {'🟢 Active' if new_status else '🔴 Inactive'}", show_alert=True)
    
    plans = await get_all_plans()
    buttons = []
    for p in plans:
        status = "🟢" if p.get("active", True) else "🔴"
        buttons.append([InlineKeyboardButton(f"{status} {p['plan_key']} - {p['name']}", callback_data=f"togp_{p['plan_key']}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="panel_back")])
    await query.message.edit_text("🔀 **TOGGLE PLANS**\n\nClick a plan to toggle:", reply_markup=InlineKeyboardMarkup(buttons))

# ============================================================
# --- SHIFT PLAN & MANAGE DAYS ---
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
        f"✅ **Plan Shifted!**\n\n👤 **User:** `{target_id}`\n💎 **New Plan:** `{plan['name']}`\n⏳ **Expiry:** `{new_expiry.strftime('%Y-%m-%d %H:%M')}`",
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
        f"Send the **number of days** to {action_type.upper()}:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")]])
    )
    await query.answer()

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
        f"✅ **Plan Approved!**\n\n👤 **User:** `{target_id}`\n💎 **Plan:** `{plan['name']}`\n⏳ **Days:** `{plan['days']}`\n📅 **Expiry:** `{expiry.strftime('%Y-%m-%d %H:%M')}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
    )
    try:
        await bot.send_message(
            target_id,
            f"🎉 **Premium Activated: {plan['name']}**\n\nAccess granted for **{plan['days']} days**.\n\nGo to /modules and start now!"
        )
    except: pass
    await query.answer()

@bot.on_callback_query(filters.regex(r"^do_cancel_(\d+)$"))
async def do_cancel_plan(client, query):
    user_id = query.from_user.id
    target_id = int(query.matches[0].group(1))
    await cancel_subscription(target_id)
    if target_id in ACTIVE_CLIENTS: await SessionManager.stop_userbot(target_id)
    AWAITING_ADMIN_INPUT.pop(user_id, None)
    await query.message.edit_text(
        f"📉 **Plan Cancelled**\n\n👤 **User:** `{target_id}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
    )
    await query.answer()

@bot.on_callback_query(filters.regex(r"^do_rmsudo_(\d+)$"))
async def do_remove_sudo(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return await query.answer("Owner only.", show_alert=True)
    target_id = int(query.matches[0].group(1))
    await remove_sudo(target_id)
    AWAITING_ADMIN_INPUT.pop(user_id, None)
    await query.message.edit_text(
        f"❌ **Sudo Removed!**\n\n👤 **User:** `{target_id}`\n\nNo longer has admin panel access.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
    )
    await query.answer()

# ============================================================
# --- SUDO TOGGLE SYSTEM ---
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
            buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("💾 Save Sudo", callback_data="sudo_save", style=ButtonStyle.PRIMARY)])
    buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)])
    return InlineKeyboardMarkup(buttons)

@bot.on_callback_query(filters.regex(r"^sudo_toggle_(\w+)$"))
async def toggle_sudo_power(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return await query.answer("Owner only.", show_alert=True)
    perm_key = query.matches[0].group(1)
    if user_id in AWAITING_SUDO_INPUT and "perms" in AWAITING_SUDO_INPUT[user_id]:
        perms = AWAITING_SUDO_INPUT[user_id]["perms"]
        perms[perm_key] = 1 if not perms.get(perm_key) else 0
        await query.message.edit_reply_markup(reply_markup=build_toggle_menu(user_id))
    await query.answer()

@bot.on_callback_query(filters.regex("^sudo_save$"))
async def save_sudo_user(client, query):
    user_id = query.from_user.id
    if user_id != ADMIN_ID: return await query.answer("Owner only.", show_alert=True)
    if user_id in AWAITING_SUDO_INPUT and AWAITING_SUDO_INPUT[user_id]["target_id"]:
        data = AWAITING_SUDO_INPUT[user_id]
        target_id = data["target_id"]
        perms = data["perms"]
        await add_sudo(target_id, perms)
        del AWAITING_SUDO_INPUT[user_id]
        on_perms = len([v for v in perms.values() if v == 1])
        await query.message.edit_text(
            f"✅ **Sudo Saved!**\n\n👤 **User ID:** `{target_id}`\n🔓 **Active Permissions:** `{on_perms}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
        )
    await query.answer()

@bot.on_callback_query(filters.regex(r"^price_sel_(\w+)$"))
async def price_plan_selected(client, query):
    if query.from_user.id != ADMIN_ID and not await check_power(query.from_user.id, 'pricing'):
        return await query.answer("Access denied. 'Pricing' required.", show_alert=True)
    plan_key = query.matches[0].group(1)
    AWAITING_PLAN_INPUT[query.from_user.id] = {"action": "price", "plan_key": plan_key}
    await query.message.edit_text(
        f"💰 **Update Price: `{plan_key}`**\n\nSend the **new price in INR**:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_pricing", style=ButtonStyle.DANGER)]])
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
        if user_id != ADMIN_ID: return
        if text.startswith('/'): return
        try:
            target_id = int(text)
        except:
            return await message.reply("❌ Invalid ID. Please send a numeric Telegram ID.")
        AWAITING_SUDO_INPUT[user_id]["target_id"] = target_id
        await message.reply(
            f"👤 **Target User ID:** `{target_id}`\n\nToggle permissions then click Save:\n✅ = ON | ❌ = OFF",
            reply_markup=build_toggle_menu(user_id)
        )
        return

    # ============ 2. HANDLE ADMIN FLOWS ============
    if user_id in AWAITING_ADMIN_INPUT:
        state = AWAITING_ADMIN_INPUT[user_id]
        action = state.get("action")

        # Ignore commands except during broadcast
        if text.startswith('/') and action != "broadcast":
            return

        # -------- BROADCAST --------
        if action == "broadcast":
            status_msg = await message.reply("📣 Broadcasting to all users...")
            cursor = db["users"].find({}, {"user_id": 1})
            done, failed = 0, 0
            async for user in cursor:
                try:
                    await bot.send_message(user["user_id"], text)
                    done += 1
                    await asyncio.sleep(0.3)
                except: failed += 1
            del AWAITING_ADMIN_INPUT[user_id]
            await status_msg.edit_text(
                f"✅ **Broadcast Finished!**\n\n👤 **Sent to:** `{done}`\n❌ **Failed:** `{failed}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- MAINTENANCE REASON --------
        elif action == "maint_wait_reason":
            await set_maintenance("on", text)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"✅ **Maintenance Mode ON**\n\n📝 **Reason:** `{text}`\n\nBot is now locked for non-admin users.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back", style=ButtonStyle.PRIMARY)]])
            )
            return

        # -------- TEST MODE: MODULE --------
        elif action == "testmode_wait_module":
            module_name = text.lower().strip()
            state["module"] = module_name
            state["action"] = "none"
            await message.reply(
                f"📦 **Module:** `{module_name}`\n\nChoose status:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🧪 Lock (Testing)", callback_data="testmode_on", style=ButtonStyle.DANGER)],
                    [InlineKeyboardButton("🌍 Unlock (Public)", callback_data="testmode_off", style=ButtonStyle.SUCCESS)],
                    [InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")]
                ])
            )
            return

        # -------- TEST MODE: BROADCAST MSG --------
        elif action == "testmode_wait_msg":
            module = state["module"]
            await set_module_testing(module, False)
            del AWAITING_ADMIN_INPUT[user_id]
            
            if text.lower() == "skip":
                await message.reply(
                    f"🌍 **Module Unlocked:** `{module.upper()}`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            else:
                status_msg = await message.reply("📣 Broadcasting update...")
                done, failed = 0, 0
                cursor = db["users"].find({}, {"user_id": 1})
                broadcast_text = (
                    f"🚀 **New Module Update: {module.upper()}**\n\n"
                    f"{text}\n\n"
                    f"👉 Use /modules to check it out!"
                )
                async for user in cursor:
                    try:
                        await bot.send_message(user["user_id"], broadcast_text)
                        done += 1
                        await asyncio.sleep(0.3)
                    except: failed += 1
                await status_msg.edit_text(
                    f"🌍 **Unlocked & Broadcast Sent!**\n\n📦 **Module:** `{module.upper()}`\n👤 **Sent:** `{done}` | ❌ **Failed:** `{failed}`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            return

        # -------- TRANSFER: FROM --------
        elif action == "transfer_wait_from":
            try: from_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            state["from_id"] = from_id
            state["action"] = "transfer_wait_to"
            await message.reply(
                f"♻️ **FROM:** `{from_id}`\n\nNow send the **TO user ID**:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")]])
            )
            return

        # -------- TRANSFER: TO --------
        elif action == "transfer_wait_to":
            try: to_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            from_id = state["from_id"]
            success, msg = await transfer_subscription(from_id, to_id)
            del AWAITING_ADMIN_INPUT[user_id]
            if success:
                await message.reply(
                    f"✅ **Transferred!**\n\n📤 From: `{from_id}`\n📥 To: `{to_id}`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            else:
                await message.reply(f"❌ **Error:** {msg}")
            return

        # -------- LOGOUT --------
        elif action == "logout_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            if target_id in ACTIVE_CLIENTS:
                try:
                    await ACTIVE_CLIENTS[target_id]["client"].log_out()
                    del ACTIVE_CLIENTS[target_id]
                except: pass
            await remove_user_session(target_id)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"✅ **Logged Out:** `{target_id}`\nSession terminated.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
            )
            return

        # -------- BAN: ID --------
        elif action == "ban_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            state["target_id"] = target_id
            state["action"] = "ban_wait_reason"
            await message.reply(
                f"👤 **User:** `{target_id}`\n\nNow send the **reason** for ban:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="panel_back", style=ButtonStyle.DANGER)]])
            )
            return

        # -------- BAN: REASON --------
        elif action == "ban_wait_reason":
            target_id = state["target_id"]
            await ban_user(target_id, text)
            if target_id in ACTIVE_CLIENTS: await SessionManager.stop_userbot(target_id)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"🚫 **User Banned!**\n\n👤 **User:** `{target_id}`\n📝 **Reason:** {text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
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
                    f"ℹ️ User `{target_id}` is not banned.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            await unban_user(target_id)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"✅ **User Unbanned!**\n\n👤 `{target_id}`\n📝 Previous: {ban_info[1]}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
            )
            return

        # -------- REMOVE SUDO: ID --------
        elif action == "rmsudo_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            info = await get_sudo_info(target_id)
            if info is None:
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"ℹ️ `{target_id}` is not a Sudo user.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            on_perms = len([v for v in info.values() if v == 1])
            state["target_id"] = target_id
            await message.reply(
                f"👤 **Sudo:** `{target_id}`\n🔓 **Active Perms:** `{on_perms}`\n\nConfirm removal?",
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
            status, time_left = await get_sub_info(target_id)
            sub = await get_active_sub(target_id)
            claimed = await has_claimed_trial(target_id)
            ban_st = await is_banned(target_id)
            sudo_info = await get_sudo_info(target_id)
            plan_name = sub.get('plan', 'None') if sub else 'None'
            expiry_str = sub['expiry_date'].strftime('%Y-%m-%d %H:%M') if sub else 'N/A'
            if status == "Active" and time_left:
                days = time_left.days
                hours, rem = divmod(time_left.seconds, 3600)
                mins, _ = divmod(rem, 60)
                time_left_str = f"{days}d {hours}h {mins}m"
            else:
                time_left_str = "N/A"
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"🔍 **PLAN ENQUIRY**\n━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User ID:** `{target_id}`\n"
                f"💎 **Plan:** `{plan_name}`\n"
                f"📊 **Status:** `{status}`\n"
                f"⏳ **Time Left:** `{time_left_str}`\n"
                f"📅 **Expiry:** `{expiry_str}`\n"
                f"🎁 **Trial:** `{'Claimed' if claimed else 'Available'}`\n"
                f"🚫 **Banned:** `{'Yes' if ban_st else 'No'}`\n"
                f"🛡️ **Sudo:** `{'Yes' if sudo_info else 'No'}`\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
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
                f"👤 **Info:** `{target_id}`\n🎁 Trial: `{'Claimed' if claimed else 'Available'}`\n💳 Plan: `{status}`\n⏳ Left: `{time_left}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
            )
            return

        # -------- APPROVE: ID --------
        elif action == "approve_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            status, _ = await get_sub_info(target_id)
            if status == "Active":
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"⚠️ User `{target_id}` already has an active plan!\n\nCancel first or use Shift Plan.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            state["target_id"] = target_id
            plans = await get_all_plans()
            buttons = []
            row = []
            for p in plans:
                row.append(InlineKeyboardButton(f"{p['name']} ({p['days']}d) ₹{p['price']}", callback_data=f"appr_sel_{p['plan_key']}"))
                if len(row) == 2:
                    buttons.append(row); row = []
            if row: buttons.append(row)
            buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")])
            await message.reply(
                f"👤 **User:** `{target_id}`\n\nSelect the **Plan**:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

        # -------- CANCEL: ID --------
        elif action == "cancel_wait_id":
            try: target_id = int(text)
            except: return await message.reply("❌ Invalid ID.")
            status, _ = await get_sub_info(target_id)
            if status != "Active":
                del AWAITING_ADMIN_INPUT[user_id]
                return await message.reply(
                    f"ℹ️ User `{target_id}` has no active plan.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
                )
            state["target_id"] = target_id
            await message.reply(
                f"👤 **User:** `{target_id}`\n💳 **Status:** `{status}`\n\nConfirm cancel?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Yes, Cancel", callback_data=f"do_cancel_{target_id}", style=ButtonStyle.DANGER)],
                    [InlineKeyboardButton("🔙 No", callback_data="panel_back", style=ButtonStyle.PRIMARY)]
                ])
            )
            return

        # -------- SHIFT PLAN: ID --------
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
                    buttons.append(row); row = []
            if row: buttons.append(row)
            buttons.append([InlineKeyboardButton("🔙 Cancel", callback_data="panel_back")])
            await message.reply(
                f"👤 User: `{target_id}`\nCurrent: `{current_plan}`\n\nSelect **New Plan**:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
            
        # -------- MANAGE DAYS: ID --------
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
                f"👤 **User:** `{target_id}`\n💎 **Plan:** `{sub['plan']}`\n⏳ **Days Left:** `{days_left}`\n\nSelect action:",
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
            new_expiry = sub["expiry_date"] + datetime.timedelta(days=days) if is_add else sub["expiry_date"] - datetime.timedelta(days=days)
            await set_sub_expiry(target_id, new_expiry)
            del AWAITING_ADMIN_INPUT[user_id]
            await message.reply(
                f"✅ **Days {'Added' if is_add else 'Deducted'}!**\n\n👤 **User:** `{target_id}`\n📅 **New Expiry:** `{new_expiry.strftime('%Y-%m-%d %H:%M')}`",
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
                f"✅ **Trial Reset!**\n\n👤 **User:** `{target_id}`\nThey can now claim the free trial again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="panel_back")]])
            )
            return

    # ============ 3. PRICE INPUT ============
    if user_id in AWAITING_PLAN_INPUT:
        state = AWAITING_PLAN_INPUT[user_id]
        if state["action"] != "price": return
        try:
            new_price = int(text)
            if new_price < 1: raise ValueError
        except:
            return await message.reply("❌ Invalid. Send a positive number.")
        plan_key = state["plan_key"]
        success = await update_plan_price(plan_key, new_price)
        del AWAITING_PLAN_INPUT[user_id]
        if success:
            await message.reply(
                f"✅ **Price Updated!**\n\nPlan: `{plan_key}`\nNew Price: **₹{new_price}**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Pricing", callback_data="panel_pricing", style=ButtonStyle.PRIMARY)]])
            )
        else:
            await message.reply("⚠️ Failed to update.")
        return
