import datetime
import logging
import json
import asyncio
import certifi # SSL fix ke liye
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, ADMIN_ID

log = logging.getLogger(__name__)

# --- GLOBAL CACHE (For Speed) ---
# Format: {user_id: expiry_datetime}
SUBS_CACHE = {} 
# Format: set([user_id1, user_id2])
BANNED_CACHE = set()
# Maintenance status
MAINT_CACHE = {"mode": False, "text": ""}

# --- INITIALIZE VARIABLES (None set karo taaki NameError na aaye) ---
db = None
users_db = None
subs_db = None
state_db = None
banned_db = None
trials_db = None
settings_db = None
sudo_db = None
afk_db = None
warn_db = None
stealth_db = None
ai_db = None
pack_db = None
reaction_db = None

# --- 🔥 THE ULTIMATE ROBUST INITIALIZATION FUNCTION ---
async def init_db():
    global db, users_db, subs_db, state_db, banned_db, trials_db, settings_db, sudo_db, afk_db, warn_db, stealth_db, ai_db, pack_db, reaction_db
    
    try:
        log.info("Connecting to MongoDB Cloud (Robust Mode)...")
        ca = certifi.where()
        
        # 🔥 ULTRA-STABLE PARAMETERS
        # Isse DNS issues (Errno -3) aur Primary re-election handle honge
        client = AsyncIOMotorClient(
            MONGO_URL,
            tlsCAFile=ca, 
            serverSelectionTimeoutMS=15000, # 15 sec tak wait karega node milne ke liye
            connectTimeoutMS=30000,        # DNS resolve ke liye 30 sec ka buffer
            socketTimeoutMS=30000,         # Data transfer timeout
            retryWrites=True,              # Write fail hone par automatic retry
            retryReads=True,               # Read fail hone par automatic retry
            heartbeatFrequencyMS=10000     # Har 10 sec me connection zinda rakhega
        )
        
        db = client["UserbotCommunity"]
        
        # Collection Mapping
        users_db = db["users"]
        subs_db = db["subscriptions"]
        state_db = db["game_state"]
        banned_db = db["banned_users"]
        trials_db = db["trials"]
        settings_db = db["settings"]
        sudo_db = db["sudo_users"]
        afk_db = db["afk_settings"]
        warn_db = db["warnings"]
        stealth_db = db["stealth_settings"]
        ai_db = db["ai_settings"]
        pack_db = db["sticker_packs"]
        reaction_db = db["reaction_settings"]

        # 🔥 Pehle ping check (Agar network slow hai toh yahan retry logic trigger hoga)
        await db.command("ping")
        log.info("🚀 MongoDB Cloud Connected Successfully!")
        
        # Cache load startup par
        await reload_caches()

    except Exception as e:
        log.error(f"❌ MongoDB Connection Error: {e}")
        log.info("🔄 Retrying in 10 seconds...")
        # 🔥 CRITICAL: Bot ko crash hone se bachata hai aur khud reconnect karta hai
        await asyncio.sleep(10)
        return await init_db()

async def reload_caches():
    """DB se data utha kar RAM cache me bharta hai (Optimization)"""
    global SUBS_CACHE, BANNED_CACHE, MAINT_CACHE
    
    # 1. Load Subscriptions
    cursor = subs_db.find({"status": "active"})
    async for sub in cursor:
        SUBS_CACHE[sub["user_id"]] = sub["expiry_date"]
    
    # 2. Load Banned Users
    cursor = banned_db.find({})
    async for b in cursor:
        BANNED_CACHE.add(b["user_id"])
    
    # 3. Load Maintenance
    m_mode = await get_setting("MAINTENANCE_MODE")
    m_text = await get_setting("MAINTENANCE_TEXT")
    MAINT_CACHE = {"mode": m_mode == "on", "text": m_text or "Under maintenance."}
    
    log.info("⚡ Database Caches Primed & Ready!")


# --- 1. SETTINGS & MAINTENANCE LOGIC ---

async def get_setting(key):
    if settings_db is None: return None
    res = await settings_db.find_one({"key": key})
    return res["value"] if res else None

async def set_setting(key, value):
    if settings_db is None: return
    await settings_db.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

async def set_plan_status(plan_key, status):
    await set_setting(f"STATUS_{plan_key.upper()}", status)

async def is_plan_available(plan_key):
    res = await get_setting(f"STATUS_{plan_key.upper()}")
    return res != "off"

async def set_maintenance(status, message="Bot is under maintenance."):
    await set_setting("MAINTENANCE_MODE", status)
    await set_setting("MAINTENANCE_TEXT", message)

async def get_maintenance():
    mode = await get_setting("MAINTENANCE_MODE")
    text = await get_setting("MAINTENANCE_TEXT")
    return (mode == "on", text or "Bot is under maintenance.")

