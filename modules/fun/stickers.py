import asyncio
import os
import io
import logging
import subprocess
import shutil
from PIL import Image, ImageDraw, ImageFont
from telethon import events, functions, types, errors
from database import save_user_pack, get_pack_short_name

log = logging.getLogger(__name__)

# --- 🛠️ GLOBAL TRACKER (To prevent duplicates) ---
PROCESSED_EVENTS = set()

# --- 🛠️ HELPERS ---

async def safe_edit(event, text, **kwargs):
    try:
        return await event.edit(text, **kwargs)
    except Exception:
        return event

def prepare_static_sticker(image_bytes):
    try:
        if not image_bytes: return None
        img = Image.open(io.BytesIO(image_bytes))
        if getattr(img, "is_animated", False):
            img.seek(0)
            img = img.convert("RGBA")
        if img.mode != 'RGBA': img = img.convert('RGBA')
        
        width, height = img.size
        if width > height:
            new_width, new_height = 512, int(512 * (height / width))
        else:
            new_height, new_width = 512, int(512 * (width / height))
            
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="PNG")
        out.seek(0)
        return out
    except Exception as e:
        log.error(f"Image Prep Error: {e}")
        return None

async def process_video_to_sticker(client, reply, event_id):
    """Downloads any video/gif, crops to 3s, removes audio, scales to 512x512 for Telegram Sticker compatibility"""
    if not is_ffmpeg():
        return None, "FFMPEG not installed on server."
        
    in_f = await client.download_media(reply, f"vid_in_{event_id}")
    out_f = f"vid_out_{event_id}.webm"
    
    try:
        cmd = [
            "ffmpeg", "-i", in_f,
            "-t", "3",
            "-vf", "scale=512:512:force_original_aspect_ratio=decrease,format=rgba,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=#00000000",
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            "-an", "-r", "30", "-y", out_f
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        
        if os.path.exists(out_f) and os.path.getsize(out_f) > 0:
            with open(out_f, "rb") as f:
                res_bytes = f.read()
            return res_bytes, None
        return None, "FFMPEG processing failed."
    except Exception as e:
        return None, str(e)
    finally:
        for f in [in_f, out_f]:
            if os.path.exists(f): os.remove(f)

async def refresh_pack(client, short_name):
    """Force Telegram to refresh the sticker set cache instantly"""
    try:
        await client(functions.messages.GetStickerSetRequest(
            stickerset=types.InputStickerSetShortName(short_name=short_name),
            hash=0
        ))
    except: pass

def is_ffmpeg():
    return shutil.which("ffmpeg") is not None or os.path.exists("/usr/bin/ffmpeg")

def draw_text(image, top, bottom):
    draw = ImageDraw.Draw(image)
    w, h = image.size
    
    # Base configuration for dynamic text scaling
    base_fs = int(h / 8) if h > 0 else 40
    min_fs = 18  # Isse chota nahi hoga font taaki readability bani rahe
    
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]
    font_path = None
    for path in font_paths:
        if os.path.exists(path):
            font_path = path
            break

    def get_auto_font(txt):
        if not font_path:
            return ImageFont.load_default(), base_fs
            
        current_fs = base_fs
        font = ImageFont.truetype(font_path, current_fs)
        
        # Loop jab tak text ki width image boundary ke andar fit na aa jaye
        while current_fs > min_fs:
            tw = draw.textlength(txt, font=font) if hasattr(draw, 'textlength') else len(txt) * (current_fs * 0.6)
            if tw < (w - 30):  # 30px padding side boundaries ke liye
                break
            current_fs -= 2
            font = ImageFont.truetype(font_path, current_fs)
            
        return font, current_fs

    def draw_t(txt, y, position_top=True):
        if not txt: return
        font, final_fs = get_auto_font(txt)
        tw = draw.textlength(txt, font=font) if hasattr(draw, 'textlength') else len(txt) * (final_fs * 0.6)
        x = (w - tw) / 2
        
        # Adjust vertical position for bottom text if font gets downscaled
        final_y = y if position_top else (h - final_fs - 25)
        
        # Stroke outline representation
        for o in range(-2, 3):
            for oy in range(-2, 3): 
                draw.text((x+o, final_y+oy), txt, font=font, fill="black")
        draw.text((x, final_y), txt, font=font, fill="white")
        
    if top:
        draw_t(top, 15, position_top=True)
    if bottom:
        draw_t(bottom, h - base_fs - 25, position_top=False)
    return image

