import asyncio
import re
import logging
from telethon import events, functions, types
from database import set_reaction_data, get_reaction_data, db

log = logging.getLogger(__name__)

# --- GLOBAL MEMORY ---
REACT_ALL = {}
REACT_TARGETS = {}
OWNER_ID_CACHE = {} # {client_object_id: user_id}

def register(client):
    
    async def sync_reactions():
        try:
            # Cache owner ID once during registration
            me = await client.get_me()
            OWNER_ID_CACHE[id(client)] = me.id
            user_id = me.id
            
            cursor = db["reaction_settings"].find({"user_id": user_id, "active": 1})
            async for doc in cursor:
                c_id = doc["chat_id"]
                emoji = doc["emoji"]
                if user_id not in REACT_ALL: REACT_ALL[user_id] = {}
                REACT_ALL[user_id][c_id] = emoji
                
            log.info(f"🎭 Reactions Synced for {user_id}")
        except Exception as e:
            log.error(f"Sync Error: {e}")

    client.loop.create_task(sync_reactions())

    # --- 1. ENABLE AUTO-REACT ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'(?i)^\.autoreact(?:\s+(.*))?'))
    async def enable_react(event):
        emoji = event.pattern_match.group(1)
        if not emoji:
            return await event.edit("❌ **Error:** Provide an emoji.")

        chat_id = event.chat_id
        user_id = OWNER_ID_CACHE.get(id(client))
        if not user_id: return

        if user_id not in REACT_ALL: REACT_ALL[user_id] = {}
        if user_id not in REACT_TARGETS: REACT_TARGETS[user_id] = {}

        if event.is_reply:
            reply = await event.get_reply_message()
            target_id = reply.sender_id
            if chat_id not in REACT_TARGETS[user_id]: REACT_TARGETS[user_id][chat_id] = {}
            REACT_TARGETS[user_id][chat_id][target_id] = emoji
            if chat_id in REACT_ALL[user_id]: del REACT_ALL[user_id][chat_id]
            await event.edit(f"🎭 **Target Set:** {emoji}")
        else:
            REACT_ALL[user_id][chat_id] = emoji
            await event.edit(f"🎭 **GC Mode:** {emoji}")

        await set_reaction_data(user_id, chat_id, emoji)
        await asyncio.sleep(2)
        await event.delete()

    # --- 2. STOP AUTO-REACT ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'(?i)^\.stopreact'))
    async def stop_react(event):
        chat_id = event.chat_id
        user_id = OWNER_ID_CACHE.get(id(client))
        if not user_id: return
        
        try:
            if user_id in REACT_ALL and chat_id in REACT_ALL[user_id]:
                del REACT_ALL[user_id][chat_id]
            if user_id in REACT_TARGETS and chat_id in REACT_TARGETS[user_id]:
                del REACT_TARGETS[user_id][chat_id]
                
            await db["reaction_settings"].update_one(
                {"user_id": user_id, "chat_id": chat_id},
                {"$set": {"active": 0}}
            )
            await event.edit("🛑 **Auto-Reaction Disabled.**")
        except: pass
        await asyncio.sleep(2)
        await event.delete()

    # --- 3. THE REACTION ENGINE (High Speed) ---
    @client.on(events.NewMessage(incoming=True))
    async def reaction_worker(event):
        user_id = OWNER_ID_CACHE.get(id(client))
        if not user_id: return
        
        chat_id = event.chat_id
        sender_id = event.sender_id
        emoji = None

        if (user_id in REACT_TARGETS and chat_id in REACT_TARGETS[user_id] and 
            sender_id in REACT_TARGETS[user_id][chat_id]):
            emoji = REACT_TARGETS[user_id][chat_id][sender_id]
        elif user_id in REACT_ALL and chat_id in REACT_ALL[user_id]:
            emoji = REACT_ALL[user_id][chat_id]

        if emoji and not event.out:
            try:
                # Custom Emoji Support (For Premium Users)
                reaction = [types.ReactionEmoji(emoticon=emoji)]
                if emoji.isdigit(): # If ID provided for premium emoji
                    reaction = [types.ReactionCustomEmoji(document_id=int(emoji))]

                await client(functions.messages.SendReactionRequest(
                    peer=event.input_chat,
                    msg_id=event.id,
                    add_to_recent=True,
                    reaction=reaction
                ))
            except: pass
