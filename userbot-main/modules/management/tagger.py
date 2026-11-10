import asyncio
from telethon import events

# --- MODULE REGISTER ---
def register(client):
    # State per user to control the tagging process
    client.tag_running = False
    client.tag_delay = 3 # Safe default delay (3 seconds)

    # Helper function to delete status messages automatically
    async def ephemeral_msg(message, seconds=5):
        await asyncio.sleep(seconds)
        try:
            await message.delete()
        except:
            pass

    # --- 1. TAG ALL COMMAND (.tagall) ---
    # Usage: .tagall <message> (Tags everyone in batches of 5)
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.tagall(?:\s+(.*))?'))
    async def tag_all_handler(event):
        if client.tag_running:
            msg = await event.edit("⚠️ **Already Running:** A tag process is active. Use `.stopall` first.")
            return asyncio.create_task(ephemeral_msg(msg))

        # Message to show with the tags
        custom_msg = event.pattern_match.group(1) or "Hey everyone, check this out!"
        
        await event.delete() # Command delete kar do taaki chat gandi na lage
        client.tag_running = True
        
        mentions = []
        count = 0
        
        try:
            # Fetching participants from the group
            async for user in client.iter_participants(event.chat_id):
                if not client.tag_running:
                    break
                
                if user.bot or user.deleted:
                    continue
                
                # Hidden tag format (markdown)
                mentions.append(f"[{user.first_name}](tg://user?id={user.id})")
                
                # Batch of 5 people per message (Telegram Flood Protection)
                if len(mentions) == 5:
                    tag_text = f"📢 {custom_msg}\n\n" + " ".join(mentions)
                    await client.send_message(event.chat_id, tag_text)
                    mentions = []
                    count += 5
                    await asyncio.sleep(client.tag_delay) # Wait to avoid ban

            # Send any remaining users
            if mentions and client.tag_running:
                tag_text = f"📢 {custom_msg}\n\n" + " ".join(mentions)
                await client.send_message(event.chat_id, tag_text)
                count += len(mentions)

            final_msg = await client.send_message(event.chat_id, f"✅ **Tagging Complete:** {count} members mentioned.")
            asyncio.create_task(ephemeral_msg(final_msg))

        except Exception as e:
            await client.send_message("me", f"❌ **TagAll Error:** `{str(e)}`")
        
        client.tag_running = False

    # --- 2. STOP TAGGING (.stopall) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.stopall$'))
    async def stop_tag_handler(event):
        if not client.tag_running:
            msg = await event.edit("❌ **Error:** No tagging process is active.")
            return asyncio.create_task(ephemeral_msg(msg))
        
        client.tag_running = False
        msg = await event.edit("🛑 **Terminated:** Tagging process stopped by user.")
        asyncio.create_task(ephemeral_msg(msg))

    # --- 3. SET DELAY (.tagdelay) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.tagdelay (\d+)$'))
    async def set_tag_delay(event):
        delay = int(event.pattern_match.group(1))
        if delay < 1:
            return await event.edit("❌ **Error:** Minimum delay is 1 second.")
        
        client.tag_delay = delay
        msg = await event.edit(f"⚡ **Speed Updated:** Tag delay set to `{delay}` seconds.")
        asyncio.create_task(ephemeral_msg(msg))
