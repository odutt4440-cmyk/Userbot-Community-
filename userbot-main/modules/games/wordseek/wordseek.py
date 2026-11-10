import json
import random
import asyncio
import unicodedata
import os
from collections import Counter
from telethon import events

# =========================================
# LOAD WORDLISTS (Shared Memory)
# =========================================
FOLDER = os.path.dirname(__file__)

def load_json(filename):
    path = os.path.join(FOLDER, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

ALL4 = load_json("all-four.json")
COMMON4 = load_json("common-four.json")
ALL5 = load_json("all-five.json")
COMMON5 = load_json("common-five.json")
ALL6 = load_json("all-six.json")
COMMON6 = load_json("common-six.json")

STARTERS = {4: "Care", 5: "Slate", 6: "Retain"}

# =========================================
# THE MODULE REGISTER
# =========================================
def register(client):
    # --- Per-User State ---
    client.ws_enabled = True
    client.ws_chat = None
    client.ws_delay_min = 0.05 # Default delay
    client.ws_delay_max = 0.15 # Default delay
    client.ws_mode = 5
    client.ws_loop = False
    client.ws_loop_cmd = "/new" 
    
    client.ws_words = ALL5.copy()
    client.ws_common = COMMON5.copy()
    client.ws_used = set()
    client.ws_green = {}
    client.ws_yellow = {}
    client.ws_black = set()
    client.ws_last_guess = None

    # --- HELPERS ---
    def reset_state():
        client.ws_green = {}
        client.ws_yellow = {}
        client.ws_black = set()
        client.ws_used = set()
        client.ws_last_guess = None

    def load_mode(mode):
        client.ws_mode = mode
        if mode == 4:
            client.ws_words = ALL4.copy()
            client.ws_common = COMMON4.copy()
        elif mode == 6:
            client.ws_words = ALL6.copy()
            client.ws_common = COMMON6.copy()
        else:
            client.ws_words = ALL5.copy()
            client.ws_common = COMMON5.copy()

    def clean_word(word):
        result = ""
        for ch in word:
            normalized = unicodedata.normalize("NFKD", ch)
            for c in normalized:
                if c.isalpha(): result += c.lower()
        return result

    def parse_feedback(text):
        lines = text.splitlines()
        target = None
        for line in reversed(lines):
            if any(emoji in line for emoji in ["🟩", "🟨", "🟥"]):
                target = line.strip()
                break
        if not target: return None
        parts = target.split()
        feedback = []
        guess = None
        for part in parts:
            if part in ["🟩", "🟨", "🟥"]:
                feedback.append(part)
            else:
                cleaned = clean_word(part)
                if cleaned: guess = cleaned
        if not guess or len(feedback) != len(guess): return None
        return guess, feedback

    def apply_constraints(guess, feedback):
        confirmed = Counter()
        for i, state in enumerate(feedback):
            char = guess[i]
            if state == "🟩":
                client.ws_green[i] = char
                confirmed[char] += 1
        for i, state in enumerate(feedback):
            char = guess[i]
            if state == "🟨":
                if char not in client.ws_yellow: client.ws_yellow[char] = set()
                client.ws_yellow[char].add(i)
                confirmed[char] += 1
        for i, state in enumerate(feedback):
            char = guess[i]
            if state == "🟥":
                if confirmed[char] == 0: client.ws_black.add(char)

    def valid_word(word):
        word = word.lower()
        if len(word) != client.ws_mode: return False
        for pos, char in client.ws_green.items():
            if word[pos] != char: return False
        for char, bad_positions in client.ws_yellow.items():
            if char not in word: return False
            for pos in bad_positions:
                if word[pos] == char: return False
        for char in client.ws_black:
            if char in word and char not in client.ws_yellow and char not in client.ws_green.values():
                return False
        return True

    def get_next_guess():
        v_common = [w for w in client.ws_common if valid_word(w) and w.lower() not in client.ws_used]
        v_all = [w for w in client.ws_words if valid_word(w) and w.lower() not in client.ws_used]
        if not client.ws_used: return STARTERS.get(client.ws_mode, "Slate")
        pool = v_common if v_common else v_all
        if not pool: return None
        freq = Counter()
        for w in pool:
            for char in set(w.lower()): freq[char] += 1
        pool.sort(key=lambda w: sum(freq[c] for c in set(w.lower())), reverse=True)
        return pool[0].capitalize()

    # =========================================
    # COMMANDS (Saved Messages Control)
    # =========================================
    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws (on|off)$"))
    async def toggle_ws(event):
        client.ws_enabled = event.pattern_match.group(1).lower() == "on"
        await event.edit(f"{'✅' if client.ws_enabled else '❌'} **WordSeek Solver {'Enabled' if client.ws_enabled else 'Disabled'}**")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws loop (on|off)$"))
    async def toggle_loop(event):
        client.ws_loop = event.pattern_match.group(1).lower() == "on"
        await event.edit(f"{'♻️' if client.ws_loop else '❌'} **Auto Loop {'Enabled' if client.ws_loop else 'Disabled'}**")

    # NEW: Delay command added back!
    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws delay (\d+\.?\d*) (\d+\.?\d*)$"))
    async def set_delay(event):
        client.ws_delay_min = float(event.pattern_match.group(1))
        client.ws_delay_max = float(event.pattern_match.group(2))
        await event.edit(f"⚡ **WordSeek Delay Set:** {client.ws_delay_min}s - {client.ws_delay_max}s")

    # =========================================
    # MAIN ENGINE
    # =========================================
    @client.on(events.NewMessage(outgoing=True))
    async def detect_new_game(event):
        if not client.ws_enabled: return
        text = event.raw_text.lower().strip()
        if text.startswith("/new"):
            client.ws_loop_cmd = text
            client.ws_chat = event.chat_id
            reset_state()
            if "4" in text: load_mode(4)
            elif "6" in text: load_mode(6)
            else: load_mode(5)

    @client.on(events.NewMessage)
    async def solver(event):
        if not client.ws_enabled or event.chat_id != client.ws_chat: return
        sender = await event.get_sender()
        if not sender: return
        sender_username = getattr(sender, "username", "") or "" 
        if sender_username.lower() != "wordseekbot": return
        
        text = event.raw_text

        # --- GAME END DETECTION (Loop Fixed) ---
        if any(x in text for x in ["Congrats!", "Game Over!"]):
            reset_state()
            if client.ws_loop and client.ws_loop_cmd:
                # Wait before starting new game to look natural
                await asyncio.sleep(random.uniform(2.5, 4.5)) 
                await client.send_message(client.ws_chat, client.ws_loop_cmd)
            return

        if "Game started!" in text:
            guess = get_next_guess()
            if guess:
                client.ws_used.add(guess.lower())
                # Delay integrated here
                await asyncio.sleep(random.uniform(client.ws_delay_min, client.ws_delay_max))
                await client.send_message(event.chat_id, guess)
            return

        res = parse_feedback(text)
        if not res: return
        guess, feedback = res
        if guess == client.ws_last_guess: return
        client.ws_last_guess = guess
        
        apply_constraints(guess, feedback)
        next_guess = get_next_guess()
        if next_guess:
            client.ws_used.add(next_guess.lower())
            async with client.action(event.chat_id, "typing"):
                # Delay integrated here too
                await asyncio.sleep(random.uniform(client.ws_delay_min, client.ws_delay_max))
                await client.send_message(event.chat_id, next_guess)
