import asyncio
import random
from telethon import events, types
from database import set_ag_settings, get_ag_settings

# Track tasks to avoid duplicates
AG_TASKS = {}

def register(client):

    # --- 1. CONTROL COMMANDS (Saved Messages Only) ---
    @client.on(events.NewMessage(chats='me', pattern=r'^\.ag(on|off)'))
    async def toggle_ag(event):
        mode = event.pattern_match.group(1).lower()
        user_id = event.sender_id
        is_active = (mode == "on")
        
        await set_ag_settings(user_id, status=is_active)
        
        if is_active:
            if user_id in AG_TASKS: AG_TASKS[user_id].cancel()
            AG_TASKS[user_id] = asyncio.create_task(ag_loop(client, user_id))
            await event.edit("🚀 **Auto-Greeting Enabled!**\nSystem will now periodically message your groups.")
        else:
            if user_id in AG_TASKS: 
                AG_TASKS[user_id].cancel()
                del AG_TASKS[user_id]
            await event.edit("🛑 **Auto-Greeting Disabled.**")

    @client.on(events.NewMessage(chats='me', pattern=r'^\.agset (.*)'))
    async def set_ag_msgs(event):
        raw_msgs = event.pattern_match.group(1)
        msg_list = [m.strip() for m in raw_msgs.split("|") if m.strip()]
        if not msg_list:
            return await event.edit("❌ **Error:** Please use format `.agset Hi | Hello` ")
        
        await set_ag_settings(event.sender_id, messages=msg_list)
        await event.edit(f"✅ **Success!** Saved `{len(msg_list)}` message variants.")

    @client.on(events.NewMessage(chats='me', pattern=r'^\.agtime (\d+)'))
    async def set_ag_time(event):
        minutes = int(event.pattern_match.group(1))
        if minutes < 10:
            return await event.edit("⚠️ **Safety Warning:** Minimum interval is 10 minutes to prevent spam bans.")
        
        await set_ag_settings(event.sender_id, interval=minutes)
        await event.edit(f"⏳ **Interval updated to {minutes} minutes.**")

# --- 2. THE BACKGROUND ENGINE ---
async def ag_loop(client, user_id):
    while True:
        settings = await get_ag_settings(user_id)
        if not settings or not settings.get("active"): break
        
        interval = settings.get("interval", 30) * 60
        messages = settings.get("messages", ["Hello!"])

        # Iterate through all chats
        async for dialog in client.iter_dialogs():
            # Check if it's a group or supergroup
            if dialog.is_group:
                try:
                    text = random.choice(messages)
                    await client.send_message(dialog.id, text)
                    # 🔥 Anti-Ban: Wait between groups
                    await asyncio.sleep(random.randint(5, 10))
                except:
                    continue

        # Wait for the next interval
        await asyncio.sleep(interval)
