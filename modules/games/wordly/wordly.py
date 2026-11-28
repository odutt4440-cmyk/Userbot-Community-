import time
import requests
import re
import asyncio
import os
from collections import Counter
from telethon import events

FOLDER = os.path.dirname(__file__)
DICT_CACHE = os.path.join(FOLDER, "wordly_dict.txt")

DEBUG = False  # Set True to see logs while debugging

def log(*args):
    if DEBUG:
        print("[WORDLY]", *args, flush=True)

def load_words():
    valid = []
    if os.path.exists(DICT_CACHE):
        try:
            with open(DICT_CACHE, "r", encoding="utf-8") as f:
                for w in f:
                    w = w.strip().lower()
                    if 3 <= len(w) <= 12 and w.isalpha():
                        valid.append(w)
            if len(valid) > 10000:
                valid.sort(key=len, reverse=True)
                return valid
        except: pass

    urls = [
        "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt",
        "https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt"
    ]

    for url in urls:
        try:
            resp = requests.get(url, timeout=15)
            data = resp.text.splitlines()
            temp = [w.strip().lower() for w in data if 3 <= len(w.strip()) <= 12 and w.strip().isalpha()]
            if temp:
                valid = list(set(temp))
                valid.sort(key=len, reverse=True)
                try:
                    with open(DICT_CACHE, "w", encoding="utf-8") as f:
                        f.write("\n".join(valid))
                except: pass
                return valid
        except: continue
    return []

# Load dictionary on startup (Sorted!)
WORDS_DB = load_words()

# 🔥 Both bots are the same game — Wordly + Wordgamez dono supported
GAME_BOTS = ("woordlybot", "wordgamezbot")

