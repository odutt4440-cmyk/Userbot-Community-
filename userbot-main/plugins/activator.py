import asyncio
import os
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot 
from core.session_manager import SessionManager
from config import ADMIN_ID
from database import (
    is_subscribed, 
    get_user_plan_type, 
    get_owner_logs,
    is_module_in_testing
)

# --- MODULE CATEGORY MAP ---
CATEGORY_MAP = {
    "games": ["wordly", "wordseek", "wordchain", "octopus", "wordle_pro"],
    "fun": ["clone", "afk", "stickers", "reaction", "extra_fun", "raid", "auto_greet", "vc_stream"],
    "management": ["tagger", "stealth", "group_tools", "info_tools", "approver"]
}

# --- KEY MAPPING: Buttons to Backend Sync ---
NAME_MAP = {
    "extra_fun": "extra_fun",
    "raid": "raid",
    "info": "info_tools",
    "group": "group_tools",
    "admin": "group_tools",
    "wordle_pro": "wordle_pro",
    "management": "management",
    "auto_greet": "auto_greet",
    "approver": "approver",
    "vc_stream": "vc_stream"
}

def get_clean_name(data_str):
    """Remove all prefixes from callback data."""
    name = data_str.replace("activate_", "").replace("force_start_", "").replace("stop_", "").replace("start_ub_", "").replace("mod_", "")
    return NAME_MAP.get(name, name)

# --- MAIN ACTIVATION HANDLER ---
@bot.on_callback_query(filters.regex(r"^(activate_|mod_)"))
async def activate_module(client, query):
    user_id = query.from_user.id
    data = query.data
    
    # 🛡️ 1. Valid Plan Check (Active subscription ya trial hona chahiye)
    if not await is_subscribed(user_id):
        return await query.message.edit_text(
            "⚠️ **Premium Access Required**\n\n"
            "You do not have an active plan or trial to use this module. Please buy a plan to continue.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 View Plans", callback_data="pay_now", style=ButtonStyle.PRIMARY)],
                [InlineKeyboardButton("🎁 Claim 24h Trial", callback_data="claim_trial_btn", style=ButtonStyle.SUCCESS)]
            ])
        )

    # 🔍 Clean Target Name
    target_name = get_clean_name(data)

    # 🛡️ 2. UNIVERSAL TESTING LOCK
    if await is_module_in_testing(target_name) and user_id != ADMIN_ID:
        return await query.answer(
            f"🧪 {target_name.upper()} is currently in Internal Testing.\n\nPlease wait for the public rollout!", 
            show_alert=True
        )

    # 🔥 3. LOGIC: PACK vs SINGLE MODULE (Empire vs Standard)
    if "_pack" in data:
        final_load_target = data.replace("mod_", "").replace("activate_", "")
    else:
        plan = await get_user_plan_type(user_id)
        final_load_target = target_name
        
        # Empire/Admin Auto-Upgrade to Folder Pack
        if user_id == ADMIN_ID or "empire" in str(plan).lower():
            for category, modules in CATEGORY_MAP.items():
                if target_name in modules:
                    final_load_target = f"{category}_pack"
                    break

    await query.message.edit_text(f"⏳ **Deploying {'Folder Pack' if '_pack' in final_load_target else 'Module'}...**")
    
    # 🔥 SessionManager call (Yahan Standard/Empire ka logic chalega)
    result_message = await SessionManager.start_userbot(user_id, final_load_target)

    # UI Response
    if "Online" in result_message or "Activated" in result_message:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Stop Session", callback_data=f"stop_{final_load_target}", style=ButtonStyle.DANGER)]
        ])
    elif "Standard Plan Limit" in result_message:
        # Agar standard plan mein limit lagti hai (agar session_manager ne limit lagayi ho)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Stop Current & Start This", callback_data=f"force_start_{final_load_target}", style=ButtonStyle.DANGER)],
            [InlineKeyboardButton("💎 Upgrade to Empire", callback_data="pay_now", style=ButtonStyle.SUCCESS)]
        ])
    else:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="modules_main", style=ButtonStyle.PRIMARY)]
        ])
        
    await query.message.edit_text(result_message, reply_markup=buttons)
    await query.answer()

