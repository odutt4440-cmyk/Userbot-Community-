import asyncio
import os
import re
import json
from telethon import events
from collections import deque

# 🔥 Load Dictionary from wordle_pro/words JSON files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Path check: wordladder folder se bahar nikal kar wordle_pro/words mein jana
DICT_DIR = os.path.join(BASE_DIR, "..", "wordle_pro", "words")

WORDS_BY_LEN = {i: set() for i in range(3, 8)}

def load_local_dict(length, filename):
    filepath = os.path.join(DICT_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                words = json.load(f)
                WORDS_BY_LEN[length] = set(w.lower() for w in words)
                print(f"[LADDER] ✅ Loaded {len(words)} words of length {length}")
        except Exception as e:
            print(f"[LADDER] ❌ Error loading {filename}: {e}")
    else:
        print(f"[LADDER] ❌ File not found: {filepath}")

# Load all sizes (3 to 7)
load_local_dict(3, "all-three.json")
load_local_dict(4, "all-four.json")
load_local_dict(5, "all-five.json")
load_local_dict(6, "all-six.json")
load_local_dict(7, "all-seven.json")


def register(client):
    # State variables
    client.wl_enabled = True
    client.wl_target_chat = None
    client.wl_loop = False
    client.wl_delay = 1.5 
    client.wl_last_cmd = "/new"

    client.wl_game = {
        "start": "",
        "target": "",
        "current": "",
        "banned": set(), 
        "path": []
    }

    def get_neighbors(word, word_set, banned):
        """Finds valid words by changing strictly 1 letter"""
        neighbors = []
        for i in range(len(word)):
            for c in 'abcdefghijklmnopqrstuvwxyz':
                if c != word[i]:
                    new_word = word[:i] + c + word[i+1:]
                    if new_word in word_set and new_word not in banned:
                        neighbors.append(new_word)
        return neighbors

    def find_chain(start, target, banned):
        """Uses BFS to find the shortest path (avoiding banned words)"""
        length = len(start)
        if length not in WORDS_BY_LEN or not WORDS_BY_LEN[length]: 
            return []
        
        word_set = WORDS_BY_LEN[length]
        # Add start and target to set just in case they are missing
        word_set.add(start)
        word_set.add(target)
        
        queue = deque([[start]])
        visited = set([start])
        
        while queue:
            path = queue.popleft()
            current_word = path[-1]
            
            if current_word == target:
                return path
            
            for neighbor in get_neighbors(current_word, word_set, banned):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return []

    # =========================================
    # CONTROL PANEL (.wlon, .wloff, .wlloop, .wldelay)
    # =========================================
    @client.on(events.NewMessage(chats='me'))
    async def control_panel_ladder(event):
        text = event.raw_text.lower().strip()
        if text == ".wlon":
            client.wl_enabled = True
            await event.edit("✅ **Word Ladder: ONLINE**")
        elif text == ".wloff":
            client.wl_enabled = False
            client.wl_target_chat = None
            await event.edit("❌ **Word Ladder: OFFLINE**")
        elif text.startswith(".wlloop"):
            client.wl_loop = "on" in text
            await event.edit(f"{'🔄' if client.wl_loop else '❌'} **Ladder Auto-Loop:** {'ON' if client.wl_loop else 'OFF'}")
        elif text.startswith(".wldelay"):
            try:
                client.wl_delay = float(text.split()[1])
                await event.edit(f"⚡ **Ladder Delay:** {client.wl_delay}s")
            except: pass

    @client.on(events.NewMessage(outgoing=True))
    async def detect_game(event):
        if not client.wl_enabled: return
        text = event.raw_text.lower().strip()
        
        # Target Chat Lock
        if text.startswith("/new") or text.startswith("/play") or text.startswith("/start"):
            client.wl_target_chat = event.chat_id
            client.wl_last_cmd = event.raw_text
            client.wl_game = {"start": "", "target": "", "current": "", "banned": set(), "path": []}
            try: await client.send_message("me", f"🎯 **Word Ladder Locked!**\nChat: `{event.chat_id}`")
            except: pass

    @client.on(events.NewMessage)
    async def game_handler(event):
        if not client.wl_enabled or client.wl_target_chat is None: return
        if event.chat_id != client.wl_target_chat: return
        
        msg = event.raw_text
        msg_up = msg.upper()
        
        # 🔥 1. GAME START DETECT
        if "WORD LADDER RACE" in msg_up or "send your chain" in msg.lower():
            match = re.search(r"([A-Z]{3,7})\s*\n.*?target.*?\n\s*([A-Z]{3,7})", msg, re.IGNORECASE | re.DOTALL)
            if match:
                start = match.group(1).lower()
                target = match.group(2).lower()
                
                client.wl_game["start"] = start
                client.wl_game["target"] = target
                client.wl_game["current"] = start
                client.wl_game["banned"] = set()
                
                chain = find_chain(start, target, client.wl_game["banned"])
                
                if chain and len(chain) > 1:
                    client.wl_game["path"] = chain
                    next_word = chain[1]
                    await asyncio.sleep(1)
                    await client.send_message(event.chat_id, next_word.upper())
                else:
                    try: await client.send_message("me", f"❌ No valid chain found from `{start.upper()}` to `{target.upper()}`.")
                    except: pass
            return

        # 🔥 2. SUCCESS DETECT (e.g. ✅ LAST -> LOSE)
        if "✅" in msg and "->" in msg:
            parts = msg.split("->")
            if len(parts) == 2:
                accepted_word = parts[1].strip().lower()
                accepted_word = re.sub(r'[^a-z]', '', accepted_word) # Remove emojis/spaces
                
                if accepted_word:
                    client.wl_game["current"] = accepted_word
                    
                    # Remove the accepted word from the old path
                    if accepted_word in client.wl_game["path"]:
                        idx = client.wl_game["path"].index(accepted_word)
                        client.wl_game["path"] = client.wl_game["path"][idx:]
                    
                    # Send the next word
                    if len(client.wl_game["path"]) > 1:
                        next_word = client.wl_game["path"][1]
                        await asyncio.sleep(client.wl_delay)
                        await client.send_message(event.chat_id, next_word.upper())
            return

        # 🔥 3. FAIL DETECT (not in my dictionary)
        if "not in my dictionary" in msg.lower() or "❌" in msg:
            current_valid = client.wl_game["current"]
            
            # Add failed word to the banned list
            if event.reply_to_msg_id:
                try:
                    replied_msg = await event.get_reply_message()
                    if replied_msg and replied_msg.text:
                        failed_word = replied_msg.text.strip().lower()
                        client.wl_game["banned"].add(failed_word)
                except: pass
            
            # Find a new path from the last valid word
            new_chain = find_chain(current_valid, client.wl_game["target"], client.wl_game["banned"])
            
            if new_chain and len(new_chain) > 1:
                client.wl_game["path"] = new_chain
                next_word = new_chain[1]
                await asyncio.sleep(1)
                await client.send_message(event.chat_id, next_word.upper())
            else:
                try: await client.send_message("me", "❌ No alternative path found in local dictionary.")
                except: pass
            return

        # 🔥 4. GAME OVER LOOP
        if "TIMES UP" in msg_up or "GAME OVER" in msg_up:
            if client.wl_loop:
                await asyncio.sleep(8)
                try: await client.send_message(event.chat_id, client.wl_last_cmd)
                except: pass
