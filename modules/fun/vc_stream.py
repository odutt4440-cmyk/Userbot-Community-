import os
import glob
import asyncio
import logging
from telethon import events, utils
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, StreamEnded, GroupCallConfig
from database import set_vc_chat, get_vc_chat

log = logging.getLogger(__name__)

# state: {user_id: {"call": PyTgCalls, "chat": int, "queue": [(path, label)], "now": label|None}}
VC = {}


def marked_id(chat_id: int) -> int:
    """Positive channel/supergroup ID ko -100 marked form mein convert."""
    if chat_id > 0:
        return int(f"-100{chat_id}")
    return chat_id


def register(client):

    # ---------------- helpers ----------------
    def state(user_id):
        return VC.get(user_id)

    async def resolve_target(target: str):
        """Resolve link / @username / chat ID.
        Numeric IDs pehle session dialogs se resolve hote hain (access_hash cached),
        private GCs ke liye zaroori."""
        target = target.strip()

        if target.lstrip('-').isdigit():
            wanted = int(target)
            raw = int(str(wanted).replace('-100', '', 1)) if str(wanted).startswith('-100') else abs(wanted)
            async for dialog in client.iter_dialogs():
                if dialog.id == wanted or utils.get_peer_id(dialog.entity) == wanted:
                    return dialog.entity
                cid = getattr(dialog.entity, 'channel_id', None)
                if cid and (cid == raw or cid == abs(wanted)):
                    return dialog.entity
            return await client.get_entity(wanted)

        return await client.get_entity(target)

    async def get_call(user_id) -> PyTgCalls | None:
        """One PyTgCalls instance per user, reused forever."""
        if user_id in VC:
            return VC[user_id]["call"]
        try:
            call = PyTgCalls(client)
            await asyncio.wait_for(call.start(), timeout=30)   # 🔑 hang-proof init
        except asyncio.TimeoutError:
            log.error(f"VC init timed out for {user_id}")
            return None
        except Exception as e:
            log.error(f"VC init failed for {user_id}: {type(e).__name__}: {e}", exc_info=True)
            return None

        VC[user_id] = {"call": call, "chat": None, "queue": [], "now": None}

        @call.on_update()
        async def _on_stream_end(pytgcalls, update):
            if isinstance(update, StreamEnded) and update.stream_type == StreamEnded.Type.AUDIO:
                st = state(user_id)
                if st and st["queue"]:
                    await play_next(user_id)
                else:
                    if st:
                        st["now"] = None
                    log.info(f"Queue empty for {user_id}, stream ended naturally.")
        return call

    async def play_next(user_id):
        st = state(user_id)
        if not st or not st["queue"] or not st["chat"]:
            if st:
                st["now"] = None
            return
        path, label = st["queue"].pop(0)
        st["now"] = label
        try:
            await st["call"].play(
                st["chat"],
                MediaStream(path, video_flags=MediaStream.Flags.IGNORE),
            )
            log.info(f"Now streaming: {label}")
        except Exception as e:
            log.error(f"play_next failed for '{label}': {type(e).__name__}: {e}")
            if os.path.exists(path):
                os.remove(path)
            await play_next(user_id)  # skip broken file, try next

    def cleanup_files(user_id):
        for f in glob.glob(f"vc_{user_id}_*"):
            try:
                os.remove(f)
            except OSError:
                pass

    # ---------------- 1. .vctarget (link / username / chat id) ----------------
    @client.on(events.NewMessage(chats='me', pattern=r'^\.vctarget(?:\s+(.+))?$'))
    async def vc_target(event):
        target = event.pattern_match.group(1)
        if not target:
            return await event.edit(
                "❌ **Usage:** `.vctarget @username` / `https://t.me/...` / `-100xxxxxxxxxx`"
            )
        try:
            entity = await resolve_target(target)
            chat_id = utils.get_peer_id(entity)
            await set_vc_chat(event.sender_id, chat_id)
            st = state(event.sender_id)
            if st:
                st["chat"] = chat_id
            title = getattr(entity, "title", str(chat_id))
            await event.edit(
                f"🎯 **VC Target Locked:** `{title}` (`{chat_id}`)\n\n"
                "🎙️ Now reply `.vcstream` to any audio in Saved Messages.\n"
                "ℹ️ If the group has no active voice chat, one will be started automatically."
            )
        except Exception as e:
            await event.edit(
                f"❌ **Failed to resolve:** `{type(e).__name__}`\n\n"
                "💡 **Tip:** For private groups, make sure this account has joined the "
                "group at least once, then use its `-100...` chat ID."
            )

    # ---------------- 2. .vcstream ----------------
    @client.on(events.NewMessage(chats='me', pattern=r'^\.vcstream$'))
    async def vc_stream(event):
        reply = await event.get_reply_message()
        if not (reply and (reply.audio or reply.voice)):
            return await event.edit(
                "❌ Reply to an **audio or voice message** with `.vcstream`."
            )

        chat_id = await get_vc_chat(event.sender_id)
        if not chat_id:
            return await event.edit(
                "❌ No target set. Use `.vctarget @group` first."
            )
        chat_id = marked_id(chat_id)

        status = await event.edit("⬇️ **Downloading audio...**")

        # 🔑 SPEED FIX #1: PyTgCalls init ko download ke SAATH parallel start karo
        # (pehli baar VC init 10-20s leta hai — download ke wait ke baad nahi)
        call, temp = await asyncio.gather(
            get_call(event.sender_id),
            client.download_media(reply, f"vc_{event.sender_id}_{reply.id}.mp3"),
        )
        if not call:
            return await status.edit("❌ **VC engine failed to start.** Check logs.")

        st = state(event.sender_id)
        st["chat"] = chat_id

        label = reply.file.name or f"voice_{reply.id}"

        try:
            if not temp or not os.path.exists(temp):
                return await status.edit("❌ **Download failed.** Try again.")

            if st["now"] is None:
                st["now"] = label
                await status.edit("📡 **Joining voice chat...**")

                # 🔑 SPEED FIX #2: join/connect pe timeout — infinite hang nahi hoga
                try:
                    await asyncio.wait_for(
                        call.play(
                            chat_id,
                            MediaStream(temp, video_flags=MediaStream.Flags.IGNORE),
                            GroupCallConfig(auto_start=True),
                        ),
                        timeout=45,
                    )
                except asyncio.TimeoutError:
                    st["now"] = None
                    if os.path.exists(temp):
                        os.remove(temp)
                    return await status.edit(
                        "❌ **Join timed out.** Possible reasons:\n"
                        "• No permission to start/manage voice chat in that group\n"
                        "• Telegram servers slow — try again in a minute"
                    )

                await status.edit(
                    f"🎙️ **Streaming Live!**\n\n"
                    f"📍 **Chat:** `{chat_id}`\n"
                    f"🎶 **Now:** `{label}`\n"
                    f"📋 **Queue:** `{len(st['queue'])}`"
                )
            else:
                st["queue"].append((temp, label))
                await status.edit(
                    f"➕ **Queued:** `{label}`\n"
                    f"📋 **Queue:** `{len(st['queue'])}`"
                )
        except Exception as e:
            st["now"] = None
            if os.path.exists(temp):
                os.remove(temp)
            log.error(f"vc_stream error: {type(e).__name__}: {e}", exc_info=True)
            await status.edit(
                f"❌ **Stream failed:** `{type(e).__name__}`\n"
                f"```{str(e) or '(no message)'}```"
            )

    # ---------------- 3. .vcqueue ----------------
    @client.on(events.NewMessage(chats='me', pattern=r'^\.vcqueue$'))
    async def vc_queue(event):
        st = state(event.sender_id)
        if not st or (st["now"] is None and not st["queue"]):
            return await event.edit("❌ Nothing is playing right now.")
        text = f"🎶 **Now:** `{st['now']}`\n📋 **Queue:**\n"
        if st["queue"]:
            text += "\n".join(
                f"`{i}.` {label}" for i, (_, label) in enumerate(st["queue"], 1)
            )
        else:
            text += "`(empty)`"
        await event.edit(text)

    # ---------------- 4. .vcskip ----------------
    @client.on(events.NewMessage(chats='me', pattern=r'^\.vcskip$'))
    async def vc_skip(event):
        st = state(event.sender_id)
        if not st or st["now"] is None:
            return await event.edit("❌ Nothing is playing right now.")

        if st["queue"]:
            await event.edit("⏭️ **Skipping to next track...**")
            await play_next(event.sender_id)
        else:
            await event.edit(
                "⚠️ **Queue is empty.** Current track will keep playing. "
                "Queue more with `.vcstream` or stop with `.vcstop`."
            )

    # ---------------- 5. .vcstop ----------------
    @client.on(events.NewMessage(chats='me', pattern=r'^\.vcstop$'))
    async def vc_stop(event):
        st = state(event.sender_id)
        if not st:
            return await event.edit("❌ No active VC session found.")

        try:
            if st["chat"]:
                await st["call"].leave_call(st["chat"])
        except Exception as e:
            log.warning(f"leave_call: {type(e).__name__}: {e}")

        cleanup_files(event.sender_id)
        VC.pop(event.sender_id, None)
        await event.edit(
            "🛑 **Stream stopped.**\n"
            "Left voice chat • Queue cleared • Cache cleaned."
        )

    # ---------------- 6. .vchelp ----------------
    @client.on(events.NewMessage(chats='me', pattern=r'^\.vchelp$'))
    async def vc_help(event):
        await event.edit(
            "🎧 **VC Stream — Commands** (Saved Messages only)\n\n"
            "🎯 `.vctarget @group` — Lock target group (link/username/ID)\n"
            "🎙️ `.vcstream` — Reply to audio/voice: go live in the VC\n"
            "📋 `.vcqueue` — Show current track and queue\n"
            "⏭️ `.vcskip` — Skip to next queued track\n"
            "🛑 `.vcstop` — Stop stream, leave VC, clear queue & cache\n"
            "❓ `.vchelp` — Show this help\n\n"
            "**Flow:** `.vctarget @group` → reply audio `.vcstream` → enjoy → `.vcstop`"
        )
