from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

# Kurigram (Pyrogram fork) client — manager bot ke liye
# bot naam same rakha hai taaki plugins mein `from bot_instance import bot` waise hi kaam kare
bot = Client(
    name="bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=8,
    sleep_threshold=60
)
