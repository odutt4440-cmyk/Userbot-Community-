import time
import requests
import re
import asyncio
import os
from collections import Counter
from telethon import events, functions, types

# =========================================
# LOAD DICTIONARY (6-12 letters only)
# =========================================
FOLDER = os.path.dirname(__file__)
DICT_CACHE = os.path.join(FOLDER, "wordly_dict.txt")

def load_words():
    valid = []
    if not os.path.exists(DICT_CACHE):
        url = "https://raw.githubusercontent.com/dolph/dictionary/master/enable1.txt"
        try:
            data = requests.get(url).text.splitlines()
            with open(DICT_CACHE, "w") as f:
                f.write("\n".join(data))
        except: return []
    with open(DICT_CACHE, "r") as f:
        for w in f:
            w = w.strip().lower()
            if 6 <= len(w) <= 12 and w.isalpha():
                valid.append(w)
    return valid

WORDS_DB = load_words()

def register(client):
    # State tracking
    client.w_game_states = {}
    client.w_enabled = True
    client.w_target_chat = None # 🔥 Stores the ID where /new was sent
    client.w_loop = False
    client.w_delay = 0.5
    client.w_last_cmd = "/new"

    # --- ADVANCED SOLVER ---
    def solve(bot_id):
        state = client.w_game_states.get(bot_id)
        if not state or not state.get('letters'): return None
        
        allowed_set = set(state['letters'].lower())
        board_counts = Counter(state['letters'].lower())
        
        for word in WORDS_DB:
            if word in state['used']: continue
            
            word_set = set(word)
            if word_set.issubset(allowed_set):
                if not state['can_repeat']:
                    word_counts = Counter(word)
                    if all(word_counts[c] <= board_counts[c] for c in word_counts):
                        state['used'].add(word)
                        return word.capitalize()
                else:
                    state['used'].add(word)
                    return word.capitalize()
        return None

    # --- ROBUST LETTER EXTRACTOR ---
    def extract_letters(text):
        text_up = text.upper()
        if "," in text: # WordgamezBot
            match = re.search(r"(?:^|\n)\s*([A-Z],\s*)+[A-Z]\s*(?:\n|$)", text_up)
            if match: return "".join(re.findall(r"[A-Z]", match.group(0)))
        if "ACTIVE LETTERS:" in text_up: # WordlyGamingBot
            part = text_up.split("ACTIVE LETTERS:")[1].splitlines()[0]
            return "".join(re.findall(r"[A-Z]", part))
        match = re.search(r"[\(\u2934]\s*([A-Z\s]+)\s*[\)\u2935]", text_up)
        if match: return "".join(re.findall(r"[A-Z]", match.group(1)))
        return "".join(re.findall(r"\b[A-Z]\b", text_up))

    # =========================================
    # CONTROL PANEL (.won, .woff, .wloop, .wdelay)
    # =========================================
    @client.on(events.NewMessage(chats='me'))
    async def control_panel(event):
        text = event.raw_text.lower().strip()
        if text == ".won":
            client.w_enabled = True
            await event.edit("✅ **Wordly Master: ONLINE**")
        elif text == ".woff":
            client.w_enabled = False
            client.w_target_chat = None # Reset target
            await event.edit("❌ **Wordly Master: OFFLINE**")
        elif text.startswith(".wloop"):
            client.w_loop = "on" in text
            await event.edit(f"{'🔄' if client.w_loop else '❌'} **Auto-Loop:** {'ON' if client.w_loop else 'OFF'}")
        elif text.startswith(".wdelay"):
            try:
                client.w_delay = float(text.split()[1])
                await event.edit(f"⚡ **Delay:** {client.w_delay}s")
            except: pass

    # =========================================
    # AUTO-LOCK DETECTION (Targeting Logic)
    # =========================================
    @client.on(events.NewMessage(outgoing=True))
    async def detect_new_game(event):
        if not client.w_enabled: return
        text = event.raw_text.lower()
        if text.startswith("/new"):
            # 🔥 LOCK ONTO THIS CHAT
            client.w_target_chat = event.chat_id
            client.w_last_cmd = event.raw_text
            # Clear previous session data for this chat
            client.w_game_states = {}
            
            
            await client.send_message("me", f"🎯 **Wordly Locked to Chat:** `{event.chat_id}`\nMode: `{client.w_last_cmd}`")

    # =========================================
    # GAME ENGINE (Continuous Play Fix)
    # =========================================
    @client.on(events.NewMessage)
    async def game_handler(event):
        # 🔥 CRITICAL CHECK: Enabled? and is this the target chat?
        if not client.w_enabled or client.w_target_chat is None: return
        if event.chat_id != client.w_target_chat: return
        
        # Don't respond to yourself unless it's a loop command
        if event.out: return 
        
        msg = event.raw_text
        msg_up = msg.upper()
        bot_id = event.sender_id
        chat_id = event.chat_id

        # 1. SYNC: Always record words found by anyone
        found_match = re.search(r'(?i)FOUND ["«](\w+)["»]|—\s*(\w+)|ACCEPTED! [\w\s\+]+ — (\w+)', msg)
        if found_match:
            found_word = next(w for w in found_match.groups() if w).lower()
            if bot_id in client.w_game_states:
                client.w_game_states[bot_id]['used'].add(found_word)

        # 2. PROGRESS & BOARD DETECTION
        progress_match = re.search(r"(\d+)\s*/\s*(\d+)", msg)
        is_board_msg = "LETTERS BOARD" in msg_up or "MODE IS LIVE" in msg_up or "ACTIVE LETTERS" in msg_up or progress_match
        
        if is_board_msg:
            letters = extract_letters(msg)
            
            # Init state for bot if new
            if bot_id not in client.w_game_states or "0/" in msg:
                client.w_game_states[bot_id] = {
                    'letters': letters,
                    'used': set(),
                    'can_repeat': "LETTERS CAN BE REPEATED" in msg_up
                }
            
            if letters:
                client.w_game_states[bot_id]['letters'] = letters

            # Logic to keep playing
            if progress_match:
                curr, goal = int(progress_match.group(1)), int(progress_match.group(2))
                if curr >= goal:
                    if client.w_loop:
                        await asyncio.sleep(8) # Safe delay for loop
                        await client.send_message(chat_id, client.w_last_cmd)
                    return

            # Solve and send WITHOUT replying
            word = solve(bot_id)
            if word:
                try:
                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(client.w_delay)
                        await client.send_message(chat_id, word)
                except: pass # Prevent crash on Mute
            return

        # 3. INSTANT RECOVERY on Rejection
        if "ALREADY FOUND" in msg_up or "NOT A VALID" in msg_up:
            word = solve(bot_id)
            if word:
                try:
                    async with client.action(chat_id, 'typing'):
                        await asyncio.sleep(client.w_delay)
                        await client.send_message(chat_id, word)
                except: pass

        # 4. GAME OVER Loop Fallback
        elif any(x in msg_up for x in ["GAME OVER", "CONGRATS"]):
            if client.w_loop:
                await asyncio.sleep(8)
                await client.send_message(chat_id, client.w_last_cmd)