# --- STOP HANDLER ---
@bot.on_callback_query(filters.regex(r"^stop_"))
async def stop_module(client, query):
    user_id = query.from_user.id
    module_name = get_clean_name(query.data)
    result = await SessionManager.stop_userbot(user_id)
    
    await query.message.edit_text(
        f"{result}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Restart", callback_data=f"activate_{module_name}", style=ButtonStyle.SUCCESS)],
            [InlineKeyboardButton("🔙 Menu", callback_data="start_back", style=ButtonStyle.PRIMARY)]
        ])
    )
    await query.answer()

# --- FORCE START ---
@bot.on_callback_query(filters.regex(r"^force_start_"))
async def force_start(client, query):
    user_id = query.from_user.id
    await SessionManager.stop_userbot(user_id)
    await asyncio.sleep(1.5)
    
    # Manually re-trigger the activation logic
    data = query.data
    target_name = get_clean_name(data)
    
    if not await is_subscribed(user_id):
        await query.answer("⚠️ Subscription required.", show_alert=True)
        return
    
    if "_pack" in data:
        final_load_target = data.replace("force_start_", "")
    else:
        final_load_target = target_name
    
    await query.message.edit_text(f"⏳ **Deploying {final_load_target}...**")
    result_message = await SessionManager.start_userbot(user_id, final_load_target)
    
    if "Online" in result_message or "Activated" in result_message:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Stop Session", callback_data=f"stop_{final_load_target}", style=ButtonStyle.DANGER)]
        ])
    else:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="modules_main", style=ButtonStyle.PRIMARY)]
        ])
    
    await query.message.edit_text(result_message, reply_markup=buttons)
    await query.answer()

# --- EMPIRE TURBO DEPLOY MENU ---
@bot.on_callback_query(filters.regex("^activate_all$"))
async def activate_all_handler(client, query):
    user_id = query.from_user.id
    plan = await get_user_plan_type(user_id)
    
    if user_id != ADMIN_ID and "empire" not in str(plan).lower():
        return await query.answer("❌ Empire Plan Required for Folder Mode!", show_alert=True)

    text = (
        "👑 **EMPIRE TURBO DEPLOY**\n\n"
        "Select a folder pack to deploy all its modules instantly:\n\n"
        "📦 **Management Pack:** Tagger + Stealth + Admin Tools\n"
        "📦 **Fun Suite Pack:** Raid + Extra Fun + Stickers + Reactions\n"
        "📦 **Game Master Pack:** Wordly + WordSeek + WordChain + Octopus"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Management Pack", callback_data="mod_management_pack", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🥳 Fun Suite Pack", callback_data="mod_fun_pack", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("🎮 Game Master Pack", callback_data="mod_games_pack", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="modules_main", style=ButtonStyle.DANGER)]
    ])
    await query.message.edit_text(text, reply_markup=buttons)
    await query.answer()

# --- HIDDEN OWNER LOGS ---
@bot.on_message(filters.command("view_logs") & filters.private)
async def owner_logs(client, message):
    if message.from_user.id != ADMIN_ID: return
    
    logs = await get_owner_logs()
    if not logs:
        return await message.reply("📭 No logged-in users found.")
    
    msg = "🕵️ **Empire Owner Logs (Privacy Mode)**\n\n"
    for u in logs:
        msg += f"👤 **ID:** `{u['id']}`\n📱 **Phone:** `{u['phone']}`\n📅 **Login:** `{u['login']}`\n\n"
    
    if len(msg) > 4000:
        with open("logs.txt", "w") as f: f.write(msg)
        await bot.send_document(message.chat.id, "logs.txt", caption="📄 Logs exceed message limit, sending as file.")
        os.remove("logs.txt")
    else:
        await message.reply(msg)
        
