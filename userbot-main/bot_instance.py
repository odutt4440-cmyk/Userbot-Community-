from telethon import TelegramClient
from config import API_ID, API_HASH

# Ye file sirf bot object ko initialize karegi
bot = TelegramClient('bot_session', API_ID, API_HASH)