def register(client):
    client.w_game_states = {}
    client.w_enabled = True
    client.w_target_chat = None
    client.w_loop = False
    client.w_delay = 0.15          # fast default (timer-friendly)
    client.w_last_cmd = "/new"
    client.w_active_bot = "woordlybot"   # 🔥 kaunsa bot active hai
    client.w_letter_cache = {}     # letters -> pre-filtered candidates

    def solve(bot_id):
        state = client.w_game_states.get(bot_id)
        if not state or not state.get('letters') or not WORDS_DB: return None

        letters_key = state['letters'].lower()
        allowed_set = set(letters_key)
        board_counts = Counter(letters_key)

        # CACHE: isi letter-set ke liye ek baar filter karo.
        # 300k+ words ka scan har guess par nahi hoga — 10-50x faster.
        cands = client.w_letter_cache.get(letters_key)
        if cands is None:
            cands = []
            for w in WORDS_DB:
                if set(w).issubset(allowed_set):
                    wc = Counter(w)
                    if all(wc[c] <= board_counts[c] for c in wc):
                        cands.append(w)
            client.w_letter_cache[letters_key] = cands
            log(f"cached {len(cands)} candidates for {letters_key!r}")

        for word in cands:
            if word in state['used']: continue
            state['used'].add(word)
            return word.capitalize()
        return None

    def extract_letters(text):
        if "▶️" in text:
            part = text.split("▶️")[1].split("\n")[0]
            letters = "".join(re.findall(r"[A-Z]", part.upper()))
            if letters: return letters

        if "📺" in text:
            part = text.split("📺")[1].split("\n")[0]
            letters = "".join(re.findall(r"[A-Z]", part.upper()))
            if letters: return letters

        match = re.search(r"(?i)letters[:\s]+([A-Z,\s]+)", text)
        if match:
            return "".join(re.findall(r"[A-Z]", match.group(1).upper()))

        return ""

    async def send_word(event, word):
        try:
            await asyncio.sleep(client.w_delay)
            await client.send_message(event.chat_id, word)
            log(f"sent: {word}")
        except Exception as e:
            log(f"send failed: {e}")

    @client.on(events.NewMessage(chats='me'))
    async def control_panel(event):
        text = event.raw_text.lower().strip()
        if text == ".won":
            client.w_enabled = True
            await event.edit("✅ **Wordly Master: ONLINE**")
        elif text == ".woff":
            client.w_enabled = False
            client.w_target_chat = None
            await event.edit("❌ **Wordly Master: OFFLINE**")
        elif text.startswith(".wloop"):
            client.w_loop = "on" in text
            await event.edit(f"{'🔄' if client.w_loop else '❌'} **Auto-Loop:** {'ON' if client.w_loop else 'OFF'}")
        elif text.startswith(".wdelay"):
            # robust parsing — ".wdelay" (bina number) current value dikhata hai
            parts = text.split()
            if len(parts) == 1:
                await event.edit(f"⚡ **Current Delay:** {client.w_delay}s\n\nUsage: `.wdelay 0.2`")
                return
            try:
                val = float(parts[1])
                if val < 0: raise ValueError
                client.w_delay = val
                await event.edit(f"⚡ **Delay Set:** {val}s")
            except ValueError:
                await event.edit("❌ Invalid delay. Example: `.wdelay 0.2`")

    @client.on(events.NewMessage(outgoing=True))
    async def detect_new_game(event):
        if not client.w_enabled: return
        text = event.raw_text.lower().strip()

        # 🔥 Lock on WoordlyBot / WordgamezBot commands (/new, /play).
        # Bare /new aur /play allowed, ya in dono bots ka mention.
        m = re.match(r"^/(new|play)(@\S+)?$", text)
        if m:
            mentioned = (m.group(2) or "").lower()
            if mentioned in ("", "@woordlybot", "@wordgamezbot"):
                # 🔥 Track kaunsa bot active hai (mention na ho toh default)
                client.w_active_bot = mentioned.lstrip("@") if mentioned else "woordlybot"
                client.w_target_chat = event.chat_id
                client.w_last_cmd = event.raw_text
                client.w_game_states = {}
                client.w_letter_cache = {}   # naye board ke liye cache reset

                try:
                    await client.send_message("me", f"🎯 **Wordly Locked!**\nChat ID: `{event.chat_id}`\nBot: `@{client.w_active_bot}`\nFast Mode: ON 🚀")
                except: pass

    @client.on(events.NewMessage)
    async def game_handler(event):
        if not client.w_enabled or client.w_target_chat is None: return
        if event.chat_id != client.w_target_chat: return
        if event.out: return

        # 🔥 Sirf ACTIVE bot ke messages process karo (Woordly ya Wordgamez —
        # jo last command bheja usi pe lock). Baaki bot ignore.
        sender = await event.get_sender()
        sender_name = (getattr(sender, "username", "") or "").lower()

        active = getattr(client, "w_active_bot", "woordlybot")
        if active and active in sender_name:
            pass  # active bot — process karo
        elif not active and any(b in sender_name for b in GAME_BOTS):
            pass  # fallback — koi bhi game bot chalega
        else:
            return

        msg = event.raw_text or ""
        msg_up = msg.upper()
        bot_id = event.sender_id

        found_match = re.search(r'(?i)found ["«](\w+)["»]', msg)
        if found_match:
            found_word = found_match.group(1).lower()
            if bot_id in client.w_game_states:
                client.w_game_states[bot_id]['used'].add(found_word)

        progress_match = re.search(r"(?i)Total(?: words found)?:\s*(\d+)\s*/\s*(\d+)", msg)
        is_board_msg = "WORD SCRAMBLE" in msg_up or "📺" in msg or "▶️" in msg or progress_match

        if is_board_msg:
            letters = extract_letters(msg)

            if bot_id not in client.w_game_states or (progress_match and int(progress_match.group(1)) == 0):
                client.w_game_states[bot_id] = {
                    'letters': letters,
                    'used': set()
                }

            if letters:
                client.w_game_states[bot_id]['letters'] = letters

            if progress_match:
                curr, goal = int(progress_match.group(1)), int(progress_match.group(2))
                if curr >= goal:
                    if client.w_loop:
                        await asyncio.sleep(5)
                        await client.send_message(event.chat_id, client.w_last_cmd)
                    return

            word = solve(bot_id)
            if word:
                await send_word(event, word)
            return

        # Instant Recovery
        if "ALREADY FOUND" in msg_up or "NOT A VALID" in msg_up or "NOT VALID" in msg_up:
            word = solve(bot_id)
            if word:
                await send_word(event, word)
