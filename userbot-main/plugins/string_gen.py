import asyncio
import re
from bot_instance import bot
from telethon import events, Button, TelegramClient
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
@bot.on(events.CallbackQuery(data="gen_string_internal"))
async def start_string_gen(event):
    if not event.is_private:
        await event.answer("⚠️ This tool only works in Private DM.", alert=True)
        return

    user_id = event.sender_id
    GEN_DATA[user_id] = {"step": "phone"}
    
    await event.edit(
        "🔑 **String Session Generator**\n\n"
        "I will help you generate a Telethon String Session securely. "
        "The string will be automatically linked to your account.\n\n"
        "**Step 1:** Please send your **Phone Number** with country code.\n"
        "Example: `+919876543210` or `+1...`",
        buttons=[Button.inline("❌ Cancel", data="start_back")]
    )

# --- 2. INPUT HANDLER ---
@bot.on(events.NewMessage)
async def handle_gen_input(event):
    if not event.is_private:
        return

    user_id = event.sender_id
    if user_id not in GEN_DATA or event.text.startswith('/'):
        return

    state = GEN_DATA[user_id]
    step = state["step"]
    text = event.raw_text.strip()

    # --- STEP 1: RECEIVE PHONE (With International Fix) ---
    if step == "phone":
        # 🔥 CLEANER: Remove all spaces, dashes, and brackets
        clean_phone = re.sub(r'[\s\-()]', '', text)
        
        # Ensure it starts with + (Telegram strict rule)
        if not clean_phone.startswith('+'):
            await event.reply("⚠️ **Format Error:** Please start the number with `+` followed by country code.\nExample: `+1...` or `+91...` ")
            return

        state["phone"] = clean_phone
        msg = await event.reply("⏳ Connecting to Telegram secure servers...")
        
        # 🔥 DEVICE SIMULATION: Reduces 'High Risk' flags for International OTP
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
            # Code request
            hash_obj = await tmp_client.send_code_request(clean_phone)
            state["client"] = tmp_client
            state["hash"] = hash_obj.phone_code_hash
            state["step"] = "otp"
            
            await msg.edit(
                "✅ **OTP Sent Successfully!**\n\n"
                f"📱 **Target:** `{clean_phone}`\n\n"
                "**Important:** Check your Telegram App (the official one) for the code first. "
                "If not there, check SMS.\n\n"
                "👉 Send code like this: `1 2 3 4 5` (spaces mandatory)."
            )
        except FloodWaitError as f:
            await msg.edit(f"❌ **Telegram Limit Hit:**\nPlease wait for `{f.seconds}` seconds. This is a Telegram security restriction.")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
        except PhoneNumberInvalidError:
            await msg.edit("❌ **Invalid Number:** The phone number you entered is not recognized by Telegram.")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
        except Exception as e:
            await msg.edit(f"❌ **Error:** `{str(e)}` \nPlease try again later.")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]

    # --- STEP 2: RECEIVE OTP ---
    elif step == "otp":
        otp = text.replace(" ", "")
        tmp_client = state["client"]
        phone = state["phone"]
        code_hash = state["hash"]
        
        msg = await event.reply("⏳ Verifying security code...")
        
        try:
            await tmp_client.sign_in(phone, otp, phone_code_hash=code_hash)
            string = tmp_client.session.save()
            
            # --- AUTO SAVE TO DATABASE ---
            await save_user_session(user_id, string, phone)
            
            # 🔥 FIX: login.py ki waiting list se user ko hata do taaki commands kaam karein
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
            await msg.edit(success_text, buttons=[[Button.inline("⚙️ Go to Modules", data="modules_main")]])
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
            
        except SessionPasswordNeededError:
            state["step"] = "password"
            await msg.edit("🔐 **Two-Step Verification (2FA) Detected.**\nPlease send your account cloud password below.")
        except PhoneCodeInvalidError:
            await msg.edit("❌ **Invalid OTP!**\nPlease make sure you sent the correct code with spaces.")
        except Exception as e:
            await msg.edit(f"❌ **Auth Error:** `{str(e)}` ")
            await tmp_client.disconnect()
            del GEN_DATA[user_id]

    # --- STEP 3: RECEIVE 2FA PASSWORD ---
    elif step == "password":
        tmp_client = state["client"]
        phone = state["phone"]
        msg = await event.reply("⏳ Verifying 2FA Password...")
        
        try:
            await tmp_client.sign_in(password=text)
            string = tmp_client.session.save()
            
            # --- AUTO SAVE TO DATABASE ---
            await save_user_session(user_id, string, phone)
            
            # 🔥 FIX: login.py ki waiting list se user ko hata do taaki commands kaam karein
            try:
                from plugins.login import WAITING_FOR_STR
                if user_id in WAITING_FOR_STR:
                    del WAITING_FOR_STR[user_id]
            except:
                pass
            
            await msg.edit(
                "🎯 **Session Successfully Linked (2FA)!**\n\n"
                f"📱 **Phone:** `{phone}`\n"
                f"🔑 **String:** `{string}`\n\n"
                "You are all set! Open modules to deploy your bot.",
                buttons=[[Button.inline("⚙️ Go to Modules", data="modules_main")]]
            )
            await tmp_client.disconnect()
            del GEN_DATA[user_id]
        except Exception as e:
            await msg.edit(f"❌ **Password Error:** `{str(e)}` \nPlease try again.")