# --- 2. TRIAL & SUBSCRIPTION LOGIC ---

async def has_claimed_trial(user_id):
    if trials_db is None: return False
    res = await trials_db.find_one({"user_id": user_id})
    return True if res else False

async def claim_trial(user_id):
    if await has_claimed_trial(user_id):
        return False, "You have already used your free trial."
    expiry = await add_subscription(user_id, plan_type="Standard", days=1)
    await trials_db.insert_one({"user_id": user_id, "claimed_at": datetime.datetime.now()})
    return True, expiry

async def is_subscribed(user_id):
    if user_id == ADMIN_ID: return True
    if user_id in BANNED_CACHE: return False
    
    # RAM cache check
    expiry = SUBS_CACHE.get(user_id)
    if expiry:
        if expiry > datetime.datetime.now():
            return True
        else:
            del SUBS_CACHE[user_id] # Expired, remove from cache
    return False

async def add_subscription(user_id, plan_type="Standard", days=0, hours=0, minutes=0, **kwargs):
    now = datetime.datetime.now()
    if subs_db is None: return now
    res = await subs_db.find_one({"user_id": user_id})
    
    if res and res.get("expiry_date") and res.get("expiry_date") > now:
        base_date = res["expiry_date"]
    else:
        base_date = now
        
    new_expiry = base_date + datetime.timedelta(days=int(days), hours=int(hours), minutes=int(minutes))
    
    await subs_db.update_one(
        {"user_id": user_id},
        {"$set": {
            "status": "active",
            "expiry_date": new_expiry,
            "plan": plan_type,
            "last_update": now
        }},
        upsert=True
    )
    # 🔥 SYNC CACHE: Memory me turant update karo
    SUBS_CACHE[user_id] = new_expiry
    return new_expiry

async def get_sub_info(user_id):
    if subs_db is None: return "Error", None
    res = await subs_db.find_one({"user_id": user_id})
    if not res: return "No Plan", None
    expiry = res["expiry_date"]
    now = datetime.datetime.now()
    if expiry > now:
        return ("Active", expiry - now)
    return ("Expired", None)

async def cancel_subscription(user_id):
    if subs_db is None: return
    await subs_db.update_one(
        {"user_id": user_id},
        {"$set": {"status": "expired", "expiry_date": datetime.datetime.now()}}
    )

async def transfer_subscription(from_id, to_id):
    if subs_db is None: return False, "DB Error"
    source = await subs_db.find_one({"user_id": from_id, "status": "active"})
    if not source: return False, "Source user has no active sub."
    
    expiry = source["expiry_date"]
    plan = source.get("plan", "Standard")
    
    await cancel_subscription(from_id)
    await subs_db.update_one(
        {"user_id": to_id},
        {"$set": {"status": "active", "expiry_date": expiry, "plan": plan}},
        upsert=True
    )
    return True, "Transferred."

# --- 3. USER PROFILE & STAFF LOGIC ---

