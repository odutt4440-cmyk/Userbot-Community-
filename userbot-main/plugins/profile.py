from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot
from database import get_user_profile

# Use Kurigram-compatible security check from start.py
from plugins.start import global_security_check as start_security_check

# --- USER PROFILE COMMAND: /me ---
@bot.on_message(filters.command("me") & filters.private)
async def user_profile_handler(client, message):
    # 🛡️ Global Ban/Maintenance Check
    if not await start_security_check(message):
        return

    user_id = message.from_user.id
    name = message.from_user.first_name or "User"

    # Fetch profile from DB
    profile = await get_user_profile(user_id)

    profile_text = (
        "👤 **Userbot Community Profile**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 **Name:** {name}\n"
        f"🆔 **User ID:** `{user_id}`\n\n"
        f"💎 **Current Plan:** `{profile['plan']}`\n"
        f"⏳ **Time Remaining:** `{profile['time_left']}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 *Empire Plan:* All modules simultaneous.\n"
        "✨ *Standard Plan:* One module at a time."
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ My Modules", callback_data="modules_main", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("💳 Upgrade / Renew", callback_data="pay_now", style=ButtonStyle.SUCCESS)]
    ])

    await message.reply(profile_text, reply_markup=buttons)
