import os
import asyncio
import logging
from telethon import events, types
from database import get_stealth_settings, set_stealth_status

log = logging.getLogger(__name__)

# --- GLOBAL CACHE ---
# Isme deleted messages ka content temporary store hota hai.
# Multi-userbot environment ke liye ye session-safe hona chahiye.
MSG_CACHE = {} 

def register(client):

    # --- 1. MESSAGE CACHER (Memory Optimization) ---
    @client.on(events.NewMessage)
    async def cacher(event):
        if not event.chat_id: return
        
        # Sirf zarurat ki info store karna taaki RAM load na ho
        MSG_CACHE[event.id] = {
            "text": event.text or "",
            "sender": event.sender_id,
            "chat": event.chat_id,
            "media": event.media if event.media else None,
            "owner": event.sender_id # Kaunsa userbot session hai
        }

        # Cache cleanup: 150 messages ke baad purana delete (Railway safe)
        if len(MSG_CACHE) > 150:
            first_key = next(iter(MSG_CACHE))
            del MSG_CACHE[first_key]

    # --- 2. SECRET SNATCHER (View-Once Capture) ---
    @client.on(events.NewMessage(incoming=True))
    async def snatcher(event):
        # Database se setting uthao
        settings = await get_stealth_settings(event.sender_id)
        if not settings.get("snatcher"): return

        # Check for View-Once Media (TTL check)
        is_view_once = False
        if event.photo and getattr(event.photo, 'ttl_seconds', None):
            is_view_once = True
        elif event.video and getattr(event.video, 'ttl_seconds', None):
            is_view_once = True

        if is_view_once:
            sender = await event.get_sender()
            name = sender.first_name if sender else "Unknown"
            
            # Inform user in Saved Messages
            await client.send_message("me", f"🕵️ **Secret Snatcher Activity!**\nCaptured a view-once media from **{name}** (`{event.sender_id}`)")
            
            # Download media carefully
            path = await event.download_media()
            await client.send_file("me", path, caption="✅ **Recovered Secret Media Successfully**")
            
            if os.path.exists(path): 
                os.remove(path)

    # --- 3. ANTI-DELETE ENGINE ---
    @client.on(events.MessageDeleted)
    async def handler(event):
        # Jab Telegram delete event bhejta hai, toh wo sirf message ID bhejta hai
        for msg_id in event.deleted_ids:
            if msg_id in MSG_CACHE:
                cached = MSG_CACHE[msg_id]
                
                # Setting check (Settings User ID se fetch karni hai)
                # Note: Session owner ki settings check honi chahiye
                me = await client.get_me()
                settings = await get_stealth_settings(me.id)
                
                if not settings.get("antidelete"): 
                    continue

                # Formatting Log
                chat_info = f"Chat ID: `{cached['chat']}`"
                log_text = (
                    f"🗑️ **Anti-Delete Detection!**\n\n"
                    f"👤 **Sender:** `{cached['sender']}`\n"
                    f"📍 **Location:** {chat_info}\n"
                    f"💬 **Content:** {cached['text'] if cached['text'] else '[No Text/Media Only]'}"
                )
                
                await client.send_message("me", log_text)
                
                # Agar photo/file thi toh usey bhi bhejo
                if cached["media"]:
                    try:
                        await client.send_file("me", cached["media"], caption="📦 **Deleted Media Attachment**")
                    except Exception as e:
                        log.error(f"Anti-Delete Media Send Error: {e}")
                
                # Cleanup cache after logging
                del MSG_CACHE[msg_id]

    # --- 4. COMMANDS TO TOGGLE (User-Friendly UI) ---
    # .snatcher [on/off]
    # .antidelete [on/off]
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.(snatcher|antidelete)(?:\s+(on|off))?'))
    async def stealth_toggle(event):
        feature = event.pattern_match.group(1).lower()
        mode = event.pattern_match.group(2)
        user_id = event.sender_id

        # Status Check (Agar sirf .snatcher likha hai)
        if not mode:
            settings = await get_stealth_settings(user_id)
            is_active = settings.get(feature)
            status_emoji = "✅ Enabled" if is_active else "❌ Disabled"
            return await event.edit(f"🕵️ **Stealth Monitor:**\n⚙️ Feature: `{feature.upper()}`\n📊 Status: **{status_emoji}**")

        # Status Update (on/off)
        mode = mode.lower()
        status_value = 1 if mode == "on" else 0
        
        await set_stealth_status(user_id, feature, status_value)
        
        await event.edit(f"🚀 **Stealth Settings Updated!**\n⚙️ Feature: `{feature.upper()}`\n📊 Mode: **{mode.upper()}**\n\n_Check Saved Messages for logs._")
        
        await asyncio.sleep(4)
        await event.delete()
