import asyncio
from telethon import events

# --- MODULE REGISTER ---
def register(client):

    # --- 1. ID COMMAND (.id) ---
    @client.on(events.NewMessage(pattern=r'(?i)^\.id'))
    async def get_id(event):
        # 🛡️ Sirf tab chalega jab message AAPKE account se bheja gaya ho
        if not event.out:
            return

        print(f"DEBUG: [.id] Command detected in chat {event.chat_id}") # Terminal check

        try:
            chat_id = event.chat_id
            if event.is_reply:
                reply = await event.get_reply_message()
                user_id = reply.sender_id
                await event.edit(
                    f"👤 **𝐔sᴇʀ 𝐈𝐃:** `{user_id}`\n"
                    f"👥 **𝐂ʜᴧᴛ 𝐈𝐃:** `{chat_id}`"
                )
            else:
                await event.edit(f"👥 **𝐂ʜᴧᴛ 𝐈𝐃:** `{chat_id}`")
        except Exception as e:
            print(f"DEBUG Error ID: {e}")

    # --- 2. INFO COMMAND (.info) ---
    @client.on(events.NewMessage(pattern=r'(?i)^\.info'))
    async def get_info(event):
        if not event.out:
            return

        print(f"DEBUG: [.info] Command detected") # Terminal check

        # Processing message
        status = await event.edit("🔍 **𝐒ᴄᴧɴɴɪɴɢ...**")
        
        try:
            if event.is_reply:
                reply = await event.get_reply_message()
                target = await client.get_entity(reply.sender_id)
            else:
                target = await client.get_entity(event.chat_id)

            # Data Extraction
            first_name = getattr(target, 'first_name', "N/A")
            last_name = getattr(target, 'last_name', "N/A")
            username = f"@{target.username}" if getattr(target, 'username', None) else "None"
            uid = target.id
            is_bot = "Yes" if getattr(target, 'bot', False) else "No"

            info_text = (
                "👤 **𝐔sᴇʀ / 𝐂ʜᴧᴛ 𝐈ɴꜰᴏ**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 **𝐍ᴧᴍᴇ:** {first_name} {last_name if last_name != 'N/A' else ''}\n"
                f"🆔 **𝐈𝐃:** `{uid}`\n"
                f"🔗 **𝐔sᴇʀɴᴧᴍᴇ:** {username}\n"
                f"🤖 **𝐁ᴏᴛ:** {is_bot}\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            await status.edit(info_text)
            
        except Exception as e:
            await status.edit(f"❌ **𝐄ʀʀᴏʀ:** `{str(e)}` ")
