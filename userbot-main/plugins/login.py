from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot 
from database import save_user_session, get_user_session, is_subscribed

try:
    from plugins.string_gen import GEN_DATA
except:
    GEN_DATA = {}

WAITING_FOR_STR = {}

# --- 1. MODULE CLICK HANDLER ---
@bot.on_callback_query(filters.regex(r"^mod_"))
async def login_step_1(client, query):
    user_id = query.from_user.id
    module_name = query.data.replace("mod_", "")
    
    existing_session = await get_user_session(user_id)
    subscribed = await is_subscribed(user_id)
    
    if existing_session:
        status_text = "✅ **Account Linked!**"
        if not subscribed:
            await query.message.edit_text(
                f"{status_text}\nModule: `{module_name.upper()}`\n\n"
                "Your account is connected, but you need an active subscription or trial to start this module.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Pay & Activate", callback_data="pay_now", style=ButtonStyle.PRIMARY)],
                    [InlineKeyboardButton("🎁 Claim 1-Day Trial", callback_data="claim_trial_btn", style=ButtonStyle.SUCCESS)],
                    [InlineKeyboardButton("🔄 Change Session String", callback_data=f"relog_{module_name}", style=ButtonStyle.DANGER)]
                ])
            )
        else:
            await query.message.edit_text(
                f"{status_text}\nModule: `{module_name.upper()}`\n\n"
                "Your account is ready for deployment. Click the button below to fire up the userbot engine!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Activate Now", callback_data=f"activate_{module_name}", style=ButtonStyle.SUCCESS)],
                    [InlineKeyboardButton("🔄 Change Session String", callback_data=f"relog_{module_name}", style=ButtonStyle.DANGER)]
                ])
            )
    else:
        WAITING_FOR_STR[user_id] = module_name
        await query.message.edit_text(
            f"🔑 **Login Required: {module_name.upper()}**\n\n"
            "To run this module, please provide your **Telethon String Session**.\n\n"
            "**Steps:**\n"
            "1. Use the 'Generate String' tool in the main menu.\n"
            "2. Copy the resulting string code.\n"
            "3. Paste and send the string here in this chat.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="start_back", style=ButtonStyle.DANGER)]
            ])
        )
    await query.answer()

# --- 2. RECEIVE STRING HANDLER ---
@bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "commands", "plan", "admin", "modules"]))
async def receive_string(client, message):
    user_id = message.from_user.id
    
    if user_id in GEN_DATA: return

    if user_id in WAITING_FOR_STR:
        if message.text.startswith('/'): return

        raw_text = message.text.strip()
        
        if "🔑 String:" in raw_text:
            string_session = raw_text.split("🔑 String:")[1].split("\n")[0].strip()
        else:
            string_session = raw_text

        if len(string_session) < 50:
            return
        
        module = WAITING_FOR_STR[user_id]
        await save_user_session(user_id, string_session)
        
        subscribed = await is_subscribed(user_id)
        if subscribed:
            await message.reply(
                f"✅ **Session Saved!**\n\n"
                f"Active subscription detected. You can now deploy `{module.upper()}` immediately!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚀 Deploy Bot", callback_data=f"activate_{module}", style=ButtonStyle.SUCCESS)]
                ])
            )
        else:
            await message.reply(
                f"✅ **Session Saved!**\n\n"
                f"Your account is linked. Now just activate your access to start using `{module.upper()}`.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Pay & Activate", callback_data="pay_now", style=ButtonStyle.PRIMARY)],
                    [InlineKeyboardButton("🎁 Claim 1-Day Trial", callback_data="claim_trial_btn", style=ButtonStyle.SUCCESS)]
                ])
            )
        
        del WAITING_FOR_STR[user_id]

# --- 3. RELOG LOGIC ---
@bot.on_callback_query(filters.regex(r"^relog_"))
async def relog(client, query):
    user_id = query.from_user.id
    module = query.data.replace("relog_", "")
    WAITING_FOR_STR[user_id] = module
    await query.message.edit_text(
        "🔄 **Update Session String**\n\n"
        "Please send your new **Telethon String Session** below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data=f"mod_{module}", style=ButtonStyle.PRIMARY)]
        ])
    )
    await query.answer()