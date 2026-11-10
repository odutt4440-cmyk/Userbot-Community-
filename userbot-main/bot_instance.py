from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

# Ye file sirf bot object ko initialize karegi (Kurigram/Pyrogram fork)
# bot naam same rakha hai taaki baaki plugins me `from bot_instance import bot` waise hi kaam kare
bot = Client(
    name="bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=False,
    workers=8,
    sleep_threshold=60
)
