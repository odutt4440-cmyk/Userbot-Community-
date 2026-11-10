import asyncio
import os
from telethon import events
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest

# --- MODULE REGISTER ---
def register(client):
    # Har user ka apna data alag rahega (SaaS Safe)
    client.cl_original = {
        'first_name': None,
        'last_name': None,
        'about': None,
        'photo_path': None, # Original photo store karne ke liye
        'has_backup': False
    }

    # Helper function to delete messages automatically
    async def ephemeral_msg(message, seconds=5):
        await asyncio.sleep(seconds)
        try:
            await message.delete()
        except:
            pass

    # --- 1. CLONE COMMAND (.clone) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.clone$'))
    async def clone_handler(event):
        if not event.is_reply:
            msg = await event.edit("❌ **Error:** Please reply to a user to clone their identity.")
            asyncio.create_task(ephemeral_msg(msg))
            return

        status = await event.edit("🧬 **Processing:** Cloning user identity...")
        reply_msg = await event.get_reply_message()
        
        try:
            target_user = await client.get_entity(reply_msg.sender_id)
            target_full = await client(GetFullUserRequest(target_user))
            
            # --- BACKUP ORIGINAL IDENTITY (ONLY ONCE) ---
            if not client.cl_original['has_backup']:
                me = await client.get_me()
                me_full = await client(GetFullUserRequest(me))
                client.cl_original['first_name'] = me.first_name
                client.cl_original['last_name'] = me.last_name
                client.cl_original['about'] = me_full.full_user.about
                
                # Backup Original Photo
                photo_backup = f"original_{event.sender_id}.jpg"
                my_photos = await client.get_profile_photos('me', limit=1)
                if my_photos:
                    await client.download_media(my_photos[0], file=photo_backup)
                    client.cl_original['photo_path'] = photo_backup
                
                client.cl_original['has_backup'] = True

            # --- CLONE TARGET'S PHOTO ---
            target_photos = await client.get_profile_photos(target_user, limit=1)
            if target_photos:
                photo_path = f"clone_{event.sender_id}.jpg"
                await client.download_media(target_photos[0], file=photo_path)
                uploaded_photo = await client.upload_file(photo_path)
                await client(UploadProfilePhotoRequest(file=uploaded_photo))
                if os.path.exists(photo_path):
                    os.remove(photo_path)

            # --- CLONE NAME & BIO ---
            await client(UpdateProfileRequest(
                first_name=target_user.first_name or '',
                last_name=target_user.last_name or '',
                about=target_full.full_user.about or ''
            ))

            await status.edit(f"✅ **Success:** Identity stolen from **{target_user.first_name}**.")
            asyncio.create_task(ephemeral_msg(status))

        except Exception as e:
            await status.edit(f"❌ **Failed:** `{str(e)}` ")
            asyncio.create_task(ephemeral_msg(status))

    # --- 2. REVERT COMMAND (.revert) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.revert$'))
    async def revert_handler(event):
        if not client.cl_original['has_backup']:
            msg = await event.edit("❌ **Error:** No backup found. You must clone someone first.")
            asyncio.create_task(ephemeral_msg(msg))
            return

        status = await event.edit("🔄 **Restoring:** Returning to original identity...")

        try:
            # Restore Photo if it was backed up
            if client.cl_original['photo_path'] and os.path.exists(client.cl_original['photo_path']):
                uploaded_photo = await client.upload_file(client.cl_original['photo_path'])
                await client(UploadProfilePhotoRequest(file=uploaded_photo))
                # Photo wapas lag gayi, ab backup file delete kar sakte hain
                os.remove(client.cl_original['photo_path'])
                client.cl_original['photo_path'] = None

            # Restore Name and Bio
            await client(UpdateProfileRequest(
                first_name=client.cl_original['first_name'] or '',
                last_name=client.cl_original['last_name'] or '',
                about=client.cl_original['about'] or ''
            ))

            # Reset state for next time
            client.cl_original['has_backup'] = False

            await status.edit("✅ **Identity Restored:** You are back to normal with your original PFP.")
            asyncio.create_task(ephemeral_msg(status))
        except Exception as e:
            await status.edit(f"❌ **Failed:** `{str(e)}` ")
            asyncio.create_task(ephemeral_msg(status))
