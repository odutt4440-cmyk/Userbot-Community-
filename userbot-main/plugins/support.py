import datetime
from bot_instance import bot
from telethon import events, Button
from config import LOG_GROUP, ADMIN_ID
from database import is_banned, get_ban_info, get_maintenance

# State tracker
SUPPORT_WAITING = {}

# --- HELPER: INTERNAL SECURITY CHECK ---
async def check_support_security(event):
    user_id = event.sender_id
    is_maint, maint_text = await get_maintenance()
    if is_maint and user_id != ADMIN_ID:
        await event.reply(f"🛠️ **Bot Under Maintenance**\n\n{maint_text}")
        return False
    if await is_banned(user_id):
        ban_info = await get_ban_info(user_id)
        reason = ban_info[1] if ban_info else "No reason provided."
        await event.reply(f"🚫 **Access Denied!**\n\nReason: `{reason}`")
        return False
    return True

# --- 1. SUPPORT MENU LOGIC ---
async def support_menu_logic(event):
    if not await check_support_security(event): return
    
    text = (
        "📢 **Support & Community Feedback**\n\n"
        "We value your feedback! If you found a bug, have an idea for a new feature, "
        "or have a complaint, please select a category below."
    )
    buttons = [
        [Button.inline("🐛 Bug Report", data="sup_bug"), Button.inline("💡 Feature Request", data="sup_feat")],
        [Button.inline("📩 General Complaint", data="sup_comp")],
        [Button.inline("🔙 Back to Main Menu", data="start_back")]
    ]
    
    # 🔥 FIX: Hamesha edit karne ki koshish karega taaki pic ke niche hi rahe
    try:
        await event.edit(text, buttons=buttons)
    except:
        # Agar edit fail ho (rare case), tabhi naya message bhejega
        await event.respond(text, buttons=buttons)

# --- 2. CALLBACK HANDLER FOR SUPPORT MAIN ---
# Ye handler ab yahi rahega, start.py me iski zarurat nahi
@bot.on(events.CallbackQuery(data="support_main"))
async def support_callback(event):
    await support_menu_logic(event)

# --- 3. CATEGORY SELECTION ---
@bot.on(events.CallbackQuery(pattern=r"sup_"))
async def start_support_input(event):
    if not await check_support_security(event): return
    
    user_id = event.sender_id
    sup_type_raw = event.data.decode("utf-8").replace("sup_", "")
    
    type_map = {
        "bug": "BUG REPORT 🐛",
        "feat": "FEATURE REQUEST 💡",
        "comp": "GENERAL COMPLAINT 📩"
    }
    
    SUPPORT_WAITING[user_id] = type_map[sup_type_raw]
    
    await event.edit(
        f"📝 **Submitting: {type_map[sup_type_raw]}**\n\n"
        "Please type your detailed message below and send it. Our team will review it instantly.",
        buttons=[[Button.inline("❌ Cancel", data="support_main")]]
    )

# --- 4. INPUT HANDLER ---
@bot.on(events.NewMessage)
async def handle_support_message(event):
    if not event.is_private: return
    user_id = event.sender_id
    
    if user_id in SUPPORT_WAITING:
        if event.text.startswith('/'): return 
        
        if not await check_support_security(event):
            del SUPPORT_WAITING[user_id]
            return

        report_type = SUPPORT_WAITING[user_id]
        report_text = event.raw_text
        user = await event.get_sender()
        name = user.first_name if user.first_name else "User"
        username = f"@{user.username}" if user.username else "N/A"
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
                await event.reply(
                    "✅ **Submission Successful!**\n\n"
                    "Thank you for your feedback. Our team has been notified.",
                    buttons=[[Button.inline("🔙 Back to Menu", data="start_back")]]
                )
            except Exception as e:
                await event.reply(f"❌ **Error:** Failed to reach admins. `{e}`")
        
        del SUPPORT_WAITING[user_id]