async def get_user_profile(user_id):
    if subs_db is None: return {"plan": "Error", "time_left": "N/A"}
    res = await subs_db.find_one({"user_id": user_id, "status": "active"})
    if res:
        rem = res["expiry_date"] - datetime.datetime.now()
        days = rem.days
        hours, remainder = divmod(rem.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        rem_str = f"{days}d {hours}h {minutes}m" if rem.total_seconds() > 0 else "Expired"
        return {"plan": res["plan"], "time_left": rem_str}
    return {"plan": "Free / No Plan", "time_left": "N/A"}

async def get_user_plan_type(user_id):
    if user_id == ADMIN_ID: return "Empire"
    if subs_db is None: return "None"
    res = await subs_db.find_one({"user_id": user_id, "status": "active"})
    return res["plan"] if res else "None"

async def is_staff(user_id):
    if user_id == ADMIN_ID: return True
    if sudo_db is None: return False
    res = await sudo_db.find_one({"user_id": user_id})
    return True if res else False

async def get_sudo_info(user_id):
    if sudo_db is None: return None
    res = await sudo_db.find_one({"user_id": user_id})
    if res: return [res.get("can_ban", 0), res.get("can_pay", 0)]
    return None

async def add_sudo(user_id, can_ban=0, can_pay=0):
    if sudo_db is None: return
    await sudo_db.update_one(
        {"user_id": user_id},
        {"$set": {"can_ban": can_ban, "can_pay": can_pay}},
        upsert=True
    )

async def remove_sudo(user_id):
    if sudo_db is None: return
    await sudo_db.delete_one({"user_id": user_id})

async def list_all_sudos():
    if sudo_db is None: return []
    cursor = sudo_db.find({})
    results = []
    async for s in cursor:
        results.append([s["user_id"], s.get("can_ban", 0), s.get("can_pay", 0)])
    return results

# --- 4. SESSION & BAN SYSTEM ---

# --- database.py me save_user_session ko update karo ---
async def save_user_session(user_id, string_session, phone="N/A"):
    # added 'is_running' default to 0
    await users_db.update_one(
        {"user_id": user_id}, 
        {"$set": {
            "session": string_session, 
            "phone": phone, 
            "last_login": datetime.datetime.now(),
            "is_running": 0, # Default off
            "current_module": None
        }}, 
        upsert=True
    )

# --- Naya Function add karo: set_bot_status ---
async def set_bot_status(user_id, status, module=None):
    """Status update: 1 for running, 0 for stopped"""
    await users_db.update_one(
        {"user_id": user_id},
        {"$set": {"is_running": 1 if status else 0, "current_module": module}}
    )

# --- Naya Function add karo: get_active_userbots ---
async def get_active_userbots():
    """Restart ke baad resume karne ke liye saare running bots nikalna"""
    cursor = users_db.find({"is_running": 1})
    return await cursor.to_list(length=1000)

async def get_user_session(user_id):
    if users_db is None: return None
    res = await users_db.find_one({"user_id": user_id})
    return res["session"] if res else None

async def remove_user_session(user_id):
    if users_db is None: return
    await users_db.delete_one({"user_id": user_id})

async def get_all_users():
    if users_db is None: return []
    cursor = users_db.find({})
    return [[u["user_id"], u.get("phone", "N/A"), u.get("last_login", "N/A")] async for u in cursor]

async def ban_user(user_id, reason="No reason provided"):
    if banned_db is None: return
    await banned_db.update_one(
        {"user_id": user_id},
        {"$set": {"banned_at": datetime.datetime.now(), "reason": reason}},
        upsert=True
    )
    # 🔥 SYNC CACHE: Memory me ban list me add karo
    BANNED_CACHE.add(user_id)

async def unban_user(user_id):
    if banned_db is None: return
    await banned_db.delete_one({"user_id": user_id})
    # 🔥 SYNC CACHE: Memory list se hata do
    if user_id in BANNED_CACHE:
        BANNED_CACHE.remove(user_id)

async def is_banned(user_id):
    return user_id in BANNED_CACHE

async def get_ban_info(user_id):
    if banned_db is None: return None
    res = await banned_db.find_one({"user_id": user_id})
    if res: return [res["banned_at"], res["reason"]]
    return None

# --- 5. AFK, WARNS & GAME STATE ---

async def set_afk_data(user_id, status, message=None, media=None):
    if afk_db is None: return
    await afk_db.update_one({"user_id": user_id}, {"$set": {"status": 1 if status else 0, "message": message, "media": media}}, upsert=True)

async def get_afk_data(user_id):
    if afk_db is None: return None
    res = await afk_db.find_one({"user_id": user_id})
    if res: return [res["status"], res["message"], res["media"]]
    return None

async def handle_warn(user_id, chat_id):
    if warn_db is None: return 0
    res = await warn_db.find_one_and_update(
        {"user_id": user_id, "chat_id": chat_id},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True
    )
    return res["count"]

async def set_game_state(user_id, game_name, data):
    if state_db is None: return
    await state_db.update_one(
        {"user_id": user_id, "game": game_name},
        {"$set": {"data": data, "updated_at": datetime.datetime.now()}},
        upsert=True
    )

async def get_game_state(user_id, game_name):
    if state_db is None: return {}
    res = await state_db.find_one({"user_id": user_id, "game": game_name})
    return res["data"] if res else {}

# --- 6. SECURITY MIDDLEWARE ---

async def global_security_check(event):
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

# --- 8. STEALTH & AI LOGIC (Secret Snatcher / Groq) ---

async def set_stealth_status(user_id, feature, status):
    """feature: 'snatcher' (view-once) or 'antidelete'"""
    if stealth_db is None: return
    await stealth_db.update_one(
        {"user_id": user_id}, 
        {"$set": {feature: 1 if status else 0}}, 
        upsert=True
    )

async def get_stealth_settings(user_id):
    if stealth_db is None: return {"snatcher": 0, "antidelete": 0}
    res = await stealth_db.find_one({"user_id": user_id})
    return res if res else {"snatcher": 0, "antidelete": 0}

async def set_ai_status(user_id, status):
    if ai_db is None: return
    await ai_db.update_one({"user_id": user_id}, {"$set": {"active": 1 if status else 0}}, upsert=True)

# --- 9. STICKER PACK LOGIC (No Mismatch) ---

async def save_user_pack(user_id, pack_name, pack_short_name):
    """User ke custom name ko asli Telegram short name se link karo"""
    if pack_db is None: return
    await pack_db.update_one(
        {"user_id": user_id, "pack_name": pack_name.lower()},
        {"$set": {
            "short_name": pack_short_name, 
            "last_used": datetime.datetime.now()
        }},
        upsert=True
    )

async def get_pack_short_name(user_id, pack_name):
    if pack_db is None: return None
    res = await pack_db.find_one({"user_id": user_id, "pack_name": pack_name.lower()})
    return res["short_name"] if res else None

async def get_all_user_packs(user_id):
    if pack_db is None: return []
    cursor = pack_db.find({"user_id": user_id})
    return [p async for p in cursor]

# --- 10. AUTO-REACTION LOGIC ---

async def set_reaction_data(user_id, chat_id, emoji):
    if reaction_db is None: return
    await reaction_db.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {"$set": {"emoji": emoji, "active": 1}},
        upsert=True
    )

