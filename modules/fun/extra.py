import asyncio
from telethon import events

# --- 🎨 ASCII ARTS DICTIONARY (Clean Look) ---
ARTS = {
    "hi": """
⠀⠀⠀⠀⠀⢀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⢰⣿⡿⠗⠀⠠⠄⡀⠀⠀⠀⠀
⠀⠀⠀⠀⡜⠁⠀⠀⠀⠀⠀⠈⠑⢶⣶⡄
⢀⣶⣦⣸⠀⢼⣟⡇⠀⠀⢀⣀⠀⠘⡿⠃
⠀⢿⣿⣿⣄⠒⠀⠠⢶⡂⢫⣿⢇⢀⠃⠀
⠀⠈⠻⣿⣿⣿⣶⣤⣀⣀⣀⣂⡠⠊⠀⠀
⠀⠀⠀⠃⠀⠀⠉⠙⠛⠿⣿⣿⣧⠀⠀⠀
⠀⠀⠘⡀⠀⠀⠀⠀⠀⠀⠘⣿⣿⡇⠀⠀
⠀⠀⠀⣷⣄⡀⠀⠀⠀⢀⣴⡟⠿⠃⠀⠀
⠀⠀⠀⢻⣿⣿⠉⠉⢹⣿⣿⠁⠀⠀⠀⠀ HELLO GUYSIS
⠀⠀⠀⠀⠉⠁⠀⠀⠀⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀
""",

    "hello": """
╔┓┏╦━━╦┓╔┓╔━━╗
║┗┛║┗━╣┃║┃║╯╰║     
║┏┓║┏━╣┗╣┗╣╰╯║      
╚┛┗╩━━╩━╩━╩━━╝
""",

    "gn": """
∩――――∩     ˗ˏˋ ★ ˎˊ˗
|    ∧  ﾍ        |
|    (* ´ ▽`)     |  < ᴳᵒᵒᵈᴺⁱᵍʜᴛ   ♡
|ﾉ^⌒⌒づ￣  ＼
(　ノ　　⌒ ヽ ＼
＼　　|￣￣￣￣￣|
　 ＼,ﾉ|
""",

    "gm": """
Good morning!
     へ   +        —̳͟͞͞💗
૮  -   ̫ ՛ )つ  —̳͟͞͞ 💗         —̳͟͞͞💗 +
(つ    <                —̳͟͞͞💗
｜  _   つ      +  —̳͟͞͞💗         —̳͟͞͞💗 ˚
`し´
""",

    "bear": """
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣰⣿⣿⣿⣿⣦⣀⣀⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⢿⣿⠟⠋⠉⠀⠀⠀⠀⠉⠑⠢⣄⡀⠀⠀⠀⠀⠀                
⠀⠀⠀⠀⠀⢠⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣿⣿⣦⡀                
⠀⣀⠀⠀⢀⡏⠀⢀⣴⣶⣶⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⠇
⣾⣿⣿⣦⣼⡀⠀⢺⣿⣿⡿⠃⠀⠀⠀⠀⣠⣤⣄⠀⠀⠈⡿⠋⠀
⢿⣿⣿⣿⣿⣇⠀⠤⠌⠁⠀⡀⢲⡶⠄⢸⣏⣿⣿⠀⠀⠀⡇⠀⠀
⠈⢿⣿⣿⣿⣿⣷⣄⡀⠀⠀⠈⠉⠓⠂⠀⠙⠛⠛⠠⠀⡸⠁⠀⠀
⠀⠀⠻⣿⣿⣿⣿⣿⣿⣷⣦⣄⣀⠀⠀⠀⠀⠑⠀⣠⠞⠁⠀⠀⠀
⠀⠀⠀⢸⡏⠉⠛⠛⠛⠿⠿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⠀⠀
⠀⠀⠀⠸⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠛⢿⣿⣿⣿⣿⡄⠀⠀⠀⠀
⠀⠀⠀⢷      𝐈𝐂𝐄 𝐁𝐄𝐀𝐑 🐻‍❄️      ⠈⢻⣿⣿⣿⣿⡀⠀⠀⠀
⠀⠀⠀⢸⣆⠀⠀⠀⠀⠀      ⠀⠀⣿⣿⣿⣿⡇⠀⠀⠀
⠀⠀⠀⢸⣿⣦⣀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⡟⠻⠿⠟⡀⠀⠀⠀
⠀⠀ ⠀⣿⣿⣿⣿⣶⠶⠤⠤⢤⣶⣾⣿⣿⡇⠀
⠀⠀⠀⠀⠹⣿⣿⣿⠏⠀⠀⠀⠈⢿⣿⣿⡿⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠈⠉⠉⠀⠀⠀⠀⠀⠀⠉⠉⠀
""",

    "fuck": """
 ⢀⣴⡿⠿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⢸⡿⣀⠠⠇⢧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⢷⠀⢀⣀⠘⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠈⣇⠉⠀⠀⠹⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⢠⢾⡄⠀⠀⠀⢻⠞⠓⢺⠉⠓⣦⡀⠀⠀⠀
⠀⣠⡾⢂⣱⠐⠛⠭⠀⢃⠀⠀⠡⡀⠈⠳⣄⠀⠀
⣴⠫⠛⠀⠈⢇⠀⠀⠀⠀⠆⠀⠀⢡⠀⠀⠘⣆⠀
⣇⢇⠀⠀⠀⠀⢆⠀⠀⠀⠈⡄⠀⠀⢧⠀⠀⢸⡆
⢻⠸⡀⠀⠀⠀⢸⡆⠀⠀⠀⠐⠀⠀⠀⠀⢀⡞⠀
⢸⠀⢳⠀⠀⠀⠀⠋⠀⠀⠀⠀⠀⠀⠀⣣⠾⠀⠀
⠈⠳⣄⢆⠀⠀⠀⠀⠆⠀⠀⠀⣠⡦⠞⠃⠀F*CK YOU
⠀⠀⠈⠛⠷⠤⠤⠖⠚⠒⠒⠚⠁⠀⠀⠀⠀⠀⠀⠀
"""
}
# --- 🛠️ SAFE EDIT HELPER ---
async def safe_edit(event, text, **kwargs):
    try:
        return await event.edit(text, **kwargs)
    except Exception:
        return None # Agar edit fail ho toh chup-chap nikal jao
        
