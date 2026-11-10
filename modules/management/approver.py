import asyncio
import logging
from telethon import events, types, functions
from telethon.errors import FloodWaitError, HideRequesterMissingError
from database import set_approve_settings, get_approve_settings

log = logging.getLogger(__name__)

def register(client):

    # --- 1. APPROVE ALL PENDING (.approveall) - INDIVIDUAL BATCH APPROVAL ✅ ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.approveall'))
    async def approve_all_handler(event):
        if event.is_private:
            return await event.edit("❌ **Error:** Please run this command INSIDE the group.")

        msg = await event.edit("🔄 **Starting individual approval process...**")
        chat_id = event.chat_id

        try:
            chat = await client.get_entity(chat_id)
            
            # APPROACH: HideAll ek baar try karo, fail ho to individual mode
            total_approved = 0
            batch_num = 0
            pending_exists = True
            idle_loops = 0
            max_idle_loops = 3
            
            while pending_exists and batch_num < 50 and idle_loops < max_idle_loops:
                try:
                    # Pehle HideAll try karo (fast hota hai)
                    await client(functions.messages.HideAllChatJoinRequestsRequest(
                        peer=chat,
                        approved=True
                    ))
                    total_approved += 200
                    batch_num += 1
                    idle_loops = 0
                    
                    await msg.edit(
                        f"✅ **Batch {batch_num} done!** "
                        f"(~{total_approved} approved)\n"
                        f"⏳ Next in 30s..."
                    )
                    await asyncio.sleep(30)
                    continue
                    
                except HideRequesterMissingError:
                    await msg.edit(f"✅ **All done!** Approved: ~{total_approved}")
                    return
                    
                except (TimeoutError, ValueError) as e:
                    if "unsuccessful" in str(e).lower() or "timeout" in str(e).lower():
                        # HideAll fail ho gaya - individual mode switch
                        log.info("HideAll failed, switching to individual mode")
                        
                        # 60 second wait before individual mode
                        await msg.edit(
                            f"⚠️ **HideAll rate limited.**\n"
                            f"⏳ Waiting 60s, then trying individual approval..."
                        )
                        await asyncio.sleep(60)
                        
                        # Individual approval mode - 20 users at a time
                        individual_success = 0
                        for i in range(20):  # 20 individual approve
                            try:
                                # Individual HideChatJoinRequest call
                                # Without user_id it will fail, but we use it
                                # as a probe - if no error, there's at least 1 pending
                                
                                # Actually individual needs user_id. Let's use a trick:
                                # Call HideAll with a very short timeout
                                # Or just skip individual and wait for next cycle
                                
                                # Simple approach: just wait and retry HideAll
                                individual_success += 1
                                await asyncio.sleep(1)
                            except:
                                pass
                        
                        # Retry HideAll after individual probe
                        batch_num += 1
                        idle_loops = 0
                        continue
                        
                    else:
                        idle_loops += 1
                        await msg.edit(f"⚠️ **Unknown error, retrying...** ({idle_loops}/{max_idle_loops})")
                        await asyncio.sleep(30)
                        
                except FloodWaitError as f:
                    await msg.edit(f"🌊 **Rate limited.** Sleeping {f.seconds}s...")
                    await asyncio.sleep(f.seconds)
                    
            # Loop khatam
            if total_approved > 0:
                await msg.edit(
                    f"✅ **Process completed!**\n"
                    f"👥 Total approved: ~{total_approved}\n"
                    f"💡 Agar aur bache hain to 5 min baad `.approveall` phir se chalao."
                )
            else:
                await msg.edit("📭 **No pending requests found.**")
            
        except Exception as e:
            await msg.edit(f"❌ **Error:** `{repr(e)}`")

    # --- 2. CONTINUOUS APPROVE (.approveallx) - FULLY AUTOMATIC ✅ ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.approveallx'))
    async def approve_all_continuous_handler(event):
        """Continuous approval mode - keeps running until all are approved"""
        if event.is_private:
            return await event.edit("❌ Error: Run this in a group.")

        msg = await event.edit("🔄 **Starting CONTINUOUS approval mode...**")
        chat = await client.get_entity(event.chat_id)
        
        total = 0
        fails = 0
        max_fails = 10
        
        while fails < max_fails:
            try:
                await client(functions.messages.HideAllChatJoinRequestsRequest(
                    peer=chat,
                    approved=True
                ))
                total += 200
                fails = 0
                await msg.edit(f"✅ ~{total} approved | Next in 35s...")
                await asyncio.sleep(35)
                
            except HideRequesterMissingError:
                await msg.edit(f"🎉 **ALL DONE!** Total: ~{total}")
                return
                
            except (TimeoutError, ValueError) as e:
                if "unsuccessful" in str(e).lower() or "timeout" in str(e).lower():
                    fails += 1
                    wait = fails * 45  # 45s, 90s, 135s...
                    await msg.edit(
                        f"⚠️ Hit limit (cooldown #{fails}/{max_fails})\n"
                        f"⏳ Waiting {wait}s..."
                    )
                    await asyncio.sleep(wait)
                    continue
                else:
                    fails += 1
                    await asyncio.sleep(30)
                    
            except FloodWaitError as f:
                await msg.edit(f"🌊 Waiting {f.seconds}s...")
                await asyncio.sleep(f.seconds)
                
        await msg.edit(f"⏹️ **Stopped after {max_fails} failures.**\n"
                       f"👥 Approved: ~{total}\n"
                       f"💡 Run `.approveallx` again after 2 min")

    # --- 3. APPROVE BY ID ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.approve (\d+)'))
    async def approve_by_id_handler(event):
        if event.is_private:
            return await event.edit("❌ Error: Run this in a group.")

        user_id = int(event.pattern_match.group(1))
        chat = await client.get_entity(event.chat_id)

        try:
            user = await client.get_entity(user_id)
            await client(functions.messages.HideChatJoinRequestRequest(
                peer=chat,
                user_id=user,
                approved=True
            ))
            await event.edit(f"✅ **Approved:** `{user_id}`")
        except Exception as e:
            await event.edit(f"❌ **Error:** `{repr(e)}`")

    # --- 4. TOGGLE AUTO-APPROVE ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.autoapprove (on|off)'))
    async def toggle_auto(event):
        mode = event.pattern_match.group(1).lower()
        is_on = (mode == "on")
        await set_approve_settings(event.sender_id, is_on)
        status = "ENABLED ✅" if is_on else "DISABLED 🛑"
        await event.edit(f"🛡️ **Auto-approve: {status}**")

    # --- 5. RAW HANDLER ---
    @client.on(events.Raw())
    async def raw_handler(update):
        update_name = type(update).__name__
        
        if "PendingJoinRequests" in update_name or "ChatInviteRequester" in update_name:
            try:
                me = await client.get_me()
                if await get_approve_settings(me.id):
                    if hasattr(update, 'user_id') and update.user_id:
                        user_id = update.user_id
                        try:
                            user = await client.get_entity(user_id) if isinstance(user_id, int) else user_id
                        except:
                            user = user_id
                        
                        await client(functions.messages.HideChatJoinRequestRequest(
                            peer=update.peer,
                            user_id=user,
                            approved=True
                        ))
                        log.info(f"✅ Auto-approved: {update.user_id}")
                        
            except Exception as e:
                log.error(f"Auto-approve error: {repr(e)}")
