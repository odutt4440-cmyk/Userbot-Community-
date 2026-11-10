from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot
from database import global_security_check

# --- 1. ENTRY POINT (/commands) ---

@bot.on_message(filters.command("commands") & filters.private)
async def commands_handler(client, message):
    # Use Kurigram-compatible security check from start.py
    from plugins.start import global_security_check as start_security_check
    if not await start_security_check(message): return

    text = (
        "📖 **EMPIRE COMMAND CENTER**\n\n"
        "Welcome to the Master Guide. Select a category below to explore all commands "
        "available in your Userbot Suite. Use these in your **Saved Messages**."
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ Management", callback_data="cmd_manage", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("🥳 Fun Suite", callback_data="cmd_fun", style=ButtonStyle.SUCCESS)
        ],
        [InlineKeyboardButton("🎮 Game Solvers", callback_data="cmd_games", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="start_back", style=ButtonStyle.DANGER)]
    ])
    await message.reply(text, reply_markup=buttons)

# --- 2. MANAGEMENT CATEGORY ---

@bot.on_callback_query(filters.regex("^cmd_manage$"))
async def help_manage(client, query):
    text = (
        "🛡️ **Userbot Management Modules**\n\n"
        "**Group Admin Tools:**\n"
        "• `.ban` - Reply to a user to ban them.\n"
        "• `.mute` - Reply to a user to mute them.\n"
        "• `.warn` - Give a warning (3 warns = Auto Ban).\n"
        "• `.banall` - Clean a group (Bans all non-admins).\n\n"
        "**General Info Tools:**\n"
        "• `.id` - Get Chat/User ID.\n"
        "• `.info` - Reply to see full user details.\n\n"
        "**📢 Tagging Tools:**\n"
        "• `.tagall <msg>` - Mention everyone in the group.\n"
        "• `.stopall` - Stop the active tag process.\n"
        "• `.tagdelay <sec>` - Set delay (Default 3s).\n\n"
        "**🕵️ Stealth Monitor:**\n"
        "• `.snatcher on/off` — Auto-save view-once media.\n"
        "• `.antidelete on/off` — Log deleted messages in Saved Msg.\n\n"
        "✅ **JOIN APPROVER:**\n"
        "• `.approveall` — Fast batch approval (200 users/batch).\n"
        "• `.approveallx` — Continuous auto-mode (Full cleanup).\n"
        "• `.autoapprove on/off` — Real-time auto-accept for new members.\n"
        "• `.approve [ID]` — Approve a specific user by their ID."
    )
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="cmd_back_main", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# --- 3. FUN CATEGORY ---

@bot.on_callback_query(filters.regex("^cmd_fun$"))
async def help_fun(client, query):
    text = (
        "🥳 **USERBOT FUN SUITE**\n\n"
        "👤 **IDENTITY & AFK:**\n"
        "• `.clone` — Copy a profile. | `.revert` — Restore.\n"
        "• `.afk [msg]` — Set auto-reply for DMs/Mentions.\n\n"
        "🖼️ **STICKERS & MEMIFY:**\n"
        "• `.kang [name]` — Create a new sticker pack.\n"
        "• `.add [name]` — Add sticker to your existing pack.\n"
        "• `.pack [name]` — Get your custom pack link.\n"
        "• `.delsticker [name]` — Remove sticker from pack.\n"
        "• `.delpack [name]` — Delete full pack from Telegram.\n"
        "• `.mm [Top] ; [Bottom]` — Create meme from media.\n\n"
        "🎭 **AUTO-REACTION:**\n"
        "• `.autoreact [emoji]` — Target user (Reply) or GC.\n"
        "• `.stopreact` — Stop auto-reactions in chat.\n\n"
        "✨ **EXTRA FUN (ASCII & Loops):**\n"
        "• `.hi` | `.hello` | `.bear` | `.fuck` | `.gn` | `.gm` — Arts.\n"
        "• `.hehe` | `.sad` | `.heart` | `.sleep` — Emoji Loops.\n"
        "• `.hack` — Hacking Anim. | `.greet` — Random Wish.\n"
        "• `.alive` — Check your userbot online status.\n\n"
        "⚔️ **RAID SUITE (Aggressive):**\n"
        "• `.spam [count] [text]` — High-speed message spam.\n"
        "• `.raid [count] [target]` — Insult raid on a user.\n"
        "• `.replyraid` (Reply) — Auto-insult reply engine.\n"
        "• `.delayraid [delay] [count] [target]` — Safe raid.\n"
        "• `.stop` — Kill raids. | `.clear` — Delete 100 msgs.\n"
        "• `.photo` — Download all profile photos of a user.\n\n"
        "🎙️ **VC STREAMER (SaaS Engine):**\n"
        "• `.vctarget [link/username/id]` — Lock a group for streaming.\n"
        "• `.vcstream` — Reply to audio in Saved Msg to go live (queues if busy).\n"
        "• `.vcqueue` — Show current track & queue list.\n"
        "• `.vcskip` — Skip to the next queued track.\n"
        "• `.vcstop` — Stop stream, leave VC & clear cache.\n"
        "• `.vchelp` — Quick VC command guide.\n\n"
        "🤖 **AUTO-GREETING (Promoter):**\n"
        "• `.agon` — Enable periodic messaging.\n"
        "• `.agoff` — Disable the promoter.\n"
        "• `.agset [Msg1 | Msg2]` — Set custom messages (Use | to split).\n"
        "• `.agtime [Min]` — Set interval (Min: 10m)."
    )
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="cmd_back_main", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# --- 4. GAMES CATEGORY ---

