import os
from dotenv import load_dotenv

# .env file se data load karne ke liye
load_dotenv()

# --- Telegram API Credentials ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# BotFather se mila hua Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# --- Database Settings ---
MONGO_URL = os.getenv("MONGO_URL", "")

# --- Admin & Security ---
# Tera Telegram User ID (Numeric) - Main Owner
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MUST_JOIN = -1003946512455
CHANNEL_LINK = "https://t.me/darkconsolecommunity" 
# Log Group ID jahan screenshots aayenge aur Sudo users approve karenge
# Ensure it starts with -100 (e.g., -100123456789)
LOG_GROUP = int(os.getenv("LOG_GROUP", "0"))

BACKUP_CHAT = int(os.getenv("BACKUP_CHAT", "0"))

UPI_ID = "sparshbaniya@fam"
PAY_QR = "assets/qr.jpg"
# --- Sudo Users System ---
# .env me IDs aise likho: SUDO_USERS=123456 789012 554433 (space dekar)
sudo_env = os.getenv("SUDO_USERS", "")
SUDO_USERS = [int(x) for x in sudo_env.split()] if sudo_env else []

# Owner (ADMIN_ID) ko hamesha Sudo list me shamil rakha hai
if ADMIN_ID not in SUDO_USERS:
    SUDO_USERS.append(ADMIN_ID)

# --- Bot Customization ---
# Welcome Pic (Local path support)
START_PIC = os.getenv("START_PIC", "assets/start.jpg")
