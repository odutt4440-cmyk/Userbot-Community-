import asyncio
import re
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot
# Telethon imports (session generate karne ke liye)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    ApiIdInvalidError, 
    PhoneNumberInvalidError, 
    PhoneCodeInvalidError, 
    SessionPasswordNeededError,
    FloodWaitError
)
from config import API_ID, API_HASH
from database import save_user_session

# User state tracker
GEN_DATA = {}

# --- 1. START GENERATION ---
@bot.on_callback_query(filters.regex("^gen_string_internal$"))
async def start_string_gen(client, query):
    if query.message.chat.type != "private":
        await query.answer("⚠️ This tool only works in Private DM.", show_alert=True)
        return

    user_id = query.from_user.id
    GEN_DATA[user_id] = {"step": "phone"}
    
    await query.message.edit_text(
        "🔑 **String Session Generator**\n\n"
        "I will help you generate a Telethon String Session securely. "
        "The string will be automatically linked to your account.\n\n"
        "**Step 1:** Please send your **Phone Number** with country code.\n"
        "Example: `+919876543210` or `+1...`",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="start_back", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# --- 2. INPUT HANDLER (Kurigram) ---
@bot.on_message(filters.private & filters.text)
async def handle_gen_input(client, message):
    user_id = message.from_user.id
    if user_id not in GEN_DATA or message.text.startswith('/'):
        return

    state = GEN_DATA[user_id]
    step = state["step"]
    text = message.text.strip()

    # --- STEP 1: RECEIVE PHONE ---
    if step == "phone":
        clean_phone = re.sub(r'[\s\-()]', '', text)
        
        if not clean_phone.startswith('+'):
            await message.reply("⚠️ **Format Error:** Please start the number with `+` followed by country code.\nExample: `+1...` or `+91...` ")
            return

        state["phone"] = clean_phone
        msg = await message.reply("⏳ Connecting to Telegram secure servers...")
        
        # Telethon client (session generation ke liye)
        tmp_client = TelegramClient(
            StringSession(), 
            API_ID, 
            API_HASH,
            device_model="iPhone 15 Pro Max",
            system_version="17.5.1",
            app_version="10.14.2",
            lang_code="en",
            system_lang_code="en-US"
        )
        
        await tmp_client.connect()
        
        try:
            hash_obj = await tmp_client.send_code_request(clean_phone)
            state["client"] = tmp_client
            state["hash"] = hash_obj.phone_code_hash
            state["step"] = "otp"
            
            await msg.edit_text(
                "✅ **OTP Sent Successfully!**\n\n"
                f"📱 **Target:** `{clean_phone}`\n\n"
                "**Important:** Check your Telegram App (the official one) for the code first. "
                "If not there, check SMS.\n\n"
                "👉 Send code like this: `1 2 3 4 5` (spaces mandatory)."
            )
        except FloodWaitError as f:
            await msg.edit_text(f"❌ **Telegram Limit Hit:**\nPlease wait for `{f.seconds}` seconds. This is a Telegram security restriction.")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
        except PhoneNumberInvalidError:
            await msg.edit_text("❌ **Invalid Number:** The phone number you entered is not recognized by Telegram.")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
        except Exception as e:
            await msg.edit_text(f"❌ **Error:** `{str(e)}` \nPlease try again later.")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]

    # --- STEP 2: RECEIVE OTP ---
    elif step == "otp":
        otp = text.replace(" ", "")
        tmp_client = state["client"]
        phone = state["phone"]
        code_hash = state["hash"]
        
        msg = await message.reply("⏳ Verifying security code...")
        
        try:
            await tmp_client.sign_in(phone, otp, phone_code_hash=code_hash)
            string = tmp_client.session.save()
            
            await save_user_session(user_id, string, phone)
            
            # login.py ki waiting list se user ko hata do
            try:
                from plugins.login import WAITING_FOR_STR
                if user_id in WAITING_FOR_STR:
                    del WAITING_FOR_STR[user_id]
            except:
                pass
            
            success_text = (
                "🎯 **Session Successfully Linked!**\n\n"
                f"📱 **Phone:** `{phone}`\n"
                f"🔑 **String:** `{string}`\n\n"
                "✅ Your account is now connected. You can now activate your userbot modules."
            )
            await msg.edit_text(success_text, reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Go to Modules", callback_data="modules_main", style=ButtonStyle.PRIMARY)]
            ]))
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
            
        except SessionPasswordNeededError:
            state["step"] = "password"
            await msg.edit_text("🔐 **Two-Step Verification (2FA) Detected.**\nPlease send your account cloud password below.")
        except PhoneCodeInvalidError:
            await msg.edit_text("❌ **Invalid OTP!**\nPlease make sure you sent the correct code with spaces.")
        except Exception as e:
            await msg.edit_text(f"❌ **Auth Error:** `{str(e)}` ")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]

    # --- STEP 3: RECEIVE 2FA PASSWORD ---
    elif step == "password":
        tmp_client = state["client"]
        phone = state["phone"]
        msg = await message.reply("⏳ Verifying 2FA Password...")
        
        try:
            await tmp_client.sign_in(password=text)
            string = tmp_client.session.save()
            
            await save_user_session(user_id, string, phone)
            
            try:
                from plugins.login import WAITING_FOR_STR
                if user_id in WAITING_FOR_STR:
                    del WAITING_FOR_STR[user_id]
            except:
                pass
            
            await msg.edit_text(
                "🎯 **Session Successfully Linked (2FA)!**\n\n"
                f"📱 **Phone:** `{phone}`\n"
                f"🔑 **String:** `{string}`\n\n"
                "You are all set! Open modules to deploy your bot.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⚙️ Go to Modules", callback_data="modules_main", style=ButtonStyle.PRIMARY)]
                ])
            )
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
        except Exception as e:
            await msg.edit_text(f"❌ **Password Error:** `{str(e)}` \nPlease try again.")
