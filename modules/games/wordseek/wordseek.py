import json
import random
import asyncio
import unicodedata
import os
import re
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

# All possible feedback emojis
FEEDBACK_EMOJIS = ["🟩", "🟨", "🟥", "🟧", "🟦", "⬜", "⬛", "🟪", "🟢", "🟡", "🔴", "🟠", "🔵"]

# Invisible characters
INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad\u180e\u2062-\u2065\u200d\u200c]")

def clean_text(text: str) -> str:
    return INVISIBLE.sub("", text)

def register(client):
    # --- Per-User State ---
    client.ws_enabled = True
    client.ws_chat = None
    client.ws_delay_min = 0.05
    client.ws_delay_max = 0.15
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

    # 🔥 1. Normal Text Parser (For old format)
    def parse_feedback_text(text):
        lines = text.splitlines()
        target = None
        for line in reversed(lines):
            if any(emoji in line for emoji in FEEDBACK_EMOJIS):
                target = line.strip()
                break
        if not target: return None
        
        target = target.replace(" ", "")
        feedback = []
        guess = ""
        for char in target:
            if char in FEEDBACK_EMOJIS:
                feedback.append(char)
            elif char.isalpha():
                guess += char.lower()
                
        if not guess or len(feedback) != len(guess): return None
        return guess, feedback

    # 🔥 2. NEW Button Parser (For the new update)
    def parse_feedback_buttons(event):
        if not event.reply_markup: return None
        guess = ""
        feedback = []
        
        for row in event.reply_markup.rows:
            for button in row.buttons:
                text = getattr(button, 'text', '').strip()
                letter = "".join([c for c in text if c.isalpha()]).lower()
                
                if len(letter) == 1:
                    guess += letter
                    data_str = str(getattr(button, 'data', '')).lower()
                    
                    # Check button text or callback data for color hints
                    if 'green' in data_str or 'correct' in data_str or '🟩' in text or '🟢' in text:
                        feedback.append('🟩')
                    elif 'yellow' in data_str or 'present' in data_str or '🟨' in text or '🟡' in text:
                        feedback.append('🟨')
                    elif 'red' in data_str or 'absent' in data_str or '🟥' in text or '🔴' in text:
                        feedback.append('🟥')
                    else:
                        # Agar data me color nahi mila, toh default red maan lo (ya debug karne ke liye None bhejo)
                        # Hum assume kar rahe hain ki jo galat hoga wo red hoga
                        feedback.append('🟥') 
                        
        if guess and len(feedback) == len(guess):
            return guess, feedback
        return None

    def apply_constraints(guess, feedback):
        confirmed = Counter()
        for i, state in enumerate(feedback):
            char = guess[i]
            if state in ["🟩", "🟢"]:
                client.ws_green[i] = char
                confirmed[char] += 1
        for i, state in enumerate(feedback):
            char = guess[i]
            if state in ["🟨", "🟡"]:
                if char not in client.ws_yellow: client.ws_yellow[char] = set()
                client.ws_yellow[char].add(i)
                confirmed[char] += 1
        for i, state in enumerate(feedback):
            char = guess[i]
            if state in ["🟥", "⬜", "⬛", "🔴"]:
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
    # COMMANDS
    # =========================================
    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws (on|off)$"))
    async def toggle_ws(event):
        client.ws_enabled = event.pattern_match.group(1).lower() == "on"
        await event.edit(f"{'✅' if client.ws_enabled else '❌'} **WordSeek Solver {'Enabled' if client.ws_enabled else 'Disabled'}**")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws loop (on|off)$"))
    async def toggle_loop(event):
        client.ws_loop = event.pattern_match.group(1).lower() == "on"
        await event.edit(f"{'♻️' if client.ws_loop else '❌'} **Auto Loop {'Enabled' if client.ws_loop else 'Disabled'}**")

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

        m = re.match(r"^/new[46]?(@\S+)?$", text)
        if m:
            mentioned = (m.group(1) or "").lower()
            if mentioned in ("", "@wordseekbot"):
                client.ws_loop_cmd = re.match(r"^/new[46]?", text).group(0)
                client.ws_chat = event.chat_id
                reset_state()
                if "4" in text: load_mode(4)
                elif "6" in text: load_mode(6)
                else: load_mode(5)
                try: await client.send_message("me", f"🎯 **WordSeek Locked!**\nChat: `{event.chat_id}`")
                except: pass

    @client.on(events.NewMessage)
    async def solver(event):
        if not client.ws_enabled or event.chat_id != client.ws_chat: return
        sender = await event.get_sender()
        if not sender: return
        sender_username = (getattr(sender, "username", "") or "").lower()
        if sender_username != "wordseekbot": return

        text = clean_text(event.raw_text or "")

        if any(x in text for x in ["Congrats!", "Game Over!"]):
            reset_state()
            if client.ws_loop and client.ws_loop_cmd:
                await asyncio.sleep(random.uniform(2.5, 4.5))
                await client.send_message(client.ws_chat, client.ws_loop_cmd)
            return

        if "Game started!" in text:
            guess = get_next_guess()
            if guess:
                client.ws_used.add(guess.lower())
                await asyncio.sleep(random.uniform(client.ws_delay_min, client.ws_delay_max))
                await client.send_message(event.chat_id, guess)
            return

        # 🔥 TRY BOTH PARSERS (Text and Buttons)
        res = parse_feedback_text(text)
        if not res:
            res = parse_feedback_buttons(event)
            
        if not res:
            # DEBUG: Agar dono fail ho jayein toh saved messages mein bhejo
            if event.reply_markup:
                try: await client.send_message("me", f"⚠️ **Debug - Buttons Not Parsed:**\n\nText: `{text}`\nButtons: `{event.reply_markup}`")
                except: pass
            return
            
        guess, feedback = res
        if guess == client.ws_last_guess: return
        client.ws_last_guess = guess

        apply_constraints(guess, feedback)
        next_guess = get_next_guess()
        
        if next_guess:
            client.ws_used.add(next_guess.lower())
            async with client.action(event.chat_id, "typing"):
                await asyncio.sleep(random.uniform(client.ws_delay_min, client.ws_delay_max))
                await client.send_message(event.chat_id, next_guess)
        else:
            fallback = [w for w in client.ws_words if w.lower() not in client.ws_used]
            if fallback:
                await client.send_message(event.chat_id, fallback[0].capitalize())
