import asyncio
import random
import re
import os
from collections import defaultdict
from telethon import events
from telethon.tl.functions.messages import DeleteMessagesRequest, SetTypingRequest
from telethon.tl.types import SendMessageTypingAction

# ==================================================
# SHARED DICTIONARY (Load once to save RAM)
# ==================================================
WORDS = set()
STARTS = defaultdict(list)
FOLDER = os.path.dirname(__file__)
DICT_FILE = os.path.join(FOLDER, "dictionary.txt")

def load_dictionary():
    if WORDS: return 
    if not os.path.exists(DICT_FILE):
        print(f"⚠️ WordChain: {DICT_FILE} not found!")
        return
    with open(DICT_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            w = line.strip().lower()
            if w.isalpha():
                WORDS.add(w)
                STARTS[w[0]].append(w)
    print(f"[✓] WordChain Dictionary Loaded: {len(WORDS)} words")

load_dictionary()

# ==================================================
# THE MODULE REGISTER
# ==================================================
def register(client):
    # --- Per-User State (Fully Isolated for Multi-GC) ---
    client.wc_active_games = {} # {chat_id: {"used": set(), "title": str}}
    client.wc_autoplay = {}     
    client.wc_spam_mode = {}    # Per-chat Spam logic
    client.wc_banned_ends = {}  # Per-chat Banned logic
    client.wc_delays = {}       # 🔥 NEW: Per-chat Delay logic {chat_id: (min, max)}
    
    client.wc_global_min = 4    # Default Fallback
    client.wc_global_max = 8
    client.wc_me = None
    client.wc_delete_saved = True

    # --- HELPERS ---
    async def get_me():
        if not client.wc_me:
            client.wc_me = await client.get_me()
        return client.wc_me

    async def typing(chat_id):
        # 🔥 Pull delay for specific chat, else use global
        d_min, d_max = client.wc_delays.get(chat_id, (client.wc_global_min, client.wc_global_max))
        delay = random.uniform(d_min, d_max)
        try:
            await client(SetTypingRequest(peer=chat_id, action=SendMessageTypingAction()))
        except: pass
        await asyncio.sleep(delay)

    def format_word(word):
        if not word: return word
        return word[0].upper() + word[1:]

    def get_valid_word(start=None, end=None, required=None, banned=None, used=None, min_len=1, banned_end=None):
        used = used or set()
        banned = banned or []
        pool = STARTS.get(start.lower(), []) if start else list(WORDS)
        
        pick_longest = (end == "longest")
        if end == "random":
            end = random.choice(list("abcdefghijklmnopqrstuvwxyz"))
        elif pick_longest:
            end = None

        def is_perfect(w):
            if w in used or len(w) < min_len: return False
            if end and not w.endswith(end): return False
            if banned_end and w.endswith(banned_end): return False
            if required and required not in w: return False
            if any(b in w for b in banned): return False
            return True

        candidates = [w for w in pool if is_perfect(w)]
        if candidates:
            return max(candidates, key=len) if pick_longest else random.choice(candidates)

        fallback = [w for w in pool if (w not in used and len(w) >= min_len and 
                   (not banned_end or not w.endswith(banned_end)) and 
                   (not required or required in w) and not any(b in w for b in banned))]
        if fallback:
            return max(fallback, key=len) if pick_longest else random.choice(fallback)

        any_valid = [w for w in pool if w not in used and len(w) >= min_len and (not banned_end or not w.endswith(banned_end))]
        return max(any_valid, key=len) if (any_valid and pick_longest) else (random.choice(any_valid) if any_valid else None)

    # ==================================================
    # SAVED MESSAGE COMMANDS (THE CONTROL PANEL)
    # ==================================================
    @client.on(events.NewMessage(chats="me"))
    async def saved_commands(event):
        raw_text = (event.raw_text or "").lower().strip()
        
        # --- 🎯 STEP 1: TARGET PARSER (onX extractor) ---
        target_chat = None
        clean_command = raw_text
        match_on = re.search(r"(.*)\s+on(\d+)$", raw_text)
        
        if match_on:
            clean_command = match_on.group(1).strip()
            idx = int(match_on.group(2))
            chats = list(client.wc_active_games.keys())
            if idx <= len(chats):
                target_chat = chats[idx - 1]
            else:
                return await client.send_message("me", f"❌ **Error:** Group `on{idx}` not found.")
        else:
            if client.wc_active_games:
                target_chat = list(client.wc_active_games.keys())[-1]

        # 🟢 Command: on1, on2 (Join Game)
        if raw_text.startswith("on") and not " " in raw_text:
            num = raw_text.replace("on", "").strip()
            if num.isdigit():
                idx = int(num)
                chats = list(client.wc_active_games.keys())
                if idx <= len(chats):
                    cid = chats[idx - 1]
                    title = client.wc_active_games[cid]['title']
                    try:
                        m = await client.send_message(cid, "/join")
                        await asyncio.sleep(1)
                        try: await client.delete_messages(cid, [m.id])
                        except: pass
                        client.wc_autoplay[cid] = True
                        await client.send_message("me", f"✅ **SUCCESS:** Joined `{title}` (on{idx}) with Autoplay ON.")
                    except Exception as e:
                        await client.send_message("me", f"❌ **FAILED:** Could not join `{title}`. Error: {e}")
                
                if client.wc_delete_saved: await event.delete()
            return

        # --- 🚫 COMMAND: BAN ---
        if clean_command.startswith("ban "):
            if not target_chat: return
            letter = clean_command.replace("ban ", "").strip().lower()
            if len(letter) == 1:
                client.wc_banned_ends[target_chat] = letter
                if client.wc_spam_mode.get(target_chat) == letter:
                    client.wc_spam_mode[target_chat] = None
                gn = client.wc_active_games[target_chat]['title']
                await client.send_message("me", f"🚫 **Banned Ending:** `{letter.upper()}` for `{gn}`")

        # --- ⚪ COMMAND: UNBAN ---
        elif clean_command.startswith("unban "):
            if not target_chat: return
            letter = clean_command.replace("unban ", "").strip().lower()
            if client.wc_banned_ends.get(target_chat) == letter:
                del client.wc_banned_ends[target_chat]
                gn = client.wc_active_games[target_chat]['title']
                await client.send_message("me", f"✅ **Unbanned:** `{letter.upper()}` for `{gn}`")

        # --- 🔥 COMMAND: SPAM ---
        elif clean_command.startswith("spam "):
            if not target_chat: return
            mode = clean_command.replace("spam ", "").strip().lower()
            if len(mode) == 1 and client.wc_banned_ends.get(target_chat) == mode:
                await client.send_message("me", f"❌ **Conflict:** `{mode.upper()}` is BANNED in this group.")
                return
            client.wc_spam_mode[target_chat] = mode
            gn = client.wc_active_games[target_chat]['title']
            await client.send_message("me", f"🔥 **Spam Mode:** `{mode.upper()}` for `{gn}`")

        # --- 📊 COMMAND: STATUS ---
        elif clean_command == "status":
            if not client.wc_active_games:
                return await client.send_message("me", "❌ No active games detected.")
            
            # If 'status on1' -> Show specific details
            if match_on:
                idx = int(match_on.group(2))
                chats = list(client.wc_active_games.keys())
                cid = chats[idx - 1]
                data = client.wc_active_games[cid]
                b = (client.wc_banned_ends.get(cid) or "None").upper()
                s = (client.wc_spam_mode.get(cid) or "None").upper()
                d_min, d_max = client.wc_delays.get(cid, (client.wc_global_min, client.wc_global_max))
                msg = (f"📑 **Group Details: on{idx}**\n\n"
                       f"🏷️ **Title:** `{data['title']}`\n"
                       f"🔥 **Spam:** `{s}`\n"
                       f"🚫 **Ban:** `{b}`\n"
                       f"⏱️ **Delay:** `{d_min}-{d_max}s`\n"
                       f"🎮 **Used Words:** `{len(data['used'])}`")
                await client.send_message("me", msg)
            else:
                # If just 'status' -> Show overall list
                msg = "🤖 **WordChain Pro Dashboard**\n\n"
                for i, (cid, data) in enumerate(client.wc_active_games.items(), 1):
                    msg += f"**on{i}** - `{data['title']}`\n"
                msg += "\n👉 _Type 'status on1' for full details._"
                await client.send_message("me", msg)

        # --- ⏱ COMMAND: SETTIME ---
        elif clean_command.startswith("settime"):
            if not target_chat: return
            parts = clean_command.split()
            if len(parts) == 3:
                s_min, s_max = int(parts[1]), int(parts[2])
                client.wc_delays[target_chat] = (s_min, s_max)
                gn = client.wc_active_games[target_chat]['title']
                await client.send_message("me", f"✅ **Delay Set:** {s_min}-{s_max}s for `{gn}`")

        if client.wc_delete_saved: await event.delete()

    # ==================================================
    # GAME DETECTION
    # ==================================================
    GAME_PATTERNS = ["/startclassic", "/startchaos", "/starthard", "/startelim", "/startmelim", "/startrfl", "/startrl", "/startbl", "the first word is", "turn order"]

    @client.on(events.NewMessage)
    async def game_monitor(event):
        if event.is_private: return
        text = (event.raw_text or "").lower()

        if any(p in text for p in GAME_PATTERNS):
            if event.chat_id not in client.wc_active_games:
                
                title = getattr(event.chat, "title", "Unknown Group")
                client.wc_active_games[event.chat_id] = {"used": set(), "title": title}
                game_no = len(client.wc_active_games)
                
                # 🔥 Notification with GC Name
                await client.send_message("me", 
                    f"🎮 **GAME DETECTED**\n"
                    f"📍 **GC:** `{title}`\n"
                    f"🆔 **ID:** `on{game_no}`\n\n"
                    f"👉 Type `on{game_no}` to join this group.")


        me = await get_me()
        my_names = [me.first_name.lower()]
        if me.username: my_names.append(me.username.lower())
        if "joined" in text and any(n in text for n in my_names):
            client.wc_active_games.setdefault(event.chat_id, {"used": set(), "title": "Unknown"})
            client.wc_autoplay[event.chat_id] = True
            await client.send_message("me", f"⚡ **AUTOPLAY ACTIVE**")

        if event.chat_id not in client.wc_autoplay or not client.wc_autoplay[event.chat_id]:
            return

        word_used_match = re.search(r"([a-z]+)\s+(is accepted|has been used)", text)
        if word_used_match:
            client.wc_active_games[event.chat_id]["used"].add(word_used_match.group(1).lower())

        if "turn:" not in text: return
        turn_match = re.search(r"turn:\s*([^\(\n]+)", text)
        if not turn_match or not any(n in turn_match.group(1).lower() for n in my_names):
            return

        start_letter = None
        if "start with" in text:
            m = re.search(r"start with\s*([a-z])", text)
            if m: start_letter = m.group(1).lower()
        elif word_used_match:
            start_letter = word_used_match.group(1)[-1]

        if not start_letter: return

        # 🔥 FIXED CONSTRAINTS EXTRACTION (Handles Uppercase from Game Bot)
        # 1. Required Letter (Handles A or a)
        req = re.search(r"include\s+([a-zA-Z])", text)
        
        # 2. Banned Letters (Handles D, F, M etc.)
        ban_req = re.search(r"exclude\s+(.*?)(?:and|\.|\n|letters)", text)
        banned_list = []
        if ban_req:
            # [a-zA-Z] use kiya taaki Uppercase bhi pakad sake aur lower() kiya taaki dictionary se match ho
            banned_list = [b.lower() for b in re.findall(r"[a-zA-Z]", ban_req.group(1))]

        # 3. Min Length
        ml = re.search(r"at least\s+(\d+)", text)
        
        # FIND WORD
        word = get_valid_word(
            start=start_letter,
            end=client.wc_spam_mode.get(event.chat_id),
            required=req.group(1).lower() if req else None,
            banned=banned_list, # Updated list
            used=client.wc_active_games[event.chat_id]["used"],
            min_len=int(ml.group(1)) if ml else 1,
            banned_end=client.wc_banned_ends.get(event.chat_id)
        )
        
        if word:
            client.wc_active_games[event.chat_id]["used"].add(word)
            await typing(event.chat_id)
            await client.send_message(event.chat_id, format_word(word))
