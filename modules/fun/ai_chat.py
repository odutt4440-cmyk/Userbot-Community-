import aiohttp
import asyncio
import json
from telethon import events
from config import GROQ_API_KEY

def register(client):
    # State variables
    client.ai_enabled = False
    client.ai_history = {}  # {chat_id: [messages]}
    
    # Default Persona (Natural, smart, conversational)
    client.ai_prompt = "You are a helpful, smart, and slightly witty human on Telegram. Reply naturally and concisely to the user. Keep your replies short and human-like."
    
    # Groq API settings
    API_URL = "https://api.groq.com/openai/v1/chat/completions"
    
    # 🔥 404 FIX: Model badal diya hai (Ye 100% active model hai)
    MODEL = "llama-3.1-8b-instant" 
    
    # --- CONTROL PANEL (Saved Messages) ---
    @client.on(events.NewMessage(chats='me', pattern=r'(?i)^\.ai'))
    async def ai_controls(event):
        text = event.raw_text.lower().strip()
        
        if text == ".ai on":
            client.ai_enabled = True
            await event.edit("✅ **AI Chat: ONLINE**\nYour userbot will now reply to DMs and Tags.")
            
        elif text == ".ai off":
            client.ai_enabled = False
            await event.edit("❌ **AI Chat: OFFLINE**")
            
        elif text.startswith(".aiprompt "):
            new_prompt = event.raw_text[10:].strip()
            client.ai_prompt = new_prompt
            await event.edit(f"✅ **AI Persona Updated:**\n`{new_prompt}`")
            
        elif text == ".aiclear":
            client.ai_history.clear()
            await event.edit("🧹 **AI Memory Cleared!** (Chat history reset)")
            
        elif text == ".aistatus":
            if not GROQ_API_KEY:
                return await event.edit("❌ **API Key Missing!** Check `config.py`")
            try:
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://api.groq.com/openai/v1/models", headers=headers) as resp:
                        if resp.status == 200:
                            await event.edit("✅ **API Key is VALID and working!**")
                        else:
                            await event.edit(f"❌ **API Key Invalid!** Status: {resp.status}")
            except Exception as e:
                await event.edit(f"❌ **Network Error:** {e}")

    # --- AI MESSAGE HANDLER ---
    @client.on(events.NewMessage(incoming=True))
    async def ai_handler(event):
        if not client.ai_enabled: return
        if not GROQ_API_KEY: return
        
        # Ignore commands or empty messages
        if event.raw_text.startswith('.') or not event.raw_text.strip(): return

        # Trigger conditions: DM, Tag, or Reply to bot
        is_private = event.is_private
        is_tagged = False
        is_reply_to_me = False
        
        me = await client.get_me()
        
        if not is_private:
            if me.username and f"@{me.username.lower()}" in event.raw_text.lower():
                is_tagged = True
            elif event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg and reply_msg.sender_id == me.id:
                    is_reply_to_me = True
                    
        # 🔥 Agar DM nahi hai, aur tag/reply bhi nahi hai, toh ignore karo
        if not (is_private or is_tagged or is_reply_to_me):
            return

        chat_id = event.chat_id
        user_text = event.raw_text
        
        # Remove the tag from the text
        if is_tagged and me.username:
            user_text = user_text.replace(f"@{me.username}", "").replace(f"@{me.username.lower()}", "").strip()

        # Initialize history for this chat
        if chat_id not in client.ai_history:
            client.ai_history[chat_id] = []

        # Append user message to history
        client.ai_history[chat_id].append({"role": "user", "content": user_text})
        
        # Keep history to last 10 messages for memory
        if len(client.ai_history[chat_id]) > 10:
            client.ai_history[chat_id] = client.ai_history[chat_id][-10:]

        # Prepare payload
        messages = [{"role": "system", "content": client.ai_prompt}] + client.ai_history[chat_id]
        
        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 250
        }
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        async with client.action(chat_id, 'typing'):
            try:
                # Timeout add kiya taaki bot hang na ho
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(API_URL, json=payload, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            ai_reply = data['choices'][0]['message']['content'].strip()
                            
                            # Send the natural AI reply
                            await event.reply(ai_reply)
                            
                            # Save AI reply to memory
                            client.ai_history[chat_id].append({"role": "assistant", "content": ai_reply})
                            
                        else:
                            err = await resp.text()
                            print(f"[AI CHAT ERROR] Status {resp.status}: {err}")
                            
                            # Agar API fail ho jaye, toh us user ke message ko history se hata do
                            client.ai_history[chat_id].pop()
                            
                            # DM mein error mat bhejo, sirf GC mein bhejo
                            if not is_private:
                                await event.reply(f"⚠️ **AI Error:** `{resp.status}` (Check logs)")
                            
            except Exception as e:
                print(f"[AI CHAT EXCEPTION] {e}")
                if chat_id in client.ai_history and client.ai_history[chat_id]:
                     client.ai_history[chat_id].pop()
