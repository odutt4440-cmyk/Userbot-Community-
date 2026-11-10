import os
import asyncio
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from pyrogram.errors import UserNotParticipant
from bot_instance import bot 
from config import START_PIC, ADMIN_ID, LOG_GROUP, CHANNEL_LINK, MUST_JOIN
from database import (
    claim_trial, 
    has_claimed_trial, 
    get_setting, 
    set_setting, 
    get_user_plan_type, 
    is_banned, 
    get_ban_info, 
    get_maintenance,
    is_staff
)

# Asli Panda (Simple ASCII Art)
BEAR_ASCII = """
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣰⣿⣿⣿⣿⣦⣀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⢿⣿⠟⠋⠉⠀⠀⠀⠀⠉⠑⠢⣄⡀⠀⠀⠀⠀⠀                
⠀⠀⠀⠀⠀⢠⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿⣦⡀                
⠀⣀⠀⠀⢀⡏⠀⢀⣴⣶⣶⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⠇
⣾⣿⣿⣦⣼⡀⠀⢺⣿⣿⡿⠃⠀⠀⠀⠀⣠⣤⣄⠀⠀⠈⡿⠋⠀
⢿⣿⣿⣿⣿⣇⠀⠤⠌⠁⠀⡀⢲⡶⠄⢸⣏⣿⣿⠀⠀⠀⡇⠀⠀
⠈⢿⣿⣿⣿⣿⣷⣄⡀⠀⠀⠈⠉⠓⠂⠀⠙⠛⠛⠠⠀⡸⠁⠀⠀
⠀⠀⠻⣿⣿⣿⣿⣿⣿⣷⣦⣄⣀⠀⠀⠀⠀⠑⠀⣠⠞⠁⠀⠀⠀
⠀⠀⠀⢸⡏⠉⠛⠛⠛⠿⠿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⠀⠀
⠀⠀⠀⠸⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠛⢿⣿⣿⣿⣿⡄⠀⠀⠀⠀
⠀⠀⠀⢷      EMPIRE USERBOT     ⠈⢻⣿⣿⣿⣿⡀⠀⠀⠀
⠀⠀⠀⢸⣆⠀⠀⠀⠀⠀      ⠀⠀⣿⣿⣿⣿⡇⠀⠀⠀
⠀⠀⠀⢸⣿⣦⣀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⡟⠻⠿⠟⡀⠀⠀⠀
⠀⠀ ⠀⣿⣿⣿⣿⣶⠶⠤⠤⢤⣶⣾⣿⣿⡇⠀
⠀⠀⠀⠀⠹⣿⣿⣿⠏⠀⠀⠀⠈⢿⣿⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠈⠉⠉⠀⠀⠀⠀⠀⠀⠉⠉⠀
"""

# --- HELPER: PRIVATE ONLY CHECK ---
async def is_private_only(message):
    if message.chat.type != "private":
        await message.reply(
            "❌ **Access Denied!**\n\n"
            "This bot is configured to work only in **Private DM** for security.\n\n"
            "👉 Please click the button below to use me in private.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Open Private Chat", url="t.me/Functional_User_bot")]
            ])
        )
        return False
    return True

# --- HELPER: SECURITY & MAINTENANCE CHECK ---
async def global_security_check(message):
    user_id = message.from_user.id
    
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        await message.reply(f"🛠️ **Bot Under Maintenance**\n\n{maint_text}")
        return False
        
    if await is_banned(user_id):
        ban_info = await get_ban_info(user_id)
        reason = ban_info[1] if ban_info else "No reason provided."
        await message.reply(f"🚫 **Access Denied!**\n\nYou have been banned from using this bot.\n\n**Reason:** `{reason}`\n**Contact:** @YourUsername for appeal.")
        return False
        
    return True

