import asyncio
from telethon import events
from database import handle_warn

def register(client):
    async def ephemeral(msg, sec=5):
        await asyncio.sleep(sec)
        try: await msg.delete()
        except: pass

    # --- 1. BAN (.ban) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ban$'))
    async def ban_user(event):
        if not event.is_reply: return
        reply = await event.get_reply_message()
        try:
            await client.edit_permissions(event.chat_id, reply.sender_id, view_messages=False)
            msg = await event.edit("🚫 **User Banned successfully.**")
            asyncio.create_task(ephemeral(msg))
        except:
            await event.edit("❌ **Error:** Admin rights required.")

    # --- 2. MUTE (.mute) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.mute$'))
    async def mute_user(event):
        if not event.is_reply: return
        reply = await event.get_reply_message()
        try:
            await client.edit_permissions(event.chat_id, reply.sender_id, send_messages=False)
            msg = await event.edit("🔇 **User Muted successfully.**")
            asyncio.create_task(ephemeral(msg))
        except:
            await event.edit("❌ **Error:** Admin rights required.")

    # --- 3. WARN (.warn) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.warn$'))
    async def warn_user(event):
        if not event.is_reply: return
        reply = await event.get_reply_message()
        count = await handle_warn(reply.sender_id, event.chat_id)
        
        warn_msg = f"⚠️ **Warning [{count}/3]**\nUser has been warned. 3 warnings result in a ban."
        if count >= 3:
            try:
                await client.edit_permissions(event.chat_id, reply.sender_id, view_messages=False)
                warn_msg = "🚫 **User Banned:** 3 warnings reached."
            except: pass
        await event.edit(warn_msg)

    # --- 4. BANALL (.banall) - Optimized & Fixed ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.banall$'))
    async def ban_all(event):
        if event.is_private:
            return await event.edit("❌ **Error:** Use this in a Group.")
        
        status = await event.edit("☣️ **Initiating Global Cleanup...**")
        count = 0
        failed = 0
        
        try:
            # 1. Saare participants ki list uthao
            async for user in client.iter_participants(event.chat_id):
                # 2. Skip Admins, Bots aur Khud ko
                if user.admin_rights or user.bot or user.is_self:
                    continue
                
                try:
                    # 3. View Messages permission hata do (Ban)
                    await client.edit_permissions(event.chat_id, user.id, view_messages=False)
                    count += 1
                    
                    # 🔥 Har 5 ban ke baad chota gap taaki account safe rahe
                    if count % 10 == 0:
                        await status.edit(f"☣️ **Cleanup in progress:** `{count}` banned...")
                        await asyncio.sleep(1)
                except:
                    failed += 1
                    continue
            
            await status.edit(f"✅ **Cleanup Complete!**\n🚫 Banned: `{count}`\n⚠️ Failed: `{failed}` (Might be admins/protected)")
        except Exception as e:
            await status.edit(f"❌ **Fatal Error:** `{str(e)}` ")
        
        asyncio.create_task(ephemeral(status, 10))
