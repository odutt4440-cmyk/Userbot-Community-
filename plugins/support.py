import datetime
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot
from config import LOG_GROUP, ADMIN_ID
from database import is_banned, get_ban_info, get_maintenance

# State tracker
SUPPORT_WAITING = {}

# --- HELPER: INTERNAL SECURITY CHECK (Kurigram) ---
async def check_support_security(message):
    user_id = message.from_user.id
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        await message.reply(f"🛠️ **Bot Under Maintenance**\n\n{maint_text}")
        return False
    if await is_banned(user_id):
        ban_info = await get_ban_info(user_id)
        reason = ban_info[1] if ban_info else "No reason provided."
        await message.reply(f"🚫 **Access Denied!**\n\nReason: `{reason}`")
        return False
    return True

# --- 1. SUPPORT MENU LOGIC ---
async def support_menu_logic(query):
    text = (
        "📢 **Support & Community Feedback**\n\n"
        "We value your feedback! If you found a bug, have an idea for a new feature, "
        "or have a complaint, please select a category below."
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🐛 Bug Report", callback_data="sup_bug", style=ButtonStyle.DANGER),
            InlineKeyboardButton("💡 Feature Request", callback_data="sup_feat", style=ButtonStyle.SUCCESS)
        ],
        [InlineKeyboardButton("📩 General Complaint", callback_data="sup_comp", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start_back", style=ButtonStyle.DANGER)]
    ])
    
    try:
        await query.message.edit_text(text, reply_markup=buttons)
    except:
        await query.message.reply(text, reply_markup=buttons)

# --- 2. CALLBACK HANDLER FOR SUPPORT MAIN ---
@bot.on_callback_query(filters.regex("^support_main$"))
async def support_callback(client, query):
    user_id = query.from_user.id
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        return await query.answer("🛠️ Bot is under maintenance.", show_alert=True)
    if await is_banned(user_id):
        return await query.answer("🚫 You are banned from using this bot.", show_alert=True)
    
    await support_menu_logic(query)
    await query.answer()

# --- 3. CATEGORY SELECTION ---
@bot.on_callback_query(filters.regex(r"^sup_(bug|feat|comp)$"))
async def start_support_input(client, query):
    user_id = query.from_user.id
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        return await query.answer("🛠️ Bot is under maintenance.", show_alert=True)
    if await is_banned(user_id):
        return await query.answer("🚫 You are banned from using this bot.", show_alert=True)
    
    sup_type_raw = query.matches[0].group(1)
    type_map = {
        "bug": "BUG REPORT 🐛",
        "feat": "FEATURE REQUEST 💡",
        "comp": "GENERAL COMPLAINT 📩"
    }
    
    SUPPORT_WAITING[user_id] = type_map[sup_type_raw]
    
    await query.message.edit_text(
        f"📝 **Submitting: {type_map[sup_type_raw]}**\n\n"
        "Please type your detailed message below and send it. Our team will review it instantly.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="support_main", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# --- 4. INPUT HANDLER (FIXED FOR CLASH) ---
@bot.on_message(filters.private & filters.text & ~filters.photo & ~filters.command(["start", "admin", "plan", "modules", "help", "commands"]))
async def handle_support_message(client, message):
    user_id = message.from_user.id
    
    # Agar user support ka wait nahi kar raha toh return karo
    if user_id not in SUPPORT_WAITING:
        return
    
    if message.text.startswith('/'): return 
    
    # Quick security check
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        await message.reply(f"🛠️ **Bot Under Maintenance**\n\n{maint_text}")
        del SUPPORT_WAITING[user_id]
        return
    if await is_banned(user_id):
        await message.reply("🚫 **Access Denied!** You are banned from using this bot.")
        del SUPPORT_WAITING[user_id]
        return

    report_type = SUPPORT_WAITING[user_id]
    report_text = message.text
    name = message.from_user.first_name or "User"
    username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
    time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_message = (
        f"📢 **NEW COMMUNITY SUBMISSION**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **Category:** `{report_type}`\n"
        f"👤 **From:** {name} ({username})\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"⏰ **Sent At:** `{time_now}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Message Content:**\n{report_text}"
    )

    if LOG_GROUP:
        try:
            await bot.send_message(LOG_GROUP, log_message)
            await message.reply(
                "✅ **Submission Successful!**\n\n"
                "Thank you for your feedback. Our team has been notified.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Menu", callback_data="start_back", style=ButtonStyle.PRIMARY)]
                ])
            )
        except Exception as e:
            await message.reply(f"❌ **Error:** Failed to reach admins. `{e}`")
    
    del SUPPORT_WAITING[user_id]
