import asyncio
import os
from bot_instance import bot 
from telethon import events, Button
from core.session_manager import SessionManager
from config import ADMIN_ID
from database import (
    is_subscribed, 
    global_security_check, 
    get_user_plan_type, 
    get_owner_logs,
    is_module_in_testing # 🔥 Ye import zaroori hai
)

# 🔥 MODULE CATEGORY MAP
CATEGORY_MAP = {
    "games": ["wordly", "wordseek", "wordchain", "octopus", "wordle_pro"],
    "fun": ["clone", "afk", "stickers", "reaction", "extra_fun", "raid", "auto_greet", "vc_stream"],
    "management": ["tagger", "stealth", "group_tools", "info_tools", "approver"]
}

# KEY MAPPING: Buttons se Backend Sync
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

def get_clean_name(data_bytes):
    data = data_bytes.decode("utf-8")
    # Universal Cleaner: Sab prefixes saaf kar deta hai
    name = data.replace("activate_", "").replace("force_start_", "").replace("stop_", "").replace("start_ub_", "").replace("mod_", "")
    return NAME_MAP.get(name, name)

# --- 🛠️ MAIN ACTIVATION HANDLER ---
@bot.on(events.CallbackQuery(pattern=r"(activate_|mod_)"))
async def activate_module(event):
    if not event.is_private:
        await event.answer("⚠️ Action allowed in Private DM only.", alert=True)
        return
    
    if not await global_security_check(event): return

    data = event.data.decode("utf-8")
    user_id = event.sender_id
    
    # 🛡️ 1. Subscription Check
    if not await is_subscribed(user_id):
        await event.edit(
            "⚠️ **Premium Access Required**", 
            buttons=[
                [Button.inline("💳 View Plans", data="pay_now")], 
                [Button.inline("🎁 Claim Trial", data="claim_trial_btn")]
            ]
        )
        return

    # 🔍 Clean Target Name
    target_name = get_clean_name(event.data)

    # 🛡️ 2. UNIVERSAL TESTING LOCK (Future Proof)
    # Ye line har module/button ko check karegi ki wo Admin-Only Testing me hai ya nahi
    if await is_module_in_testing(target_name) and user_id != ADMIN_ID:
        return await event.answer(
            f"🧪 {target_name.upper()} is currently in Internal Testing.\n\nPlease wait for the public rollout!", 
            alert=True
        )

    # 🔥 3. LOGIC: Pack vs Single Module
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

    await event.edit(f"⏳ **Deploying {'Folder Pack' if '_pack' in final_load_target else 'Module'}...**")
    
    # Session Manager call
    result_message = await SessionManager.start_userbot(user_id, final_load_target)

    # UI Response
    if "Online" in result_message or "Activated" in result_message:
        buttons = [[Button.inline(f"🛑 Stop Session", data=f"stop_{final_load_target}")]]
    elif "Standard Plan Limit" in result_message:
        buttons = [
            [Button.inline("🛑 Stop Current & Start This", data=f"force_start_{final_load_target}")], 
            [Button.inline("💎 Upgrade to Empire", data="pay_now")]
        ]
    else:
        buttons = [[Button.inline("🔙 Back", data="modules_main")]]
        
    await event.edit(result_message, buttons=buttons)

# --- 🛑 STOP HANDLER ---
@bot.on(events.CallbackQuery(pattern=r"stop_"))
async def stop_module(event):
    if not event.is_private: return
    user_id = event.sender_id
    module_name = get_clean_name(event.data)
    result = await SessionManager.stop_userbot(user_id)
    await event.edit(f"{result}", buttons=[[Button.inline("🚀 Restart", data=f"activate_{module_name}"), Button.inline("🔙 Menu", data="start_back")]])

# --- ⚡ FORCE START ---
@bot.on(events.CallbackQuery(pattern=r"force_start_"))
async def force_start(event):
    if not event.is_private: return
    user_id = event.sender_id
    await SessionManager.stop_userbot(user_id)
    await asyncio.sleep(1.5)
    await activate_module(event)

# --- 👑 EMPIRE TURBO DEPLOY MENU ---
@bot.on(events.CallbackQuery(data="activate_all"))
async def activate_all_handler(event):
    if not event.is_private: return
    if not await global_security_check(event): return
    
    user_id = event.sender_id
    plan = await get_user_plan_type(user_id)
    
    if user_id != ADMIN_ID and "empire" not in str(plan).lower():
        return await event.answer("❌ Empire Plan Required for Folder Mode!", alert=True)

    text = (
        "👑 **𝐄ᴍᴘɪʀᴇ 𝐓ᴜʀʙᴏ 𝐃ᴇᴘʟᴏʏ**\n\n"
        "Select a folder pack to deploy all its modules instantly:\n\n"
        "📦 **Management Pack:** Tagger + Stealth + Admin Tools\n"
        "📦 **Fun Suite Pack:** Raid + Extra Fun + Stickers + Reactions\n"
        "📦 **Game Master Pack:** Wordly + WordSeek + WordChain + Octopus"
    )
    buttons = [
        [Button.inline("🛡️ Management Pack", data="mod_management_pack")],
        [Button.inline("🥳 Fun Suite Pack", data="mod_fun_pack")],
        [Button.inline("🎮 Game Master Pack", data="mod_games_pack")],
        [Button.inline("🔙 Back to Menu", data="modules_main")]
    ]
    await event.edit(text, buttons=buttons)

# --- 🕵️ HIDDEN OWNER LOGS ---
@bot.on(events.NewMessage(pattern=r'(?i)^/view_logs'))
async def owner_logs(event):
    if event.sender_id != ADMIN_ID: return
    
    logs = await get_owner_logs()
    if not logs:
        return await event.reply("📭 No logged-in users found.")
    
    msg = "🕵️ **Empire Owner Logs (Privacy Mode)**\n\n"
    for u in logs:
        msg += f"👤 **ID:** `{u['id']}`\n📱 **Phone:** `{u['phone']}`\n📅 **Login:** `{u['login']}`\n\n"
    
    if len(msg) > 4000:
        with open("logs.txt", "w") as f: f.write(msg)
        await event.reply("📄 Logs exceed message limit, sending as file.", file="logs.txt")
        os.remove("logs.txt")
    else:
        await event.reply(msg)