def register(client):

    # --- 1. KANG COMMAND (.kang [name]) - CREATE ONLY ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.kang(?:\s+([\w\s]+))?(?:\s+(.+))?'))
    async def kang_handler(event):
        if event.id in PROCESSED_EVENTS: return
        PROCESSED_EVENTS.add(event.id)

        if not event.is_reply:
            return await safe_edit(event, "❌ **Error:** Reply to media to create a pack.")
        
        reply = await event.get_reply_message()
        pack_arg = event.pattern_match.group(1)
        emoji = event.pattern_match.group(2) or "⚡"
        pack_name = pack_arg.strip() if pack_arg else "EmpirePack"
        
        status = await safe_edit(event, f"✨ **Creating Pack `{pack_name}`...**")
        
        try:
            is_anim = reply.file.ext == '.tgs'
            is_video_raw = reply.file.mime_type == 'video/webm' or (reply.media and hasattr(reply.media, 'document') and reply.media.document.mime_type == 'video/webm')
            is_other_video = reply.file.mime_type in ['video/mp4', 'image/gif'] or reply.file.ext in ['.mp4', '.gif']

            if is_other_video:
                await safe_edit(status, "🎬 **Processing video/gif into Sticker format (Max 3s, No Audio)...**")
                v_bytes, err = await process_video_to_sticker(client, reply, event.id)
                if err: return await safe_edit(status, f"❌ FFMPEG Error: {err}")
                sticker_io = io.BytesIO(v_bytes)
                sticker_io.name = "sticker.webm"
                is_video = True
            else:
                media_bytes = await client.download_media(reply, bytes)
                is_video = is_video_raw
                if not is_anim and not is_video:
                    sticker_io = prepare_static_sticker(media_bytes)
                    sticker_io.name = "sticker.png"
                else:
                    sticker_io = io.BytesIO(media_bytes)
                    sticker_io.name = "sticker.tgs" if is_anim else "sticker.webm"

            sent_msg = await client.send_file('me', sticker_io, force_document=True)
            doc = sent_msg.media.document
            sticker_item = types.InputStickerSetItem(
                document=types.InputDocument(id=doc.id, access_hash=doc.access_hash, file_reference=doc.file_reference),
                emoji=emoji
            )

            me = await client.get_me()
            short_name = f"{pack_name.replace(' ', '_')}_{me.id}_by_{me.username or me.id}"
            
            await client(functions.stickers.CreateStickerSetRequest(
                user_id=me.id, title=pack_name, short_name=short_name, stickers=[sticker_item]
            ))
            
            await save_user_pack(me.id, pack_name, short_name)
            await safe_edit(status, f"✅ **Pack Created!**\n🔗 https://t.me/addstickers/{short_name}")
            
            await sent_msg.delete()
            await refresh_pack(client, short_name)

        except Exception as e:
            if "SHORTNAME_OCCUPIED" in str(e):
                await safe_edit(status, f"❌ **Error:** Pack `{pack_name}` already exists.\n👉 Use `.add {pack_name}`.")
            else:
                await safe_edit(status, f"❌ **Error:** {str(e)}")

    # --- 2. ADD COMMAND (.add [name]) - ADD TO EXISTING ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.add(?:\s+([\w\s]+))?(?:\s+(.+))?'))
    async def add_handler(event):
        if event.id in PROCESSED_EVENTS: return
        PROCESSED_EVENTS.add(event.id)

        if not event.is_reply:
            return await safe_edit(event, "❌ Reply to media + specify pack name.")
        
        pack_arg = event.pattern_match.group(1)
        if not pack_arg:
            return await safe_edit(event, "❌ **Usage:** `.add PackName` ")

        pack_name = pack_arg.strip()
        emoji = event.pattern_match.group(2) or "⚡"
        reply = await event.get_reply_message()
        status = await safe_edit(event, f"🚀 **Adding to `{pack_name}`...**")
        
        try:
            me = await client.get_me()
            short_name = await get_pack_short_name(me.id, pack_name)
            if not short_name:
                short_name = f"{pack_name.replace(' ', '_')}_{me.id}_by_{me.username or me.id}"

            is_anim = reply.file.ext == '.tgs'
            is_video_raw = reply.file.mime_type == 'video/webm' or (reply.media and hasattr(reply.media, 'document') and reply.media.document.mime_type == 'video/webm')
            is_other_video = reply.file.mime_type in ['video/mp4', 'image/gif'] or reply.file.ext in ['.mp4', '.gif']

            if is_other_video:
                await safe_edit(status, "🎬 **Processing video/gif into Sticker format...**")
                v_bytes, err = await process_video_to_sticker(client, reply, event.id)
                if err: return await safe_edit(status, f"❌ FFMPEG Error: {err}")
                sticker_io = io.BytesIO(v_bytes)
                sticker_io.name = "sticker.webm"
            else:
                media_bytes = await client.download_media(reply, bytes)
                if not is_anim and not is_video_raw:
                    sticker_io = prepare_static_sticker(media_bytes)
                    sticker_io.name = "sticker.png"
                else:
                    sticker_io = io.BytesIO(media_bytes)
                    sticker_io.name = "sticker.tgs" if is_anim else "sticker.webm"

            sent_msg = await client.send_file('me', sticker_io, force_document=True)
            doc = sent_msg.media.document
            sticker_item = types.InputStickerSetItem(
                document=types.InputDocument(id=doc.id, access_hash=doc.access_hash, file_reference=doc.file_reference),
                emoji=emoji
            )

            await client(functions.stickers.AddStickerToSetRequest(
                stickerset=types.InputStickerSetShortName(short_name=short_name),
                sticker=sticker_item
            ))
            
            await safe_edit(status, f"✅ **Added to `{pack_name}`!**\n🔗 https://t.me/addstickers/{short_name}")
            
            await sent_msg.delete()
            await refresh_pack(client, short_name)

        except Exception as e:
            await safe_edit(status, f"❌ **Failed:** {str(e)}")

    # --- 3. DELETE STICKER (.delsticker [name]) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.delsticker(?:\s+(.*))?'))
    async def remove_sticker_handler(event):
        if event.id in PROCESSED_EVENTS: return
        PROCESSED_EVENTS.add(event.id)

        if not event.is_reply: return await safe_edit(event, "❌ Reply to sticker.")
        pack_name = event.pattern_match.group(1) or "Pack"
        
        status = await safe_edit(event, f"🗑️ **Removing from `{pack_name}`...**")
        try:
            reply = await event.get_reply_message()
            if not reply.media or not hasattr(reply.media, 'document'):
                return await safe_edit(status, "❌ Reply to an actual sticker.")
                
            short_name = await get_pack_short_name((await client.get_me()).id, pack_name)

            await client(functions.stickers.RemoveStickerFromSetRequest(
                sticker=types.InputDocument(
                    id=reply.media.document.id, 
                    access_hash=reply.media.document.access_hash, 
                    file_reference=reply.media.document.file_reference
                )
            ))
            await safe_edit(status, f"✅ **Sticker removed from `{pack_name}`!**")
            if short_name: await refresh_pack(client, short_name)

        except Exception as e:
            err_str = str(e)
            if any(x in err_str for x in ["STICKERSET_NOT_MODIFIED", "STICKERSET_INVALID", "STICKER_INVALID"]):
                await safe_edit(status, f"✅ **Sticker removed from `{pack_name}`!**")
                if 'short_name' in locals() and short_name: 
                    await refresh_pack(client, short_name)
            else:
                await safe_edit(status, f"❌ **Failed:** {err_str}")

    # --- 4. DELETE PACK (.delpack [name]) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.delpack(?:\s+(.*))?'))
    async def delete_pack_handler(event):
        if event.id in PROCESSED_EVENTS: return
        PROCESSED_EVENTS.add(event.id)

        pack_arg = event.pattern_match.group(1)
        if not pack_arg: return await safe_edit(event, "❌ Specify Pack Name.")
        
        pack_name = pack_arg.strip()
        status = await safe_edit(event, f"⚠️ **Deleting Pack `{pack_name}`...**")
        try:
            me = await client.get_me()
            short_name = await get_pack_short_name(me.id, pack_name)
            if not short_name:
                short_name = f"{pack_name.replace(' ', '_').strip()}_{me.id}_by_{me.username or me.id}"

            try:
                await client(functions.stickers.DeleteStickerSetRequest(stickerset=types.InputStickerSetShortName(short_name=short_name)))
            except: pass

            from database import db
            if db is not None:
                await db["sticker_packs"].delete_one({"user_id": me.id, "pack_name": pack_name.lower()})
            
            await safe_edit(status, f"🗑️ **Pack `{pack_name}` deleted.**")
        except Exception as e:
            await safe_edit(status, f"❌ **Failed:** {str(e)}")

    # --- 5. PACK LINK (.pack [name]) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.pack(?:\s+(.*))?'))
    async def pack_handler(event):
        pack_name = event.pattern_match.group(1).strip() if event.pattern_match.group(1) else "EmpirePack"
        me = await client.get_me()
        sn = await get_pack_short_name(me.id, pack_name)
        if not sn: sn = f"{pack_name.replace(' ', '_')}_{me.id}_by_{me.username or me.id}"
        await safe_edit(event, f"📦 **Pack:** `{pack_name}`\n🔗 https://t.me/addstickers/{sn}")

    # --- 6. ADVANCED MEMIFY COMMAND (.mm TOP ; BOTTOM) ---
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\.mm(?:\s+(.*))?'))
    async def memify_handler(event):
        if event.id in PROCESSED_EVENTS: return
        PROCESSED_EVENTS.add(event.id)
        
        if not event.is_reply: return await safe_edit(event, "❌ Reply to a photo or sticker.")
        
        text = event.pattern_match.group(1)
        if not text: return await safe_edit(event, "❌ Usage: `.mm Top ; Bottom` ya `.mm Top` ")
        
        if ";" in text:
            parts = text.split(";", 1)
            top = parts[0].strip().upper()
            bottom = parts[1].strip().upper()
        else:
            top = text.strip().upper()
            bottom = ""
            
        reply = await event.get_reply_message()
        status = await safe_edit(event, "🎨 **Creating Meme...**")
        
        try:
            is_video_sticker = reply.file.mime_type == 'video/webm' or (reply.file.ext == '.webm') or (reply.file.mime_type in ['video/mp4', 'image/gif']) or (reply.media and hasattr(reply.media, 'document') and reply.media.document.mime_type == 'video/webm')
            is_anim_tgs = reply.file.ext == '.tgs'
            
            if is_video_sticker and is_ffmpeg():
                fpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if not os.path.exists(fpath):
                    fpath = "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
                
                in_f = await client.download_media(reply, f"mm_in_{event.id}.webm")
                out_f = f"mm_out_{event.id}.webm"
                
                filters = ["scale=512:512:force_original_aspect_ratio=decrease,format=rgba,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=#00000000"]
                
                # FFMPEG Dynamic Font Scale Logic: Text length ke hisab se scaling evaluate karega (min size limit: 18)
                if top:
                    filters.append(f"drawtext=fontfile='{fpath}':text='{top}':fontcolor=white:fontsize='if(lt(tw,w-40),40,max(18,40*(w-40)/tw))':borderw=4:bordercolor=black:x=(w-text_w)/2:y=25")
                if bottom:
                    filters.append(f"drawtext=fontfile='{fpath}':text='{bottom}':fontcolor=white:fontsize='if(lt(tw,w-40),40,max(18,40*(w-40)/tw))':borderw=4:bordercolor=black:x=(w-text_w)/2:y=h-40-35")
                
                filt = ",".join(filters)
                cmd = ["ffmpeg", "-i", in_f, "-t", "3", "-vf", filt, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-an", "-y", out_f]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                await client.send_file(
                    event.chat_id, out_f, reply_to=reply.id, mime_type="video/webm",
                    attributes=[types.DocumentAttributeSticker(alt="⚡", stickerset=types.InputStickerSetEmpty())]
                )
                for f in [in_f, out_f]: 
                    if os.path.exists(f): os.remove(f)
            else:
                img_data = await client.download_media(reply, bytes, thumb=-1 if is_anim_tgs else None)
                if not img_data:
                    return await safe_edit(status, "❌ Media read failed.")
                    
                image = Image.open(io.BytesIO(img_data)).convert("RGBA")
                processed_image = prepare_static_sticker(img_data)
                if processed_image:
                    image = Image.open(processed_image).convert("RGBA")
                
                meme_img = draw_text(image, top, bottom)
                output = io.BytesIO()
                meme_img.save(output, format="WEBP", method=6)
                output.name = "sticker.webp"
                output.seek(0)
                
                await client.send_file(
                    event.chat_id, 
                    output, 
                    reply_to=reply.id, 
                    as_sticker=True,
                    attributes=[types.DocumentAttributeSticker(alt="⚡", stickerset=types.InputStickerSetEmpty())]
                )
                
            await status.delete()
        except Exception as e: 
            await safe_edit(status, f"❌ Failed: {str(e)}")