def register(client):

    # --- 1. ASCII ARTS ---
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.(hi|hello|gn|gm|bear|fuck)"))
    async def ascii_handler(event):
        cmd = event.pattern_match.group(1).lower()
        if cmd == "fuck":
            await safe_edit(event, "F*ck You Baby 🖕")
            await asyncio.sleep(1.5)
            await safe_edit(event, "Baby, Ohh.. Yes 👅")
            await asyncio.sleep(1.5)
            
        await safe_edit(event, f"<code>{ARTS[cmd]}</code>", parse_mode='html')

    # --- 2. EMOJI LOOPS ---
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.(hehe|sad|heart|sleep)"))
    async def emoji_handler(event):
        cmd = event.pattern_match.group(1).lower()
        lists = {
            "hehe": ["😀", "😃", "😄", "😁", "😎", "😅", "🤣", "😂", "😛", "😜", "🤪", "😝", "🤫", "🫡", "😶", "😆"],
            "sad": ["🙂", "🙃", "🥲", "😐", "😕", "🙁", "☹️", "😰", "😥", "😢", "😭", "😣", "😞", "😩"],
            "heart": ["💌", "💘", "💝", "💖", "💗", "💓", "💞", "💕", "💟", "❣️", "❤️‍🔥", "❤️‍🩹", "❤️", "🩷", "🧡", "💛", "💚", "💙", "🩵", "💜", "🤎", "🖤", "🩶", "🤍"],
            "sleep": ["😴🥱😴🥱", "🥱😴🥱😴", "😴🥱😴🥱", "🥱😴😴🥱"]
        }
        for emoji in lists[cmd]:
            # Agar safe_edit fail hota hai (msg deleted), toh loop tod do
            if not await safe_edit(event, emoji): break
            await asyncio.sleep(0.8)
        
        if cmd == "heart": await safe_edit(event, "You Are So Cute 🙈")

    # --- 3. GREET COMMAND ---
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.greet"))
    async def greet_handler(event):
        wishes = ["Aaj ka din badhiya ho! 💪", "Let's make today awesome! 🌟", "Keep good vibes! 🌸", "Aaj kuch zabardast karte hain! 🎉"]
        await safe_edit(event, random.choice(wishes))

    # --- 4. ALIVE COMMAND ---
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.alive"))
    async def alive_handler(event):
        me = await client.get_me()
        try:
            await event.delete()
            await client.send_message(event.chat_id, f"<b>EMPIRE IS ALIVE 👑</b>\n\n👤 <b>Owner:</b> {me.first_name}\n⚙️ <b>Status:</b> Online", parse_mode='html')
        except: pass

    # --- 5. HACKING ANIMATION ---
    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.hack"))
    async def hack_handler(event):
        await safe_edit(event, "`Trying to get the weakness...` ")
        await asyncio.sleep(1.5)
        await safe_edit(event, "`Found Some INFORMATION...` ")
        await asyncio.sleep(1)
        for i in range(0, 101, 10):
            status = f"<code>[Processing... {'#'*(i//10)}{' '*(10-i//10)}] {i}%</code>"
            if not await safe_edit(event, status, parse_mode='html'): break
            await asyncio.sleep(0.4)
        await safe_edit(event, "`Gained Access... You are Hacked Buddy!` 😈")
