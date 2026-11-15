import asyncio
from telethon import events
from telethon.errors import FloodWaitError, ChatAdminRequiredError, UserAdminInvalidError
from database import handle_warn

def register(client):
    async def ephemeral(msg, sec=5):
        await asyncio.sleep(sec)
        try: await msg.delete()
        except: pass

    # --- 1. BAN (.ban) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.ban$'))
    async def ban_user(event):
        if not event.is_reply: 
            return await event.edit("❌ **Error:** Reply to the user you want to ban.")
        
        reply = await event.get_reply_message()
        try:
            await client.edit_permissions(event.chat_id, reply.sender_id, view_messages=False)
            msg = await event.edit("🚫 **User Banned successfully.**")
            asyncio.create_task(ephemeral(msg))
        except ChatAdminRequiredError:
            await event.edit("❌ **Error:** I need Admin rights with 'Ban Users' permission.")
        except UserAdminInvalidError:
            await event.edit("❌ **Error:** I can't ban a Group Admin.")
        except Exception as e:
            await event.edit(f"❌ **Error:** {str(e)}")

    # --- 2. MUTE (.mute) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.mute$'))
    async def mute_user(event):
        if not event.is_reply: 
            return await event.edit("❌ **Error:** Reply to the user you want to mute.")
        
        reply = await event.get_reply_message()
        try:
            await client.edit_permissions(event.chat_id, reply.sender_id, send_messages=False)
            msg = await event.edit("🔇 **User Muted successfully.**")
            asyncio.create_task(ephemeral(msg))
        except ChatAdminRequiredError:
            await event.edit("❌ **Error:** I need Admin rights with 'Restrict Members' permission.")
        except UserAdminInvalidError:
            await event.edit("❌ **Error:** I can't mute a Group Admin.")
        except Exception as e:
            await event.edit(f"❌ **Error:** {str(e)}")

    # --- 3. WARN (.warn) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.warn$'))
    async def warn_user(event):
        if not event.is_reply: 
            return await event.edit("❌ **Error:** Reply to the user you want to warn.")
        
        reply = await event.get_reply_message()
        count = await handle_warn(reply.sender_id, event.chat_id)
        
        warn_msg = f"⚠️ **Warning [{count}/3]**\nUser has been warned. 3 warnings result in a ban."
        
        if count >= 3:
            try:
                await client.edit_permissions(event.chat_id, reply.sender_id, view_messages=False)
                warn_msg = "🚫 **User Banned:** 3 warnings reached."
            except Exception:
                warn_msg = f"⚠️ **Warning [{count}/3]**\n(User has 3 warns, but couldn't be banned. Might be an admin.)"
        
        await event.edit(warn_msg)

    # --- 4. BANALL (.banall) - Fixed & Robust ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.banall$'))
    async def ban_all(event):
        if event.is_private:
            return await event.edit("❌ **Error:** Use this in a Group.")
        
        status = await event.edit("☣️ **Initiating Global Cleanup...**")
        count = 0
        failed = 0
        
        try:
            async for user in client.iter_participants(event.chat_id):
                # Sirf khud ko aur bots ko skip karo
                if user.bot or user.is_self:
                    continue
                
                try:
                    # Admin ho ya na ho, ban karne ki koshish karo
                    await client.edit_permissions(event.chat_id, user.id, view_messages=False)
                    count += 1
                    
                    # Har 10 ban ke baad chota gap + status update
                    if count % 10 == 0:
                        await status.edit(f"☣️ **Cleanup in progress:** `{count}` banned...")
                        await asyncio.sleep(1.5)
                        
                except FloodWaitError as e:
                    # Agar Telegram limit laga de toh ruk jao
                    await status.edit(f"⏳ **Flood limit reached.** Waiting for {e.seconds} seconds...")
                    await asyncio.sleep(e.seconds)
                    
                except Exception:
                    # Agar user admin hai ya protected hai toh fail count badhao
                    failed += 1
                    continue
            
            await status.edit(
                f"✅ **Cleanup Complete!**\n"
                f"🚫 **Banned:** `{count}`\n"
                f"⚠️ **Failed (Admins/Protected):** `{failed}`"
            )
        except Exception as e:
            await status.edit(f"❌ **Fatal Error:** `{str(e)}` ")
        
        asyncio.create_task(ephemeral(status, 10))
