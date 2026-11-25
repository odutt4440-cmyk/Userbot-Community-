import json
import random
import asyncio
import unicodedata
import os
import re
from collections import Counter
from telethon import events, functions, types, errors

# =========================================
# LOAD WORDLISTS
# =========================================
FOLDER = os.path.dirname(__file__)
WORDS_DIR = os.path.join(FOLDER, "words")

def load_json(filename):
    path = os.path.join(WORDS_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data["words"] if isinstance(data, dict) else data
    return []

STARTERS = {
    3: "Ten", 4: "Care", 5: "Slate", 6: "Retain", 7: "Staring"
}

FILE_MAP = {
    3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"
}

def register(client):
    # 🔥 PERMANENTLY DISABLED: The Wordle Pro bot (@wordlegameprobot)
    # has been deleted. This module has no bot to play with, and its old
    # loose /new detection was hijacking other bots' commands
    # (e.g. /new@WordSeekBot). It must stay fully off to avoid clashes.

    client.wd_enabled = False
    client.wd_chat = None
    client.wd_delay_min = 1.0
    client.wd_delay_max = 2.0
    client.wd_mode = 5
    client.wd_loop = False
    client.wd_loop_cmd = "/new"

    client.wd_used = set()
    client.wd_green = {}
    client.wd_yellow = {}
    client.wd_black = set()
    client.wd_last_guess = None

    async def safe_edit(event, text):
        try: await event.edit(text)
        except: pass

    def reset_state():
        client.wd_green = {}
        client.wd_yellow = {}
        client.wd_black = set()
        client.wd_used = set()
        client.wd_last_guess = None

    def parse_full_board(text):
        lines = text.splitlines()
        found_clues = []
        for line in lines:
            match = re.search(r"([🟩🟨🟥⬜⬛\s]{3,})\s+([A-Z]{3,7})", line.upper())
            if match:
                raw_emojis = match.group(1).replace(" ", "")
                emojis = list(raw_emojis)
                word = match.group(2).lower()
                if len(emojis) == len(word):
                    found_clues.append((word, emojis))
        return found_clues

    def apply_constraints_from_history(clues):
        client.wd_green = {}
        client.wd_yellow = {}
        client.wd_black = set()
        all_present_chars = set()

        for word, emojis in clues:
            for i, emoji in enumerate(emojis):
                if emoji == "🟩" or emoji == "🟨":
                    all_present_chars.add(word[i])

        for word, emojis in clues:
            client.wd_used.add(word)
            for i, emoji in enumerate(emojis):
                char = word[i]
                if emoji == "🟩":
                    client.wd_green[i] = char
                elif emoji == "🟨":
                    if char not in client.wd_yellow: client.wd_yellow[char] = set()
                    client.wd_yellow[char].add(i)
                elif emoji in ["🟥", "⬜", "⬛"]:
                    if char not in all_present_chars:
                        client.wd_black.add(char)

    def is_valid(word):
        word = word.lower()
        if len(word) != client.wd_mode: return False
        for pos, char in client.wd_green.items():
            if word[pos] != char: return False
        for char in client.wd_black:
            if char in word: return False
        for char, bad_positions in client.wd_yellow.items():
            if char not in word: return False
            for pos in bad_positions:
                if word[pos] == char: return False
        return True

    def get_next_guess():
        suffix = FILE_MAP.get(client.wd_mode, "five")
        common = load_json(f"common-{suffix}.json")
        all_words = load_json(f"all-{suffix}.json")
        pool = list(set(common + all_words))
        candidates = [w for w in pool if is_valid(w) and w.lower() not in client.wd_used]
        if not candidates: return None
        freq = Counter("".join(candidates))
        candidates.sort(key=lambda w: sum(freq[c] for c in set(w.lower())), reverse=True)
        return candidates[0].capitalize()

    # --- COMMANDS (kept for manual control, but locked OFF) ---
    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.wd (on|off)$"))
    async def toggle_wd(event):
        if event.pattern_match.group(1).lower() == "on":
            await safe_edit(event, "🧩 **Wordle Pro: DISABLED**\nBot was deleted. Use WordSeek / Wordly / Word Ladder instead.")
        else:
            client.wd_enabled = False
            client.wd_chat = None
            await safe_edit(event, "🧩 **Wordle Pro: OFF**")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.wd loop (on|off)$"))
    async def toggle_loop(event):
        client.wd_loop = event.pattern_match.group(1).lower() == "on"
        await safe_edit(event, f"♻️ **Loop Mode: {'ON' if client.wd_loop else 'OFF'}**")

    @client.on(events.NewMessage(chats='me', pattern=r"(?i)^\.wd delay (\d+\.?\d*) (\d+\.?\d*)$"))
    async def set_delay(event):
        try:
            client.wd_delay_min = float(event.pattern_match.group(1))
            client.wd_delay_max = float(event.pattern_match.group(2))
            await safe_edit(event, f"⚡ **Flash Speed Set:** {client.wd_delay_min}s - {client.wd_delay_max}s")
        except:
            await safe_edit(event, "❌ **Usage:** `.wd delay 0.1 0.5` (Min Max)")

    # --- AUTO LOCK: PERMANENTLY DEAD ---
    @client.on(events.NewMessage(outgoing=True))
    async def detect_new(event):
        # 🔥 Never locks anything. Bot deleted — this module is retired.
        return

    # --- GAME HANDLER: PERMANENTLY DEAD ---
    @client.on(events.NewMessage)
    async def game_handler(event):
        # 🔥 Never reacts. Bot deleted — this module is retired.
        return
