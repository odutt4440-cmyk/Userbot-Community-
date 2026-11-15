import time
import requests
import re
import asyncio
import os
from collections import Counter
from telethon import events

FOLDER = os.path.dirname(__file__)
DICT_CACHE = os.path.join(FOLDER, "wordly_dict.txt")

DEBUG = False # Fast play ke liye logs band kar diye hain

def log(*args):
    if DEBUG:
        print("[WORDLY]", *args)

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
                # 🔥 FIX: Sorting sirf ek baar hogi jab load hoga (Fast play)
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
                # 🔥 FIX: Sorting ek baar
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

def register(client):
    client.w_game_states = {} 
    client.w_enabled = True
    client.w_target_chat = None 
    client.w_loop = False
    client.w_delay = 0.5  # 🔥 Fast delay (half second)
    client.w_last_cmd = "/new"

    def solve(bot_id):
        state = client.w_game_states.get(bot_id)
        if not state or not state.get('letters') or not WORDS_DB: return None
        
        allowed_set = set(state['letters'].lower())
        board_counts = Counter(state['letters'].lower())
        
        # 🔥 FIX: Ab sorting baar-baar nahi hogi, direct sorted list me se dhundega
        for word in WORDS_DB:
            if word in state['used']: continue
            
            if set(word).issubset(allowed_set):
                word_counts = Counter(word)
                if all(word_counts[c] <= board_counts[c] for c in word_counts):
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
            try:
                client.w_delay = float(text.split()[1])
                await event.edit(f"⚡ **Delay:** {client.w_delay}s")
            except: pass

    @client.on(events.NewMessage(outgoing=True))
    async def detect_new_game(event):
        if not client.w_enabled: return
        text = event.raw_text.lower().strip()
        
        if text.startswith("/new") or text.startswith("/play"):
            client.w_target_chat = event.chat_id
            client.w_last_cmd = event.raw_text
            client.w_game_states = {}
            
            try:
                await client.send_message("me", f"🎯 **Wordly Locked!**\nChat ID: `{event.chat_id}`\nFast Mode: ON 🚀")
            except: pass

    @client.on(events.NewMessage)
    async def game_handler(event):
        if not client.w_enabled or client.w_target_chat is None: return
        if event.chat_id != client.w_target_chat: return
        if event.out: return 
        
        msg = event.raw_text
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

            # 🔥 FIX: Typing animation hatadi taaki fast chale
            word = solve(bot_id)
            if word:
                try:
                    await asyncio.sleep(client.w_delay) # Sirf chhota sa delay
                    await client.send_message(event.chat_id, word)
                except: pass
            return

        # Instant Recovery
        if "ALREADY FOUND" in msg_up or "NOT A VALID" in msg_up or "NOT VALID" in msg_up:
            word = solve(bot_id)
            if word:
                try:
                    await asyncio.sleep(client.w_delay)
                    await client.send_message(event.chat_id, word)
                except: pass
