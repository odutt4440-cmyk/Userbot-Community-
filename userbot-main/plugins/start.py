import os
import asyncio
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import UserNotParticipant
from richgram import rich_button, rich_button_row, rich_send
from bot_instance import bot 
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

# --- HELPER: PRIVATE ONLY CHECK (Kurigram version) ---
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

# --- HELPER: SECURITY & MAINTENANCE CHECK (Kurigram version) ---
async def global_security_check(message):
    user_id = message.from_user.id
    
    # 1. Maintenance Check (Admin is exempt)
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        await message.reply(f"🛠️ **Bot Under Maintenance**\n\n{maint_text}")
        return False
        
    # 2. Ban Check
    if await is_banned(user_id):
        ban_info = await get_ban_info(user_id)
        reason = ban_info[1] if ban_info else "No reason provided."
        await message.reply(f"🚫 **Access Denied!**\n\nYou have been banned from using this bot.\n\n**Reason:** `{reason}`\n**Contact:** @YourUsername for appeal.")
        return False
        
    return True

# --- REAL FORCE JOIN CHECK (Kurigram native) ---
async def check_user_joined(user_id):
    """Asli API check. Agar join nahi kiya toh UserNotParticipant raise hoga."""
    if user_id == ADMIN_ID or not MUST_JOIN:
        return True
    
    try:
        # Kurigram ka native method
        await bot.get_chat_member(MUST_JOIN, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        # Agar channel private hai ya bot admin nahi hai, toh fail-open (block mat karo)
        print(f"Force-join check error: {e}")
        return True

# --- 1. MAIN MENU LOGIC (richgram colored buttons) ---
async def send_start_menu(message, edit=False):
    global START_MEDIA
    welcome_text = (
        "ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴜsᴇʀ ᴄᴏᴍᴍᴜɴɪᴛʏ!\n"
        "──────────────────\n"
        "ᴛʀᴜsᴛᴇᴅ ɢᴜᴀʀᴅ ᴇɴɢɪɴᴇ ʟᴏᴀᴅs ʏᴏᴜʀ ᴇɴᴛɪʀᴇ ʙᴏᴛ ғʀᴏᴍ ᴀ sɪɴɢʟᴇ sᴇssɪᴏɴ sᴛʀɪɴɢ. "
        "ᴇxᴘᴇʀɪᴇɴᴄᴇ ʜɪɢʜ-sᴘᴇᴇᴅ ɢᴀᴍᴇs, ʟᴇx-ғʀᴇᴇ ɪɴᴛᴇʀᴀᴄᴛɪᴏɴ ᴛᴏᴏʟs, ᴀɴᴅ ᴀᴅᴠᴀɴᴄᴇᴅ ᴍᴏᴅᴜʟᴇs ʀɪɢʜᴛ ᴀᴛ ʏᴏᴜʀ ғɪɴɢᴇʀᴛɪᴘs. ⚡🔥"
    )
    
    # richgram buttons (colored)
    buttons = (
        rich_button_row(
            rich_button("ᴇxᴛʀᴀᴄᴛ ᴍᴏᴅᴜʟᴇs", callback_data="modules_main", style="primary")
        )
        + rich_button_row(
            rich_button("ᴄʟᴀɪᴍ 𝟽-ᴅᴀʏ ᴛʀɪᴀʟ", callback_data="claim_trial_btn", style="success")
        )
        + rich_button_row(
            rich_button("sᴜᴘᴘᴏʀᴛ", callback_data="support_main", style="primary")
        )
        + rich_button_row(
            rich_button("ʀᴜʟᴇs", callback_data="rules", style="danger"),
            rich_button("ᴄʜᴀɴɴᴇʟ", url=CHANNEL_LINK, style="link")
        )
        + rich_button_row(
            rich_button("ɢᴇɴᴇʀᴀᴛᴇ sᴇssɪᴏɴ", callback_data="gen_string_internal", style="success")
        )
    )

    try:
        cached_id = await get_setting("START_PIC_ID")
        if cached_id and ("MessageMedia" in cached_id or "Photo(" in cached_id):
            cached_id = None

        if edit:
            # richgram edit ke liye alag method hai, par simplicity ke liye text edit karte hain
            await message.edit_text(welcome_text)
            # Note: richgram edit alag se handle karna padega, abhi ke liye text-only edit
        else:
            # Photo ke saath rich message bhejna richgram se possible hai
            await rich_send(
                bot,
                message.chat.id,
                welcome_text + buttons,
                reply_to_message_id=message.id
            )
    except Exception as e:
        print(f"Start Menu Error: {e}")
        await message.reply(welcome_text)

# --- 2. COMMAND HANDLERS (Kurigram) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if not await global_security_check(message): return
    
    user_id = message.from_user.id
    
    # REAL FORCE JOIN CHECK
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
                [InlineKeyboardButton("📢 Join Community", url=CHANNEL_LINK)],
                [InlineKeyboardButton("✅ Verify & Continue", callback_data="verify_join")]
            ])
        )
        return

    # Bear Animation
    anim_msg = await message.reply(f"<code>{BEAR_ASCII}</code>")
    await asyncio.sleep(2.5)
    await anim_msg.delete()
    
    if LOG_GROUP:
        name = message.from_user.first_name or "User"
        await bot.send_message(LOG_GROUP, f"👤 **Bot Started:** {name} (`{user_id}`)")
    
    await send_start_menu(message)

