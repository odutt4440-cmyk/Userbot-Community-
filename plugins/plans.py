from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from bot_instance import bot
from database import (
    global_security_check, 
    is_plan_available,
    get_all_active_plans,
    get_plan
)

# --- UNIVERSAL PLAN MENU LOGIC (Dynamic from DB) ---
async def send_plans_menu(message, edit=False):
    # DB se saare active plans fetch karo
    plans = await get_all_active_plans()
    
    if not plans:
        text = "⚠️ **No plans available right now.**\nPlease check back later."
        if edit:
            await message.edit_text(text)
        else:
            await message.reply(text)
        return
    
    # Tier ke hisaab se group karo
    tiers = {
        "standard": {"title": "✨ **Standard Tiers** (Self Session | 1 Module)", "items": []},
        "empire": {"title": "🚀 **Empire Tiers** (Self Session | Multi Module)", "items": []},
        "ultra_standard": {"title": "🥇 **Ultra Premium** (We Provide Account ID)", "items": []},
        "ultra_empire": {"title": "👑 **Ultra Empire** (We Provide Account ID)", "items": []},
    }
    
    for p in plans:
        tier = p.get("tier", "standard")
        if tier in tiers:
            tiers[tier]["items"].append(p)
    
    # Dynamic text generate
    plan_text = "💎 **Empire Userbot Premium Plans**\n" + "━" * 20 + "\n\n"
    
    for tier_key, tier_data in tiers.items():
        if not tier_data["items"]:
            continue
        plan_text += f"{tier_data['title']}\n"
        for p in tier_data["items"]:
            plan_text += f"• {p['days']} Days ➔ **₹{p['price']}**\n"
        plan_text += "\n"
    
    plan_text += "━" * 20 + "\n"
    plan_text += "🎁 **New User?** Claim your 24h Free Trial!\n"
    plan_text += "👇 Select a plan to get payment details:"
    
    # Buttons dynamically generate
    buttons = []
    row = []
    for p in plans:
        # Style: standard = PRIMARY, empire = SUCCESS, ultra = DANGER (premium)
        tier = p.get("tier", "standard")
        if tier == "standard":
            style = ButtonStyle.PRIMARY
        elif tier == "empire":
            style = ButtonStyle.SUCCESS
        else:
            style = ButtonStyle.DANGER
        
        label = f"{p['name'][:8]} ({p['days']}d) - ₹{p['price']}"
        row.append(InlineKeyboardButton(
            label,
            callback_data=f"buy_{p['plan_key']}",
            style=style
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    # Back button
    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="start_back", style=ButtonStyle.PRIMARY)])
    
    markup = InlineKeyboardMarkup(buttons)
    
    if edit:
        await message.edit_text(plan_text, reply_markup=markup)
    else:
        await message.reply(plan_text, reply_markup=markup)

# --- COMMAND HANDLER: /plan ---
@bot.on_message(filters.command("plan") & filters.private)
async def plans_cmd(client, message):
    # Use the Kurigram-specific security check from start.py
    from plugins.start import global_security_check as start_security_check
    if not await start_security_check(message): return
    await send_plans_menu(message, edit=False)

# --- BUTTON HANDLER: pay_now ---
@bot.on_callback_query(filters.regex("^pay_now$"))
async def pay_callback(client, query):
    await send_plans_menu(query.message, edit=True)
    await query.answer()

# --- PLAN AVAILABILITY CHECKER ---
@bot.on_callback_query(filters.regex(r"^buy_(\w+)$"))
async def check_and_pay(client, query):
    plan_key = query.matches[0].group(1)
    
    # Check 1: Setting-based toggle (existing)
    if not await is_plan_available(plan_key):
        await query.message.edit_text(
            "⚠️ **Notice:** This plan is currently unavailable.\n\n"
            "Please contact us via **Support** for manual requests.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Support", callback_data="support_main", style=ButtonStyle.PRIMARY)],
                [InlineKeyboardButton("🔙 View Other Plans", callback_data="pay_now", style=ButtonStyle.PRIMARY)]
            ])
        )
        return await query.answer()
    
    # Check 2: DB active field
    plan = await get_plan(plan_key)
    if not plan or not plan.get("active", True):
        await query.answer("This plan is no longer available.", show_alert=True)
        return
    
    # 🔥 FIX: Trigger payment flow with user ID
    from plugins.payment import show_payment_info
    await show_payment_info(query.message, plan_key, query.from_user.id)
    await query.answer()