# --- REAL FORCE JOIN CHECK ---
async def check_user_joined(user_id):
    if user_id == ADMIN_ID or not MUST_JOIN:
        return True
    
    try:
        await bot.get_chat_member(MUST_JOIN, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Force-join check error: {e}")
        return True

# --- 1. MAIN MENU LOGIC ---
async def send_start_menu(message, edit=False):
    user_id = message.from_user.id
    
    # Normal English Text
    welcome_text = (
        "**WELCOME TO USER COMMUNITY!**\n"
        "──────────────────\n"
        "Trusted Guard Engine loads your entire bot from a single session string. "
        "Experience high-speed games, lex-free interaction tools, and advanced modules right at your fingertips. ⚡🔥"
    )
    
    button_list = []
    if user_id == ADMIN_ID or await is_staff(user_id):
        button_list.append([
            InlineKeyboardButton("🛡️ Admin Panel", callback_data="admin_panel_main", style=ButtonStyle.DANGER)
        ])
        
    button_list.extend([
        [InlineKeyboardButton("Extract Modules", callback_data="modules_main", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("Claim 24-Hour Trial", callback_data="claim_trial_btn", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("Support", callback_data="support_main", style=ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton("Rules", callback_data="rules", style=ButtonStyle.DANGER),
            InlineKeyboardButton("Channel", url=CHANNEL_LINK)
        ],
        [InlineKeyboardButton("Generate Session", callback_data="gen_string_internal", style=ButtonStyle.SUCCESS)]
    ])
    
    buttons = InlineKeyboardMarkup(button_list)

    try:
        cached_id = await get_setting("START_PIC_ID")
        if cached_id and ("MessageMedia" in cached_id or "Photo(" in cached_id):
            cached_id = None

        if edit:
            await message.edit_text(welcome_text, reply_markup=buttons)
        else:
            sent = await bot.send_photo(
                message.chat.id,
                START_PIC,
                caption=welcome_text,
                reply_markup=buttons
            )
            if not cached_id and sent and sent.photo:
                await set_setting("START_PIC_ID", str(sent.photo.file_id))
    except Exception as e:
        print(f"Start Menu Error: {e}")
        await message.reply(welcome_text, reply_markup=buttons)

# --- 2. COMMAND HANDLERS ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if not await global_security_check(message): return
    
    user_id = message.from_user.id
    is_joined = await check_user_joined(user_id)
    
    if not is_joined:
        join_text = (
            "🚀 **Welcome to Empire Userbot!**\n\n"
            "To keep our community secure and updated, you must join our official channel before using the bot.\n\n"
            "📢 **Join the channel below and click 'Verify' to unlock your dashboard.**"
        )
        await bot.send_photo(
            message.chat.id,
            START_PIC,
            caption=join_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Community", url=CHANNEL_LINK, style=ButtonStyle.PRIMARY)],
                [InlineKeyboardButton("✅ Verify & Continue", callback_data="verify_join", style=ButtonStyle.SUCCESS)]
            ])
        )
        return

    anim_msg = await message.reply(f"<code>{BEAR_ASCII}</code>")
    await asyncio.sleep(2.5)
    await anim_msg.delete()
    
    if LOG_GROUP:
        name = message.from_user.first_name or "User"
        await bot.send_message(LOG_GROUP, f"👤 **Bot Started:** {name} (`{user_id}`)")
    
    await send_start_menu(message)

# NOTE: /help handler removed from here. It is in help.py now.

@bot.on_message(filters.command("modules") & filters.private)
async def modules_cmd(client, message):
    if not await global_security_check(message): return
    await modules_main_logic(message, edit=False)

# --- 3. MODULES MAIN MENU ---
async def modules_main_logic(message, edit=False):
    text = (
        "📂 **MODULE CENTER**\n\n"
        "Deploy your userbot now. Standard users can load single modules, "
        "while Empire users can deploy **Whole Folder Packs** at once!"
    )
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 EMPIRE TURBO DEPLOY (FOLDER MODE)", callback_data="empire_packs", style=ButtonStyle.PRIMARY)],
        [
            InlineKeyboardButton("🛡️ Management", callback_data="management_ub", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("🥳 Fun Tools", callback_data="fun_ub", style=ButtonStyle.SUCCESS)
        ],
        [InlineKeyboardButton("🎮 Game Bots", callback_data="games_ub", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="start_back", style=ButtonStyle.DANGER)]
    ])
    
    if edit:
        await message.edit_text(text, reply_markup=buttons)
    else:
        await message.reply(text, reply_markup=buttons)

# --- 4. SUBMENU HANDLERS ---

# --- MANAGEMENT SUBMENU ---
@bot.on_callback_query(filters.regex("^management_ub$"))
async def management_menu(client, query):
    text = (
        "🛡️ **Userbot Management Modules**\n\n"
        "**Group Admin Tools:**\n"
        "• `.ban` - Reply to a user to ban them.\n"
        "• `.mute` - Reply to a user to mute them.\n"
        "• `.warn` - Give a warning (3 warns = Auto Ban).\n"
        "• `.banall` - Clean a group (Bans all non-admins).\n\n"
        "**General Info Tools:**\n"
        "• `.id` - Get Chat/User ID.\n"
        "• `.info` - Reply to see full user details.\n\n"
        "**📢 Tagging Tools:**\n"
        "• `.tagall <msg>` - Mention everyone in the group.\n"
        "• `.stopall` - Stop the active tag process.\n"
        "• `.tagdelay <sec>` - Set delay (Default 3s).\n\n"
        "**🕵️ Stealth Monitor:**\n"
        "• `.snatcher on/off` — Auto-save view-once media.\n"
        "• `.antidelete on/off` — Log deleted messages in Saved Msg.\n\n"
        "✅ **JOIN APPROVER:**\n"
        "• `.approveall` — Fast batch approval (200 users/batch).\n"
        "• `.approveallx` — Continuous auto-mode.\n"
        "• `.autoapprove on/off` — Real-time auto-accept.\n"
        "• `.approve [ID]` — Approve a specific user by their ID."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👮 Admin Tools", callback_data="mod_admin", style=ButtonStyle.DANGER)],
        [InlineKeyboardButton("📢 Tagger (TagAll)", callback_data="mod_tagger", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔍 Info Tools", callback_data="mod_info", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🕵️ Stealth", callback_data="mod_stealth", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("✅ Join Approver", callback_data="mod_approver", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("🔙 Back", callback_data="modules_main", style=ButtonStyle.DANGER)]
    ])
    await query.message.edit_text(text, reply_markup=buttons)
    await query.answer()

# --- FUN SUBMENU ---
@bot.on_callback_query(filters.regex("^fun_ub$"))
async def fun_menu(client, query):
    text = (
        "🥳 **USERBOT FUN SUITE**\n\n"
        "👤 **IDENTITY & AFK:**\n"
        "• `.clone` — Copy a profile. | `.revert` — Restore.\n"
        "• `.afk [msg]` — Set auto-reply for DMs/Mentions.\n\n"
        "🖼️ **STICKERS & MEMIFY:**\n"
        "• `.kang` — Add any sticker/photo to your pack.\n"
        "• `.mm [text]` — Create memes from stickers.\n\n"
        "🎭 **AUTO-REACTION:**\n"
        "• `.autoreact [emoji]` — Target user (Reply) or GC.\n"
        "• `.stopreact` — Stop auto-reactions in chat.\n\n"
        "⚔️ **RAID SUITE:**\n"
        "• `.spam [count] [text]` — High-speed message spam.\n"
        "• `.raid [count] [target]` — Insult raid on a user.\n"
        "• `.replyraid` (Reply) — Auto-insult reply engine.\n"
        "• `.stop` — Kill raids. | `.clear` — Delete 100 msgs.\n\n"
        "🎙️ **VC STREAMER:**\n"
        "• `.vctarget` — Lock a group for streaming.\n"
        "• `.vcstream` — Reply to audio to go live.\n"
        "• `.vcstop` — Stop stream, leave VC.\n\n"
        "🤖 **AUTO-GREETING:**\n"
        "• `.agon` — Enable periodic messaging.\n"
        "• `.agoff` — Disable the promoter."
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Identity Clone", callback_data="mod_clone", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("💤 AFK Reply", callback_data="mod_afk", style=ButtonStyle.PRIMARY)
        ],
        [
            InlineKeyboardButton("🖼️ Stickers & Meme", callback_data="mod_stickers", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("🎭 Auto-React", callback_data="mod_reaction", style=ButtonStyle.SUCCESS)
        ],
        [
            InlineKeyboardButton("⚔️ Raid Suite", callback_data="mod_raid", style=ButtonStyle.DANGER),
            InlineKeyboardButton("✨ Extra Fun", callback_data="mod_extra_fun", style=ButtonStyle.PRIMARY)
        ],
        [InlineKeyboardButton("🤖 Auto-Greeting", callback_data="mod_auto_greet", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("🎙️ VC Streamer", callback_data="mod_vc_stream", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back", callback_data="modules_main", style=ButtonStyle.DANGER)]
    ])
    await query.message.edit_text(text, reply_markup=buttons)
    await query.answer()

# --- GAMES SUBMENU ---
@bot.on_callback_query(filters.regex("^games_ub$"))
async def games_menu(client, query):
    text = (
        "🎮 **Userbot Game Modules**\n\n"
        "Deploy high-speed solvers. Use these commands in saved message once active:\n\n"
        "🧩 **WordSeek Solver:**\n"
        "• `.ws on` | `.ws off` — Toggle Solver\n"
        "• `.ws loop on` | `.ws loop off` — Auto Restart\n"
        "• `.ws delay 0.5 1.5` — Set Min/Max speed\n\n"
        "📝 **Wordly Master:**\n"
        "• `.won` | `.woff` — Toggle Automation\n"
        "• `.wloop on` | `.wloop off` — Auto New Game\n"
        "• `.wdelay 0.5` — Set Typing Delay\n"
        "• `.wstatus` — Check Round Stats\n\n"
        "🐙 **Octopus Engine:**\n"
        "• `.octo on` / `.octo off` — Toggle\n"
        "• `.octo delay 2.6 3.2` — Adjust Timing\n\n"
        "⛓️ **WordChain Pro:**\n"
        "• `on1`, `on2`... — Join specific game ID\n"
        "• `ban y` / `unban y` — Ban/unban letter endings\n"
        "• `spam random` / `spam longest` — Spam mode\n"
        "• `status` — Check all active games\n\n"
        "🧩 **Wordle Pro:**\n"
        "• `.wd on/off` — Toggle Master Solver.\n"
        "• `.wd loop on/off` — Auto-start rounds.\n"
        "• `.wd delay 1.0 2.5` — Set Typing Delay.\n"
        "👉 _Supports 3, 4, 5, 6, 7 letter modes automatically!_"
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("WordSeek", callback_data="mod_wordseek", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("WordChain", callback_data="mod_wordchain", style=ButtonStyle.PRIMARY)
        ],
        [
            InlineKeyboardButton("Octopus", callback_data="mod_octopus", style=ButtonStyle.SUCCESS),
            InlineKeyboardButton("Wordly", callback_data="mod_wordly", style=ButtonStyle.SUCCESS)
        ],
        [InlineKeyboardButton("Wordle Pro", callback_data="mod_wordle_pro", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back", callback_data="modules_main", style=ButtonStyle.DANGER)]
    ])
    await query.message.edit_text(text, reply_markup=buttons)
    await query.answer()

# --- EMPIRE PACKS MENU ---
@bot.on_callback_query(filters.regex("^empire_packs$"))
async def empire_packs_menu(client, query):
    user_id = query.from_user.id
    plan = await get_user_plan_type(user_id)
    if user_id != ADMIN_ID and "empire" not in str(plan).lower():
        return await query.answer("❌ Empire Plan Required for Folder Mode!", show_alert=True)
    
    text = (
        "👑 **EMPIRE FOLDER DEPLOY**\n\n"
        "Select a folder pack to deploy all its modules instantly:\n\n"
        "• **Management:** Tagger + Stealth + Admin Tools\n"
        "• **Fun Pack:** Raid + Extra Fun + Stickers + Reactions\n"
        "• **Games Pack:** Wordly + WordSeek + WordChain + Octopus"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ Management Pack", callback_data="mod_management_pack", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🥳 Fun Suite Pack", callback_data="mod_fun_pack", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton("🎮 Game Master Pack", callback_data="mod_games_pack", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back", callback_data="modules_main", style=ButtonStyle.DANGER)]
    ])
    await query.message.edit_text(text, reply_markup=buttons)
    await query.answer()

# --- 5. OTHER CALLBACKS ---
@bot.on_callback_query(filters.regex("^modules_main$"))
async def modules_callback(client, query):
    await modules_main_logic(query.message, edit=True)
    await query.answer()

@bot.on_callback_query(filters.regex("^start_back$"))
async def start_back_callback(client, query):
    await query.message.delete()
    await send_start_menu(query.message)

@bot.on_callback_query(filters.regex("^verify_join$"))
async def verify_join_callback(client, query):
    user_id = query.from_user.id
    joined = await check_user_joined(user_id)
    
    if not joined:
        await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
        return
    
    await query.answer("✅ Access Granted! Empire Core Unlocked.", show_alert=False)
    
    try:
        await query.message.delete()
    except:
        pass
    
    anim = await bot.send_message(query.message.chat.id, "<code>🔓 Initializing...</code>")
    await asyncio.sleep(1)
    await anim.edit_text(f"<code>{BEAR_ASCII}</code>")
    await asyncio.sleep(2.5)
    await anim.delete()
    
    await send_start_menu(query.message)

@bot.on_callback_query(filters.regex("^claim_trial_btn$"))
async def trial_handler(client, query):
    user_id = query.from_user.id
    if await has_claimed_trial(user_id):
        await query.answer("⚠️ You have already used your free trial!", show_alert=True)
        return
    success, result = await claim_trial(user_id)
    if success:
        await query.answer("🎉 24-Hour Trial Activated!", show_alert=True)
        await query.message.edit_text(
            "🎁 **Free Trial Activated!**\n\nAccess granted for 24 hours. Start your userbot now! 🚀",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Open Modules", callback_data="modules_main", style=ButtonStyle.PRIMARY)]
            ])
        )
    else:
        await query.answer(f"❌ Error: {result}", show_alert=True)

@bot.on_callback_query(filters.regex("^rules$"))
async def rules_callback(client, query):
    await query.answer("1. One trial per user.\n2. No spamming commands.\n3. Respect community", show_alert=True)
