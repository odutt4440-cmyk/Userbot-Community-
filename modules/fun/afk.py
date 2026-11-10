import asyncio
import os
from telethon import events
from database import set_afk_data, get_afk_data

# --- FONT ENGINE ---
def stylize(text):
    """Normal text ko stylized font me badalne ke liye"""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    # Lowercase -> Small Caps | Uppercase -> Bold Mathematical
    fancy = "ᴧʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"
    table = str.maketrans(alphabet, fancy)
    return text.translate(table)

def register(client):
    client.afk_active = False
    client.afk_message = "I am currently offline."
    client.afk_media = None 

    # --- 1. SET AFK COMMAND ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.afk(?:\s+(.*))?'))
    async def set_afk_handler(event):
        reason_raw = event.pattern_match.group(1) or "I am currently offline. Please leave a message!"
        
        # Stylize the reason
        reason = stylize(reason_raw)
        media = None
        
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg.media:
                media = reply_msg.media 
        
        client.afk_active = True
        client.afk_message = reason
        client.afk_media = media
        
        await set_afk_data(event.sender_id, True, reason, str(media) if media else None)
        
        header = stylize("AFK Mode Activated!")
        reply_label = stylize("Auto-Reply:")
        
        status_text = f"💤 **{header}**\n\n**{reply_label}** `{reason}`"
        if media:
            status_text += f"\n✅ {stylize('Media attached to reply.')}"
            
        status_msg = await event.respond(status_text)
        
        try: await event.delete()
        except: pass
        
        await asyncio.sleep(10)
        try: await status_msg.delete()
        except: pass

    # --- 2. DISABLE AFK ---
    @client.on(events.NewMessage(outgoing=True))
    async def disable_afk_on_activity(event):
        if not client.afk_active: return
        if event.text.startswith('.'): return
        
        me = await client.get_me()
        if event.chat_id == me.id: return

        client.afk_active = False
        await set_afk_data(me.id, False)
        
        msg = stylize("Back Online! AFK mode has been disabled.")
        back_msg = await event.respond(f"✅ **{msg}**")
        await asyncio.sleep(5)
        try: await back_msg.delete()
        except: pass

    # --- 3. AUTO REPLY LOGIC ---
    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def afk_auto_reply(event):
        if client.afk_active:
            sender = await event.get_sender()
            if not sender or getattr(sender, 'bot', False): return

            await asyncio.sleep(1) 
            
            # Stylized Labels
            header = stylize("𝐀ᴜᴛᴏ-𝐑ᴇᴘʟʏ:")
            footer = stylize("𝐏ᴏᴡᴇʀᴇᴅ ʙʏ 𝐔sᴇʀʙᴏᴛ 𝐂ᴏᴍᴍᴜɴɪᴛʏ")

            # Final Stylized Output
            final_reply = (
                f" {header}\n"
                f"{client.afk_message}\n\n"
                f"{footer}"
            )

            await event.reply(final_reply)

            if client.afk_media:
                await client.send_file(event.chat_id, client.afk_media, reply_to=event.id)

    # --- STARTUP SYNC ---
    async def startup_sync():
        me = await client.get_me()
        data = await get_afk_data(me.id)
        if data and data[0] == 1:
            client.afk_active = True
            client.afk_message = data[1] or stylize("I am away.")
    
    asyncio.create_task(startup_sync())