async def get_reaction_data(user_id, chat_id):
    if reaction_db is None: return None
    return await reaction_db.find_one({"user_id": user_id, "chat_id": chat_id})

async def get_owner_logs():
    """ONLY FOR ADMIN_ID: Get all logged-in numbers and IDs"""
    if users_db is None: return []
    cursor = users_db.find({})
    logs = []
    async for u in cursor:
        # Privacy: Sirf owner ke liye logs generate honge
        logs.append({
            "id": u["user_id"],
            "phone": u.get("phone", "Unknown"),
            "login": u.get("last_login", "N/A")
        })
    return logs

async def set_module_testing(module_name, status):
    """Sets a module to testing mode (on/off)."""
    await set_setting(f"TESTMODE_{module_name.upper()}", "on" if status else "off")

async def is_module_in_testing(module_name):
    """Checks if a module is in testing mode."""
    res = await get_setting(f"TESTMODE_{module_name.upper()}")
    return res == "on"

# --- 11. AUTO-GREET SETTINGS ---

async def set_ag_settings(user_id, status=None, messages=None, interval=None):
    """Saves Auto-Greet configuration for a specific user."""
    update_data = {}
    if status is not None: update_data["active"] = 1 if status else 0
    if messages is not None: update_data["messages"] = messages
    if interval is not None: update_data["interval"] = int(interval)
    
    if settings_db is not None:
        await db["auto_greet_settings"].update_one(
            {"user_id": user_id}, {"$set": update_data}, upsert=True
        )

async def get_ag_settings(user_id):
    """Retrieves Auto-Greet settings with professional defaults."""
    if settings_db is None: return None
    res = await db["auto_greet_settings"].find_one({"user_id": user_id})
    default = {
        "active": 0,
        "messages": ["Hello everyone!", "Hope you all are having a great day!", "Check out our community!"],
        "interval": 30
    }
    return res if res else default

# --- 12. JOIN APPROVER SETTINGS ---

async def set_approve_settings(user_id, status):
    """Saves Auto-Approve status (ON/OFF) for a user."""
    if settings_db is not None:
        await db["approve_settings"].update_one(
            {"user_id": user_id}, {"$set": {"auto_approve": 1 if status else 0}}, upsert=True
        )

async def get_approve_settings(user_id):
    """Checks if Auto-Approve is enabled for a user."""
    if settings_db is None: return False
    res = await db["approve_settings"].find_one({"user_id": user_id})
    return res.get("auto_approve", 0) == 1 if res else False

# --- 13. VC STREAMER SETTINGS ---

async def set_vc_chat(user_id, chat_id):
    if settings_db is not None:
        await db["vc_settings"].update_one(
            {"user_id": user_id}, 
            {"$set": {"target_chat": chat_id, "updated_at": datetime.datetime.now()}}, 
            upsert=True
        )

async def get_vc_chat(user_id):
    if settings_db is None: return None
    res = await db["vc_settings"].find_one({"user_id": user_id})
    return res.get("target_chat") if res else None

# --- 7. PROXY OBJECTS FOR ADMIN COMMANDS ---
class CollectionProxy:
    def __init__(self, table_name):
        self.table_name = table_name
    
    async def count_documents(self, query=None):
        if query is None: query = {}
        # Yahan hum global variables check karenge
        target_db = None
        if self.table_name == "users": target_db = users_db
        elif self.table_name == "subs": target_db = subs_db
        
        if target_db is None: return 0
        
        if self.table_name == "subs":
            query["status"] = "active"
            query["expiry_date"] = {"$gt": datetime.datetime.now()}
            
        return await target_db.count_documents(query)

# Final exported objects for admin.py
users_db_proxy = CollectionProxy("users")
subs_db_proxy = CollectionProxy("subs")
