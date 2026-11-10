import logging
import asyncio
import gc
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from config import API_ID, API_HASH, ADMIN_ID
from database import get_user_session, is_subscribed, get_user_plan_type, set_bot_status
from core.plugin_loader import load_all_modules
from bot_instance import bot # Manager Bot for notifications

log = logging.getLogger(__name__)

ACTIVE_CLIENTS = {}
USER_LOCKS = {}

# 🔥 Modules that should NEVER sleep (24/7 Active)
PERSISTENT_MODULES = ["afk", "stealth", "reaction", "fun_pack", "management_pack"]

# ⏳ Idle Timeout: 2 Hours (Only if bot is 100% silent)
IDLE_TIMEOUT = 7200 

class SessionManager:
    @staticmethod
    async def start_userbot(user_id, module_name):
        """Starts userbot with Gamer-Friendly Hibernation logic."""
        if user_id not in USER_LOCKS:
            USER_LOCKS[user_id] = asyncio.Lock()
        
        async with USER_LOCKS[user_id]:
            if not await is_subscribed(user_id):
                return "❌ Subscription Expired."

            trigger = str(module_name).strip().lower()

            # 🛠️ HARD CLEANUP: Ghost instance killer
            if user_id in ACTIVE_CLIENTS:
                try:
                    old = ACTIVE_CLIENTS[user_id]
                    await old["client"].disconnect()
                    if old["task"]: old["task"].cancel()
                    if old["monitor"]: old["monitor"].cancel()
                except: pass
                del ACTIVE_CLIENTS[user_id]
                gc.collect()

            # 🚀 Session Retrieval
            string_session = await get_user_session(user_id)
            if not string_session: return "❌ Session not found."

            client = TelegramClient(
                StringSession(string_session), API_ID, API_HASH,
                sequential_updates=True,
                flood_sleep_threshold=60,
                device_model="Empire-SaaS Pro"
            )

            try:
                await asyncio.wait_for(client.connect(), timeout=30)
                if not await client.is_user_authorized():
                    return "❌ Session invalid. Relogin required."

                client._event_builders.clear()
                
                # Load Plugin/Category
                await load_all_modules(client, target_module=trigger)
                
                # Background Listening Task
                task = client.loop.create_task(client.run_until_disconnected())
                
                ACTIVE_CLIENTS[user_id] = {
                    "client": client,
                    "module": trigger,
                    "task": task,
                    "last_activity": datetime.now(),
                    "monitor": None
                }

                # 🔥 HIBERNATION LOGIC
                # Agar ye persistent module nahi hai, toh activity monitor chalu karo
                if not any(m in trigger for m in PERSISTENT_MODULES):
                    ACTIVE_CLIENTS[user_id]["monitor"] = client.loop.create_task(
                        SessionManager.hibernate_monitor(user_id)
                    )

                # 🎮 GAMER PROTECTION:
                # Jab bhi userbot koi message bhejega (Manual or Automated Solve), timer reset hoga.
                @client.on(events.NewMessage(outgoing=True))
                async def reset_timer(event):
                    if user_id in ACTIVE_CLIENTS:
                        # log.info(f"Activity detected for {user_id}, resetting sleep timer.")
                        ACTIVE_CLIENTS[user_id]["last_activity"] = datetime.now()

                await set_bot_status(user_id, True, trigger.upper())
                log.info(f"🚀 Userbot Online: {user_id} | Module: {trigger}")
                
                return f"🚀 **Userbot Online!**\n📦 **Module:** `{trigger.upper()}`"

            except Exception as e:
                log.error(f"Startup Error: {e}")
                return f"❌ **Error:** `{str(e)}`"

    @staticmethod
    async def hibernate_monitor(user_id):
        """Monitors for total silence. If bot is solving games, it stays awake."""
        while user_id in ACTIVE_CLIENTS:
            await asyncio.sleep(600) # Check every 10 mins
            data = ACTIVE_CLIENTS.get(user_id)
            if not data: break
            
            # Kitni der se bot ne kuch nahi bheja?
            idle_sec = (datetime.now() - data["last_activity"]).total_seconds()
            
            if idle_sec > IDLE_TIMEOUT:
                log.info(f"😴 Hibernating totally silent bot: {user_id}")
                
                # 🛑 Stop the bot
                await SessionManager.stop_userbot(user_id)
                
                # 📩 Send Professional DM
                try:
                    await bot.send_message(
                        user_id, 
                        "😴 **Hibernation Active**\n\n"
                        "Your userbot has entered sleep mode due to 2 hours of total inactivity. "
                        "Don't worry, all your settings are safe!\n\n"
                        "⚡ **Wake up?** Use the /modules menu to restart."
                    )
                except: pass
                break

    @staticmethod
    async def stop_userbot(user_id):
        if user_id in ACTIVE_CLIENTS:
            try:
                data = ACTIVE_CLIENTS[user_id]
                await data["client"].disconnect()
                if data["task"]: data["task"].cancel()
                if data["monitor"]: data["monitor"].cancel()
                
                await set_bot_status(user_id, False, None)
                del ACTIVE_CLIENTS[user_id]
                gc.collect()
                return "🛑 **Stopped & Memory Purged.**"
            except: pass
        return "⚠️ Not running."