@bot.on_message(filters.command("help") & filters.private)
async def help_handler(client, message):
    help_text = "📖 **Help Guide**\n\nUse buttons below to explore and activate premium modules."
    await message.reply(
        help_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Modules", callback_data="modules_main")]
        ])
    )

@bot.on_message(filters.command("modules") & filters.private)
async def modules_cmd(client, message):
    if not await global_security_check(message): return
    await modules_main_logic(message, edit=False)

# --- 3. MODULES MAIN MENU ---
async def modules_main_logic(message, edit=False):
    text = (
        "📂 **ᴍᴏᴅᴜʟᴇ ᴄᴇɴᴛᴇʀ**\n\n"
        "Deploy your userbot now. Standard users can load single modules, "
        "while Empire users can deploy **Whole Folder Packs** at once!"
    )
    
    buttons = (
        rich_button_row(
            rich_button("🚀 ᴇᴍᴘɪʀᴇ ᴛᴜʀʙᴏ ᴅᴇᴘʟᴏʏ (ғᴏʟᴅᴇʀ ᴍᴏᴅᴇ)", callback_data="empire_packs", style="primary")
        )
        + rich_button_row(
            rich_button("🛡️ Management", callback_data="management_ub", style="success"),
            rich_button("🥳 Fun Tools", callback_data="fun_ub", style="success")
        )
        + rich_button_row(
            rich_button("🎮 Game Bots", callback_data="games_ub", style="primary")
        )
        + rich_button_row(
            rich_button("🔙 Back to Menu", callback_data="start_back", style="danger")
        )
    )
    
    if edit:
        await message.edit_text(text)
    else:
        await rich_send(bot, message.chat.id, text + buttons, reply_to_message_id=message.id)

# --- 4. CALLBACK HANDLERS (Kurigram) ---
@bot.on_callback_query(filters.regex("^modules_main$"))
async def modules_callback(client, query):
    await query.message.edit_text("Loading...")
    # Note: richgram edit abhi text-only hai, isliye simple edit
    await modules_main_logic(query.message, edit=True)

@bot.on_callback_query(filters.regex("^start_back$"))
async def start_back_callback(client, query):
    await query.message.delete()
    await send_start_menu(query.message)

@bot.on_callback_query(filters.regex("^verify_join$"))
async def verify_join_callback(client, query):
    user_id = query.from_user.id
    
    # REAL CHECK: API se verify karo
    joined = await check_user_joined(user_id)
    
    if not joined:
        await query.answer("❌ You haven't joined the channel yet!", show_alert=True)
        return
    
    await query.answer("✅ Access Granted! Empire Core Unlocked.", show_alert=False)
    
    try:
        await query.message.delete()
    except:
        pass
    
    # Bear sequence
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
                [InlineKeyboardButton("⚙️ Open Modules", callback_data="modules_main")]
            ])
        )
    else:
        await query.answer(f"❌ Error: {result}", show_alert=True)

@bot.on_callback_query(filters.regex("^rules$"))
async def rules_callback(client, query):
    await query.answer("1. One trial per user.\n2. No spamming commands.\n3. Respect community", show_alert=True)
