from bot_instance import bot
from telethon import events, Button
from database import get_user_profile, global_security_check
import datetime

# --- USER PROFILE COMMAND: /me ---
@bot.on(events.NewMessage(pattern=r'(?i)^/me'))
async def user_profile_handler(event):
    # 🛡️ Private DM Check
    if not event.is_private:
        return # Ignore in groups as per your request

    # 🛡️ Global Ban/Maintenance Check
    if not await global_security_check(event):
        return

    user_id = event.sender_id
    user = await event.get_sender()
    name = user.first_name if user.first_name else "User"

    # Database se optimized profile data uthao
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

    buttons = [
        [Button.inline("⚙️ My Modules", data="modules_main")],
        [Button.inline("💳 Upgrade / Renew", data="pay_now")]
    ]

    await event.reply(profile_text, buttons=buttons)
