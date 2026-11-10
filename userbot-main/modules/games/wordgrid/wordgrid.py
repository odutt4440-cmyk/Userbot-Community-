import re, asyncio, gc, os, requests
from telethon import events
from .ocr_engine import extract_grid
from .solver import GridSolver

DICT_FILE = os.path.join(os.path.dirname(__file__), "wordgrid_dict.txt")
state = {"enabled": False, "target": None, "delay": 0.5}

def load_dict():
    if not os.path.exists(DICT_FILE):
        try:
            url = "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt"
            data = requests.get(url, timeout=10).text.splitlines()
            with open(DICT_FILE, "w") as f: f.write("\n".join(data))
        except: return {}
    words = {}
    with open(DICT_FILE, "r") as f:
        for line in f:
            w = line.strip().upper()
            l = len(w)
            if l not in words: words[l] = []
            words[l].append(w)
    return words

WORDS_BY_LEN = load_dict()

def register(client):
    # 1. Admin Commands
    @client.on(events.NewMessage(chats='me', pattern=r'\.(wgon|wgoff|wgdelay)'))
    async def admin_cmds(event):
        cmd = event.pattern_match.group(1)
        if cmd == "wgon": 
            state["enabled"] = True
            await event.reply("✅ **WordGrid: ON**")
        elif cmd == "wgoff": 
            state["enabled"] = False
            await event.reply("❌ **WordGrid: OFF**")
        elif cmd == "wgdelay": 
            state["delay"] = float(event.raw_text.split()[1])
            await event.reply(f"⚡ **Delay:** `{state['delay']}s`")

    # 2. Separate Locker Logic (Only reacts to YOUR /new)
    @client.on(events.NewMessage)
    async def locker(event):
        # Check if it's YOUR message and matches command
        if state["enabled"] and event.out and "/new" in event.raw_text:
            state["target"] = event.chat_id
            await client.send_message('me', f"🎯 **WordGrid Locked to Chat:** `{event.chat_id}`")

    # 3. Game Handler
    @client.on(events.NewMessage)
    async def game_handler(event):
        if not state["enabled"] or event.chat_id != state["target"] or not event.media: 
            return
        
        # Grid Capturing Message
        await client.send_message('me', "📸 **Grid Captured!** Processing...")
        
        path = await event.download_media()
        await asyncio.sleep(1.5)
        grid = extract_grid(path)
        
        if not grid:
            await client.send_message('me', "⚠️ **OCR Failed.**")
            return
            
        # Grid Visualization in Saved Messages
        grid_str = "\n".join([" ".join(row) for row in grid])
        await client.send_message('me', f"🧩 **Detected Grid:**\n`{grid_str}`")
        
        solver = GridSolver(grid)
        clues = re.findall(r'([A-Z-]{3,})', event.raw_text.upper())
        lens = re.findall(r'\((\d+)\)', event.raw_text)
        
        for i, clue in enumerate(clues):
            target_len = int(lens[i]) if i < len(lens) else len(clue.replace('-', ''))
            pattern = f"^{clue.replace('-', '.')}$"
            
            candidates = WORDS_BY_LEN.get(target_len, [])
            for word in candidates:
                if re.match(pattern, word) and solver.solve(word):
                    await client.send_message('me', f"✅ **Found:** `{word}`")
                    async with event.client.action(event.chat_id, 'typing'):
                        await asyncio.sleep(state["delay"])
                        await event.client.send_message(event.chat_id, word)
                    break
