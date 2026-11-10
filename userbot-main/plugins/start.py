import os
import asyncio
from bot_instance import bot 
from telethon import events, Button
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import UserNotParticipantError
from config import START_PIC, ADMIN_ID, LOG_GROUP, CHANNEL_LINK, MUST_JOIN
from database import claim_trial, has_claimed_trial, get_setting, set_setting, get_user_plan_type, is_banned, get_ban_info, get_maintenance

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
⠀⠀⠀⢷      𝐄𝐌𝐏𝐈𝐑𝐄 𝐔𝐒𝐄𝐑𝐁𝐎𝐓     ⠈⢻⣿⣿⣿⣿⡀⠀⠀⠀
⠀⠀⠀⢸⣆⠀⠀⠀⠀⠀      ⠀⠀⣿⣿⣿⣿⡇⠀⠀⠀
⠀⠀⠀⢸⣿⣦⣀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⡟⠻⠿⠟⡀⠀⠀⠀
⠀⠀ ⠀⣿⣿⣿⣿⣶⠶⠤⠤⢤⣶⣾⣿⣿⡇⠀
⠀⠀⠀⠀⠹⣿⣿⣿⠏⠀⠀⠀⠈⢿⣿⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠈⠉⠉⠀⠀⠀⠀⠀⠀⠉⠉⠀
"""

# Photo caching handle
START_MEDIA = None
VERIFIED_USERS = set()

# --- HELPER: PRIVATE ONLY CHECK ---
async def is_private_only(event):
    if not event.is_private:
        await event.reply(
            "❌ **Access Denied!**\n\n"
            "This bot is configured to work only in **Private DM** for security.\n\n"
            "👉 Please click the button below to use me in private.",
            buttons=[[Button.url("📩 Open Private Chat", "t.me/Functional_User_bot")]] # Update username
        )
        return False
    return True

# --- HELPER: SECURITY & MAINTENANCE CHECK ---
async def global_security_check(event):
    user_id = event.sender_id
    
    # 1. Maintenance Check (Admin is exempt)
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        await event.reply(f"🛠️ **Bot Under Maintenance**\n\n{maint_text}")
        return False
        
    # 2. Ban Check
    if await is_banned(user_id):
        ban_info = await get_ban_info(user_id) # Returns (time, reason)
        reason = ban_info[1] if ban_info else "No reason provided."
        await event.reply(f"🚫 **Access Denied!**\n\nYou have been banned from using this bot.\n\n**Reason:** `{reason}`\n**Contact:** @YourUsername for appeal.")
        return False
        
    return True

async def check_user_joined(user_id):
    # Admin aur pehle se verified log allowed hain
    if user_id == ADMIN_ID or user_id in VERIFIED_USERS or not MUST_JOIN:
        return True
    
    try:
        # Ek last automated check (Sirf safety ke liye)
        await bot(GetParticipantRequest(channel=MUST_JOIN, user_id=user_id))
        VERIFIED_USERS.add(user_id) # List me daal do
        return True
    except:
        # Agar join nahi kiya toh False
        return False

# --- 1. MAIN MENU LOGIC ---
async def send_start_menu(event, edit=False):
    global START_MEDIA
    welcome_text = (
        "𝐖ᴇʟᴄᴏᴍᴇ ᴛᴏ 𝐔sᴇʀʙᴏᴛ 𝐂ᴏᴍᴍᴜɴɪᴛʏ!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "ᴛʀᴧɴsꜰᴏʀᴍ ʏᴏᴜʀ ᴏʀᴅɪɴᴧʀʏ ᴛᴇʟᴇɢʀᴧᴍ ᴧᴄᴄᴏᴜɴᴛ ɪɴᴛᴏ ᴧ ᴘᴏᴡᴇʀꜰᴜʟ ᴜsᴇʀʙᴏᴛ ᴇᴍᴘɪʀᴇ. "
        "ᴇxᴘᴇʀɪᴇɴᴄᴇ ʜɪɢʜ-sᴘᴇᴇᴅ ɢᴧᴍᴇs, ɴᴇxᴛ-ɢᴇɴ ᴧᴜᴛᴏᴍᴧᴛɪᴏɴ ᴛᴏᴏʟs, ᴧɴᴅ ᴧᴅᴠᴧɴᴄᴇᴅ ᴍᴧɴᴧɢᴇᴍᴇɴᴛ "
        "ᴍᴏᴅᴜʟᴇs ʀɪɢʜᴛ ᴧᴛ ʏᴏᴜʀ ꜰɪɴɢᴇʀᴛɪᴘs. ⚡️🔥"
    )
    
    buttons = [
        [Button.inline("𝐄xᴘʟᴏʀᴇ 𝐌ᴏᴅᴜʟᴇs ", data="modules_main")],
        [Button.inline("𝐂ʟᴧɪᴍ 𝟷-𝐃ᴧʏ 𝐓ʀɪᴧʟ ", data="claim_trial_btn")],
        [Button.inline("𝐒ᴜᴘᴘᴏʀᴛ", data="support_main")], # <--- Naya Button
        [Button.inline("𝐑ᴜʟᴇs  ", data="rules"), Button.url(" 𝐂ʜᴧɴɴᴇʟ", CHANNEL_LINK)],
        [Button.inline("𝐆ᴇɴᴇʀᴧᴛᴇ 𝐒ᴇssɪᴏɴ", data="gen_string_internal")] 
    ]

    try:
        # DB se cache uthao
        cached_id = await get_setting("START_PIC_ID")
        
        # 🔥 AUTO-CLEANUP: Agar DB me purana "Kachra" (lambi string) hai, toh use ignore karo
        if cached_id and ("MessageMedia" in cached_id or "Photo(" in cached_id):
            cached_id = None

        if edit:
            await event.edit(welcome_text, buttons=buttons)
        else:
            try:
                # Try sending with Cached ID (Fast)
                sent_msg = await bot.send_file(
                    event.chat_id, 
                    cached_id if cached_id else START_PIC, 
                    caption=welcome_text, 
                    buttons=buttons
                )
                # Agar pehli baar hai ya ID galat thi, toh naya ID save karo
                if not cached_id and sent_msg and sent_msg.photo:
                    await set_setting("START_PIC_ID", str(sent_msg.photo.id))
            except Exception:
                # 🛡️ ULTIMATE FALLBACK: Agar ID fail ho jaye, toh local file se bhejo
                await bot.send_file(
                    event.chat_id, 
                    START_PIC, 
                    caption=welcome_text, 
                    buttons=buttons
                )
                
    except Exception as e:
        print(f"Start Menu Error: {e}")
        if edit: await event.edit(welcome_text, buttons=buttons)
        else: await event.respond(welcome_text, buttons=buttons)

# --- 2. COMMAND HANDLERS (Updated with Strict Force Join) ---
@bot.on(events.NewMessage(pattern=r'(?i)^/start'))
async def start_handler(event):
    if not await is_private_only(event): return
    if not await global_security_check(event): return
    
    user_id = event.sender_id
    
    # 🔥 FORCE JOIN CHECK
    is_joined = await check_user_joined(user_id)
    
    if not is_joined:
        join_text = (
            "🚀 **Welcome to Empire Userbot!**\n\n"
            "To keep our community secure and updated, you must join our official channel before using the bot.\n\n"
            "📢 **Join the channel below and click 'Verify' to unlock your dashboard.**"
        )
        buttons = [
            [Button.url("📢 Join Community", CHANNEL_LINK)],
            [Button.inline("✅ Verify & Continue", data="verify_join")]
        ]
        # Photo ke saath Join message dikhao
        return await bot.send_file(event.chat_id, START_PIC, caption=join_text, buttons=buttons)

    # ✅ AGAR JOINED HAI -> Tab Bear Animation aayegi
    anim_msg = await event.respond(f"<code>{BEAR_ASCII}</code>", parse_mode='html')
    await asyncio.sleep(2.5)
    await anim_msg.delete()
    
    if LOG_GROUP:
        user = await event.get_sender()
        name = user.first_name if user.first_name else "User"
        await bot.send_message(LOG_GROUP, f"👤 **Bot Started:** {name} (`{event.sender_id}`)")
    
    await send_start_menu(event)

@bot.on(events.NewMessage(pattern=r'(?i)^/help'))
async def help_handler(event):
    if not await is_private_only(event): return
    help_text = "📖 **Help Guide**\n\nUse buttons below to explore and activate premium modules."
    await event.reply(help_text, buttons=[[Button.inline("⚙️ Open Modules", data="modules_main")]])

# Command Handler (/modules)
@bot.on(events.NewMessage(pattern=r'(?i)^/modules'))
async def modules_cmd(event):
    if not await is_private_only(event): return
    if not await global_security_check(event): return
    
    # 🔥 FIX: modules_main ko modules_main_logic se replace kiya
    await modules_main_logic(event, edit=False)




# --- 1. MODULES MAIN MENU ---
async def modules_main_logic(event, edit=False):
    text = (
        "📂 **𝐌ᴏᴅᴜʟᴇ 𝐂ᴇɴᴛᴇʀ**\n\n"
        "Deploy your userbot now. Standard users can load single modules, "
        "while Empire users can deploy **Whole Folder Packs** at once!"
    )
    buttons = [
        [Button.inline("🚀 𝐄ᴍᴘɪʀᴇ 𝐓ᴜʀʙᴏ 𝐃ᴇᴘʟᴏʏ (𝐅ᴏʟᴅᴇʀ 𝐌ᴏᴅᴇ)", data="empire_packs")],
        [Button.inline("🛡️ Management", data="management_ub"), Button.inline("🥳 Fun Tools", data="fun_ub")],
        [Button.inline("🎮 Game Bots", data="games_ub")],
        [Button.inline("🔙 Back to Menu", data="start_back")]
    ]
    if edit: await event.edit(text, buttons=buttons)
    else: await event.respond(text, buttons=buttons)

# --- 2. EMPIRE FOLDER SELECTION MENU ---
@bot.on(events.CallbackQuery(data="empire_packs"))
async def empire_packs_menu(event):
    if not await global_security_check(event): return
    
    # Plan check before showing folders
    plan = await get_user_plan_type(event.sender_id)
    if event.sender_id != ADMIN_ID and "empire" not in str(plan).lower():
        return await event.answer("❌ Empire Plan Required for Folder Mode!", alert=True)

    text = (
        "👑 **𝐄ᴍᴘɪʀᴇ 𝐅ᴏʟᴅᴇʀ 𝐃ᴇᴘʟᴏʏ**\n\n"
        "Select a folder pack to deploy all its modules instantly:\n\n"
        "• **Management:** Tagger + Stealth + Admin Tools\n"
        "• **Fun Pack:** Raid + Extra Fun + Stickers + Reactions\n"
        "• **Games Pack:** Wordly + WordSeek + WordChain + Octopus"
    )
    buttons = [
        [Button.inline("🛡️ Management Pack", data="mod_management_pack")],
        [Button.inline("🥳 Fun Suite Pack", data="mod_fun_pack")],
        [Button.inline("🎮 Game Master Pack", data="mod_games_pack")],
        [Button.inline("🔙 Back", data="modules_main")]
    ]
    await event.edit(text, buttons=buttons)



# Button Handler
@bot.on(events.CallbackQuery(data="modules_main"))
async def modules_callback(event):
    if not await global_security_check(event): return
    await modules_main_logic(event, edit=True)



# --- 4. MANAGEMENT TOOLS MENU ---
@bot.on(events.CallbackQuery(data="management_ub"))
async def management_menu(event):
    text = (
        "🛡️ **Userbot Management Modules**\n\n"
        "**Group Admin Tools:**\n"
        "• `.ban` - Reply to a user to ban them.\n"
        "• `.mute` - Reply to a user to mute them.\n"
        "• `.warn` - Give a warning (3 warns = Auto Ban).\n"
        "• `.banall` - Clean a group (Bans all non-admins).\n\n"
        "**General Info Tools:**\n"
        "• `.id` - Get Chat/User ID.\n"
        "• `.info` - Reply to see full user details."
        "**📢 Tagging Tools:**\n"
        "• `.tagall <msg>` - Mention everyone in the group.\n"
        "• `.stopall` - Stop the active tag process.\n"
        "• `.tagdelay <sec>` - Set delay (Default 3s).\n"
        "CHECK /commands to view all userbots command."
    )
    buttons = [
        [Button.inline("👮 Admin Tools", data="mod_admin")],
        [Button.inline("📢 Tagger (TagAll)", data="mod_tagger")],
        [Button.inline("🔍 Info Tools", data="mod_info")],
        [Button.inline("🕵️ Stealth", data="mod_stealth")],
        [Button.inline("✅ Join Approver", data="mod_approver")],
        [Button.inline("🔙 Back", data="modules_main")]
    ]
    await event.edit(text, buttons=buttons)

## --- 5. FUN TOOLS MENU (With Auto-Reaction Added!) ---
@bot.on(events.CallbackQuery(data="fun_ub"))
async def fun_menu(event):
    if not await global_security_check(event): return
    text = (
        "🥳 *𝐔sᴇʀʙᴏᴛ 𝐅ᴜɴ 𝐒ᴜɪᴛᴇ* \n\n"
        "👤 *𝐈ᴅᴇɴᴛɪᴛʏ 𝐂规ᴏɴᴇ:* \n"
        "• `.clone` — Reply to copy a profile.\n"
        "• `.revert` — Restore your original profile.\n\n"
        "💤 *𝐀𝐅Κ 𝐒ʏsᴛᴇᴍ:* \n"
        "• `.afk [msg]` — Auto-reply for DMs.\n\n"
        "🖼️ *𝐒ᴛɪᴄᴋᴇʀs & 𝐌ᴇᴍɪꜰʏ:* \n"
        "• `.kang` — Add any sticker/photo to your pack.\n"
        "• `.mm [text]` — Create memes from stickers.\n\n"
        "🎭 *𝐀ᴜᴛᴏ-𝐑ᴇᴧᴄᴛɪᴏɴ (Target/GC):* \n"
        "• `.autoreact [emoji]` — Reply to someone OR type openly in GC.\n"
        "• `.stopreact` — Stop auto-reactions in the current chat.\n"
        "CHECK /commands to view all userbots command."
    )
    buttons = [
        [Button.inline("👤 Identity Clone", data="mod_clone"), Button.inline("💤 AFK Reply", data="mod_afk")],
        [Button.inline("🖼️ Stickers & Meme", data="mod_stickers"), Button.inline("🎭 Auto-React", data="mod_reaction")],
        [Button.inline("⚔️ Raid Suite", data="mod_raid"), Button.inline("✨ Extra Fun", data="mod_extra_fun")],
        [Button.inline("🤖 Auto-Greeting", data="mod_auto_greet")],
        [Button.inline("🎙️ VC Streamer", data="mod_vc_stream")],
        [Button.inline("🔙 𝐁ᴧᴄᴋ", data="modules_main")]
    ]
    await event.edit(text, buttons=buttons)

# --- 6. GAMES MENU (Full Long Text Fix) ---
@bot.on(events.CallbackQuery(data="games_ub"))
async def games_menu(event):
    if not await global_security_check(event): return

    # Tera ditto same lamba text
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
        "• `.octo on`- before starting game command\n"
        "• after starting choose rounds and mode\n"
        "• `.octo off`- it will stop the bot\n"
        "• `.octo delay 2.6 3.2` — Adjust Timing\n\n"
        "⛓️ **WordChain Pro:**\n"
        "• `on1`, `on2`... — Join specific game ID remember this id to perform command to play in multi gc\n"
        "• `ban y` | `ban y onx` — ban letter ending from y or any letter u want onx is the gc id u get in starting\n"
        "• `unban y`| `unban y onx` — unban letter ending from y or any letter u want\n"
        "• `spam random` | `spam <char>` — Ending mode\n"
        "• `spam longest` — Spam longest words\n"
        "• `settime 1 3 onx` — Set Min/Max delay\n"
        "• `status onx` — Check  and status regarding about ban and spam for specific gc\n"
        "• `status` — Check all active games and status regarding about ban and spam\n"
        "CHECK /commands to view all userbots command."
    )
    
    buttons = [
        [Button.inline("WordSeek", data="mod_wordseek"), Button.inline("WordChain", data="mod_wordchain")],
        [Button.inline("Octopus", data="mod_octopus"), Button.inline("Wordly", data="mod_wordly")],
        [Button.inline("Wordle Pro", data="mod_wordle_pro")],
        #[Button.inline("🕵️ WordGrid", data="mod_wordgrid")],
        [Button.inline("🔙 Back to Categories", data="modules_main")]
    ]

    try:
        await event.delete() 
        await bot.send_message(event.chat_id, text, buttons=buttons)
    except Exception as e:
        print(f"Error in Games Menu: {e}")
        
# --- 7. TRIAL & CALLBACKS ---
@bot.on(events.CallbackQuery(data="claim_trial_btn"))
async def trial_handler(event):
    user_id = event.sender_id
    if await has_claimed_trial(user_id):
        await event.answer("⚠️ You have already used your free trial!", alert=True)
        return
    success, result = await claim_trial(user_id)
    if success:
        await event.answer("🎉 24-Hour Trial Activated!", alert=True)
        await event.edit("🎁 **Free Trial Activated!**\n\nAccess granted for 24 hours. Start your userbot now! 🚀", 
                         buttons=[[Button.inline("⚙️ Open Modules", data="modules_main")]])
    else:
        await event.answer(f"❌ Error: {result}", alert=True)

# --- callback_handler update karo ---
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    if not await global_security_check(event): return
    data = event.data.decode("utf-8")
    
    if data == "start_back":
        await send_start_menu(event, edit=True)

    # 🔥 3. VERIFY JOIN CALLBACK
    elif data == "verify_join":
        user_id = event.sender_id
        
        # 🔥 Jaisa tune kaha: Button dabate hi "True" maan lo
        VERIFIED_USERS.add(user_id)
        
        await event.answer("✅ Access Granted! Empire Core Unlocked.", alert=False)
        
        try:
            await event.delete() # Join msg uda do
        except:
            pass
            
        # Professional Sequence (Direct to Bear)
        anim = await event.respond("<code>🔓 Initializing...</code>", parse_mode='html')
        await asyncio.sleep(1)
        await anim.edit(f"<code>{BEAR_ASCII}</code>", parse_mode='html')
        
        await asyncio.sleep(2.5)
        await anim.delete()
        
        await send_start_menu(event)
    
    elif data == "rules":
        await event.answer("1. One trial per user.\n2. No spamming commands.\n3. Respect community", alert=True)
    elif data == "dev_info":
        await event.answer("Developed by: @YourUsername\nSystem: SQLite Fast Engine v2.5", alert=True)