@bot.on_callback_query(filters.regex("^cmd_games$"))
async def help_games(client, query):
    text = (
        "🎮 **Userbot Game Modules**\n\n"
        "Deploy high-speed solvers. Use these commands in saved message once active:\n\n"
        "🧩 **WordSeek Solver: (@WordSeekBot)**\n"
        "• `.ws on` | `.ws off` — Toggle Solver\n"
        "• `.ws loop on` | `.ws loop off` — Auto Restart\n"
        "• `.ws delay 0.5 1.5` — Set Min/Max speed\n\n"
        "📝 **Wordly Master: (@WordlyGamingBot @Wordgamezbot)**\n"
        "• `.won` | `.woff` — Toggle Automation\n"
        "• `.wloop on` | `.wloop off` — Auto New Game\n"
        "• `.wdelay 0.5` — Set Typing Delay\n"
        "• `.wstatus` — Check Round Stats\n\n"
        "🐙 **Octopus Engine: (@OctopusEN_Bot)**\n"
        "• `.octo on`- before starting game command\n"
        "• after starting choose rounds and mode\n"
        "• `.octo off`- it will stop the bot\n"
        "• `.octo delay 2.6 3.2` — Adjust Timing\n\n"
        "⛓️ **WordChain Pro: (@on9wordchainbot)**\n"
        "• `on1`, `on2`... — Join specific game ID.\n"
        "• `ban y` | `ban y onx` — Ban letter ending from y or any letter.\n"
        "• `unban y`| `unban y onx` — Unban letter ending.\n"
        "• `spam random` | `spam <char>` — Ending mode\n"
        "• `spam longest` — Spam longest words\n"
        "• `settime 1 3 onx` — Set Min/Max delay\n"
        "• `status onx` — Check status for specific GC\n"
        "• `status` — Check all active games\n\n"
        "🧩 **WORDLE PRO (@wordlegameprobot):**\n"
        "• `.wd on/off` — Toggle Master Solver.\n"
        "• `.wd loop on/off` — Auto-start rounds.\n"
        "• `.wd delay 1.0 2.5` — Set Typing Delay.\n"
        "👉 _Supports 3, 4, 5, 6, 7 letter modes automatically!_"
    )
    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="cmd_back_main", style=ButtonStyle.DANGER)]
        ])
    )
    await query.answer()

# --- 5. NAVIGATION HELPERS ---

@bot.on_callback_query(filters.regex("^cmd_back_main$"))
async def help_back(client, query):
    text = (
        "📖 **EMPIRE COMMAND CENTER**\n\n"
        "Select a category below to explore all commands."
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛡️ Management", callback_data="cmd_manage", style=ButtonStyle.PRIMARY),
            InlineKeyboardButton("🥳 Fun Suite", callback_data="cmd_fun", style=ButtonStyle.SUCCESS)
        ],
        [InlineKeyboardButton("🎮 Game Solvers", callback_data="cmd_games", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="start_back", style=ButtonStyle.DANGER)]
    ])
    await query.message.edit_text(text, reply_markup=buttons)
    await query.answer()

# NOTE: /help handler has been REMOVED from this file.
# It already exists in plugins/start.py, so keeping it here caused duplicate replies.
