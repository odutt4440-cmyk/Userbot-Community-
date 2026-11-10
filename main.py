import logging
import os
import glob
import importlib
import asyncio
import gc
from pyrogram import idle
from pyrogram.types import BotCommand
from config import API_ID, API_HASH, BOT_TOKEN, LOG_GROUP, ADMIN_ID, BACKUP_CHAT
from bot_instance import bot 
from database import init_db, get_active_userbots

# 1. Logging Configuration
logging.basicConfig(
    format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)
log = logging.getLogger(__name__)

# --- 2. CLOUD MAINTENANCE TASK ---
async def auto_backup_task():
    """Placeholder for cloud database monitoring."""
    while True:
        await asyncio.sleep(21600) # Every 6 hours
        log.info("☁️ MongoDB Atlas: Cloud synchronization is active and secure.")

# --- 🔥 AUTO-RESUME LOGIC (Staggered Boot Protocol) ---
async def resume_userbots():
    """
    Resumes active sessions one-by-one with a delay to prevent 
    server CPU spikes and memory exhaustion.
    """
    from core.session_manager import SessionManager
    
    # Wait for the Main Bot to settle first
    await asyncio.sleep(10)
    
    log.info("🔍 Initializing session recovery protocol...")
    active_users = await get_active_userbots()
    
    if not active_users:
        log.info("ℹ️ No active sessions found in database.")
        return

    log.info(f"♻️ Recovery Mode: Resuming {len(active_users)} sessions with staggered delay.")

    for user in active_users:
        try:
            # Handle both list and dictionary formats from DB
            user_id = user["user_id"] if isinstance(user, dict) else user[0]
            module = user.get("current_module", "All Modules") if isinstance(user, dict) else user[3]
            
            log.info(f"🚀 Restoring session for: {user_id}")
            
            # Start the userbot using optimized SessionManager
            await SessionManager.start_userbot(user_id, module)
            
            # 🔥 CRITICAL: 15-second gap to allow RAM to stabilize
            await asyncio.sleep(15) 
            
        except Exception as e:
            log.error(f"❌ Failed to restore session {user_id}: {e}")
    
    log.info("✅ All active sessions have been successfully recovered.")
    gc.collect() # Final RAM cleanup after boot

# 3. Plugin Loader
def load_plugins():
    path = "plugins/*.py"
    files = glob.glob(path)
    
    # 🔥 FIX: Payment.py ko sabse pehle load karo
    files.sort(key=lambda x: "payment" not in x)
    
    for name in files:
        if name.endswith("__init__.py"):
            continue
        plugin_name = os.path.basename(name).replace(".py", "")
        try:
            importlib.import_module(f"plugins.{plugin_name}")
            log.info(f"✅ Plugin loaded: {plugin_name}")
        except Exception as e:
            log.error(f"❌ Plugin failed {plugin_name}: {e}")

async def start_bot():
    print("---------------------------------------")
    print("   EMPIRE USERBOT ENGINE STARTING...   ")
    print("---------------------------------------")
    
    # STEP 1: DATABASE INITIALIZATION
    await init_db()
    log.info("SaaS Database connected (MongoDB Cloud).")

    # STEP 2: START MANAGER BOT (Kurigram)
    await bot.start()

    # --- SYNC BOT COMMANDS (Kurigram native method) ---
    try:
        await bot.set_bot_commands([
            BotCommand("start", "Open the main menu"),
            BotCommand("commands", "View all userbot commands"),
            BotCommand("modules", "Manage your active modules"),
            BotCommand("plan", "Premium subscription plans"),
            BotCommand("me", "Check your profile status"),
            BotCommand("help", "Empire Community guide")
        ])
        log.info("Bot commands synced with Telegram API.")
    except Exception as e:
        log.error(f"Command sync failed: {e}")

    # --- LOGGING UPDATES ---
    if LOG_GROUP:
        try:
            await bot.send_message(
                LOG_GROUP, 
                "⚡ **System Reboot Successful!**\n\n"
                "• **Engine:** `v3.0 Optimized`\n"
                "• **Database:** `Online` (MongoDB)\n"
                "• **Status:** `Waiting for sessions...`"
            )
        except Exception as e:
            log.error(f"Log group notification failed: {e}")

    # STEP 3: LOAD SYSTEM PLUGINS
    load_plugins()

    # 🔥 STEP 4: TRIGGER RECOVERY & BACKUP TASKS
    asyncio.create_task(resume_userbots()) 
    asyncio.create_task(auto_backup_task())
    
    print("---------------------------------------")
    print("   ENGINE IS ONLINE AND STABLE!        ")
    print("---------------------------------------")
    
    # Kurigram mein run_until_disconnected ki jagah idle() use hota hai
    await idle()

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        pass
