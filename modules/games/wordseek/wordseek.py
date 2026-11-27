import json
import random
import asyncio
import unicodedata
import os
import re
import base64
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

FEEDBACK_EMOJIS = ["🟩", "🟨", "🟥", "🟧", "🟦", "⬜", "⬛", "🟪"]

INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad\u180e\u2062-\u2065]")

# Matches the bot's rich-message buttons: data="wh:<state>:<LETTER>"
RICH_BTN = re.compile(r"data(?:-base64)?=(?:\"|&quot;|')wh:(correct|present|absent):([A-Za-z])(?:\"|&quot;|')")

def clean_text(text: str) -> str:
    return INVISIBLE.sub("", text)

def log(msg):
    print(f"[WORDSEEK] {msg}", flush=True)

def register(client):
    # --- Per-User State ---
    client.ws_enabled = True
    client.ws_debug = False
    client.ws_chat = None
    client.ws_delay_min = 0.05
    client.ws_delay_max = 0.15
    client.ws_mode = 5
    client.ws_loop = False
    client.ws_loop_cmd = "/new"
    client.ws_loop_cooldown = 3.0      # gap between /new rounds
    client.ws_loop_max = 0             # 0 = unlimited (safety cap)

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
        log(f"mode loaded: {mode} letters")

    def clean_word(word):
        result = ""
        for ch in word:
            normalized = unicodedata.normalize("NFKD", ch)
            for c in normalized:
                if c.isalpha(): result += c.lower()
        return result

    # =========================================
    # 🔥 PARSER 1: RICH MESSAGE (tg-button via html_text)
    # =========================================
    def parse_rich_feedback(message):
        """WordSeek sends a Rich Message whose board tiles are
        <tg-button type='callback_data' data='wh:<state>:<L>'>.
        Telethon-MCUB renders rich content into html_text."""
        try:
            html = message.html_text or ""
        except Exception:
            html = ""
        if not html:
            return None
        if client.ws_debug:
            log(f"html_text: {html[:300]!r}")
        entries = []  # (letter, state) in document order
        for m in RICH_BTN.finditer(html):
            state, letter = m.group(1).lower(), m.group(2).lower()
            entries.append((letter, state))
        if not entries:
            return None
        return build_feedback(entries)

    # =========================================
    # PARSER 2: INLINE BUTTONS (wh: data attr)
    # =========================================
    async def collect_buttons(message):
        buttons = []
        try:
            rows = await message.get_buttons()
            if rows:
                for row in rows:
                    if isinstance(row, (list, tuple)):
                        buttons.extend(row)
                    elif row is not None:
                        buttons.append(row)
        except Exception as e:
            log(f"get_buttons failed: {e}")
        return buttons

    def decode_data(data):
        if data is None:
            return ""
        if isinstance(data, bytes):
            try:
                return data.decode("utf-8", "ignore")
            except Exception:
                return ""
        try:
            return base64.b64decode(str(data)).decode("utf-8", "ignore")
        except Exception:
            return str(data)

    async def parse_button_feedback(message):
        entries = []
        for btn in await collect_buttons(message):
            text = decode_data(getattr(btn, "data", None))
            if client.ws_debug and text:
                log(f"button data: {text!r}")
            if not text.startswith("wh:"):
                continue
            parts = text.split(":")
            if len(parts) != 3:
                continue
            state, letter = parts[1].lower(), parts[2].lower()
            if state in ("correct", "present", "absent") and letter.isalpha():
                entries.append((letter, state))
        if not entries:
            return None
        return build_feedback(entries)

    def build_feedback(entries):
        """Common: entries in order, each full row = one guess."""
        n = client.ws_mode
        if len(entries) < n:
            return None
        last_row = entries[-n:]
        guess = "".join(l for l, s in last_row)
        if len(guess) != n or not guess.isalpha():
            return None
        feedback = []
        for _, state in last_row:
            if state == "correct":
                feedback.append("🟩")
            elif state == "present":
                feedback.append("🟨")
            else:
                feedback.append("⬛")
        return guess, feedback

    # =========================================
    # PARSERS 3/4: OLD-FORMAT FALLBACKS
    # =========================================
    def parse_emoji_feedback(text):
        lines = text.splitlines()
        for line in reversed(lines):
            if any(emoji in line for emoji in FEEDBACK_EMOJIS):
                parts = line.split()
                feedback = []
                guess = None
                for part in parts:
                    if part in FEEDBACK_EMOJIS:
                        feedback.append(part)
                    else:
                        cleaned = clean_word(part)
                        if cleaned: guess = cleaned
                if guess and len(feedback) == len(guess):
                    return guess, feedback
        return None

    def parse_bare_word(text):
        for line in reversed(text.splitlines()):
            stripped = line.strip()
            if re.fullmatch(rf"[A-Za-z]{{{client.ws_mode}}}", stripped):
                word = stripped.lower()
                if client.ws_last_guess and word == client.ws_last_guess:
                    return word, ["⬛"] * client.ws_mode
        return None

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
            if state in ["🟥", "⬜", "⬛", "🟪"]:
                if confirmed[char] == 0: client.ws_black.add(char)
        log(f"constraints: green={dict(client.ws_green)} yellow={ {k: sorted(v) for k, v in client.ws_yellow.items()} } black={sorted(client.ws_black)}")

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

    # =========================================
    # 🔥 SMARTER GUESS LOGIC (positional scoring + caching)
    # =========================================
    def build_positional_freq(pool_lower):
        """Per-position letter frequency across the candidate pool."""
        pos_freq = [Counter() for _ in range(client.ws_mode)]
        for w in pool_lower:
            for i, c in enumerate(w):
                pos_freq[i][c] += 1
        return pos_freq

    def score_word(word_lower, pos_freq):
        """Score = positional strength + unique-letter bonus.
        High score = maximizes info gained per guess."""
        s = sum(pos_freq[i][c] for i, c in enumerate(word_lower))
        s += len(set(word_lower)) * 2
        return s

    def get_next_guess():
        if not client.ws_used:
            return STARTERS.get(client.ws_mode, "Slate")

        v_common = [w for w in client.ws_common if valid_word(w) and w.lower() not in client.ws_used]
        v_all = [w for w in client.ws_words if valid_word(w) and w.lower() not in client.ws_used]
        pool = v_common if v_common else v_all
        if not pool:
            return None

        # ENDGAME: 1-2 candidates bache toh seedha answer maar do
        if len(pool) <= 2:
            return pool[0].capitalize()

        # Positional frequency compute (fresh each turn — pool chhota hota
        # jata hai, toh ye fast hai; warm-up pe hi heavy hota hai)
        pool_lower = [w.lower() for w in pool]
        pos_freq = build_positional_freq(pool_lower)

        # Scoring source: common pool prefer karo (answers wahan se aate hain),
        # warna all-pool se elimination word
        source = v_common if v_common else v_all
        best, best_score = None, -1
        for w in source:
            s = score_word(w.lower(), pos_freq)
            if s > best_score:
                best, best_score = w, s
        return best.capitalize()

    async def send_guess(event, guess):
        client.ws_used.add(guess.lower())
        client.ws_last_guess = guess.lower()
        log(f"sending guess: {guess}")
        # 🔥 typing action hata diya — har guess par extra RPC round-trip
        # lagta tha, wahi "time le raha" feel ka bada reason tha
        await asyncio.sleep(random.uniform(client.ws_delay_min, client.ws_delay_max))
        await client.send_message(event.chat_id, guess)

    # =========================================
    # COMMANDS (Saved Messages Control)
    # =========================================
    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws (on|off)$"))
    async def toggle_ws(event):
        client.ws_enabled = event.pattern_match.group(1).lower() == "on"
        try:
            await event.edit(f"{'✅' if client.ws_enabled else '❌'} **WordSeek Solver {'Enabled' if client.ws_enabled else 'Disabled'}**")
        except Exception:
            await client.send_message("me", f"{'✅' if client.ws_enabled else '❌'} **WordSeek Solver {'Enabled' if client.ws_enabled else 'Disabled'}**")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws loop (on|off)$"))
    async def toggle_loop(event):
        client.ws_loop = event.pattern_match.group(1).lower() == "on"
        try:
            await event.edit(f"{'♻️' if client.ws_loop else '❌'} **Auto Loop {'Enabled' if client.ws_loop else 'Disabled'}**")
        except Exception:
            await client.send_message("me", f"{'♻️' if client.ws_loop else '❌'} **Auto Loop {'Enabled' if client.ws_loop else 'Disabled'}**")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws delay (\d+\.?\d*) (\d+\.?\d*)$"))
    async def set_delay(event):
        client.ws_delay_min = float(event.pattern_match.group(1))
        client.ws_delay_max = float(event.pattern_match.group(2))
        try:
            await event.edit(f"⚡ **WordSeek Delay Set:** {client.ws_delay_min}s - {client.ws_delay_max}s")
        except Exception:
            await client.send_message("me", f"⚡ **WordSeek Delay Set:** {client.ws_delay_min}s - {client.ws_delay_max}s")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.ws debug (on|off)$"))
    async def toggle_debug(event):
        client.ws_debug = event.pattern_match.group(1).lower() == "on"
        try:
            await event.edit(f"🐞 **WordSeek Debug {'Enabled' if client.ws_debug else 'Disabled'}**")
        except Exception:
            await client.send_message("me", f"🐞 **WordSeek Debug {'Enabled' if client.ws_debug else 'Disabled'}**")

    # =========================================
    # MAIN ENGINE
    # =========================================
    @client.on(events.NewMessage(outgoing=True))
    async def detect_new_game(event):
        if not client.ws_enabled: return
        text = event.raw_text.lower().strip()

        # Only lock on WordSeekBot commands: /new, /new4, /new6
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
                log(f"locked on chat {event.chat_id} via {text}")
                try: await client.send_message("me", f"🎯 **WordSeek Locked!**\nChat: `{event.chat_id}`")
                except: pass

    @client.on(events.NewMessage)
    async def solver(event):
        if not client.ws_enabled or event.chat_id != client.ws_chat: return
        sender = await event.get_sender()
        if not sender: return
        sender_username = (getattr(sender, "username", "") or "").lower()
        if sender_username != "wordseekbot": return

        message = event.message
        text = clean_text(event.raw_text or "")
        low = text.lower()
        log(f"bot message received: {text[:80]!r}")

        # --- GAME END DETECTION (broad — loop pakka chalega) ---
        if any(x in low for x in [
            "congrats", "guessed it correctly", "game over",
            "the word was", "better luck", "you lost", "out of guesses"
        ]):
            log("game ended — resetting")
            reset_state()
            if client.ws_loop and client.ws_loop_cmd:
                log(f"loop: restarting with {client.ws_loop_cmd}")
                await asyncio.sleep(random.uniform(client.ws_loop_cooldown, client.ws_loop_cooldown + 1.5))
                await client.send_message(client.ws_chat, client.ws_loop_cmd)
            return

        # --- GAME START ---
        if "game started" in low:
            guess = get_next_guess()
            log("game start detected")
            if guess:
                await send_guess(event, guess)
            return

        # --- INVALID WORD / ALREADY GUESSED ---
        if "is not a valid" in low or "already guessed your word" in low or "not in the word list" in low:
            log("invalid/dupe word — advancing")
            if client.ws_last_guess:
                client.ws_used.add(client.ws_last_guess)
            client.ws_last_guess = None
            guess = get_next_guess()
            if guess:
                await send_guess(event, guess)
            return

        # --- FEEDBACK PARSING (rich first, then fallbacks) ---
        res = parse_rich_feedback(message)
        if not res:
            res = await parse_button_feedback(message)
        if not res:
            res = parse_emoji_feedback(text)
        if not res:
            res = parse_bare_word(text)
        if not res:
            if client.ws_debug:
                log(f"could not parse feedback. raw={event.raw_text!r}")
            return

        guess, feedback = res
        log(f"feedback parsed: guess={guess} feedback={''.join(feedback)}")
        client.ws_last_guess = guess

        # Agar feedback aisi word ki hai jo humne bheji thi hi nahi
        # (kisi aur ne guess kiya), toh constraints apply karne mein
        # koi harm nahi — board sab ki guesses dikhaata hai aur
        # constraints globally valid hote hain.
        apply_constraints(guess, feedback)
        next_guess = get_next_guess()
        if next_guess:
            await send_guess(event, next_guess)
        else:
            fallback = [w for w in client.ws_words if w.lower() not in client.ws_used]
            log(f"pool empty — fallback: {len(fallback)} words left")
            if fallback:
                await send_guess(event, fallback[0].capitalize())
