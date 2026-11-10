from bot_instance import bot
from telethon import events, Button
from database import global_security_check, is_plan_available

# --- UNIVERSAL PLAN MENU LOGIC ---
async def send_plans_menu(event, edit=False):
    plan_text = (
        "💎 **Empire Userbot Premium Plans**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ **Standard Tiers** (Self Session | 1 Module)\n"
        "• 15 Days ➔ **₹10** | 30 Days ➔ **₹30**\n\n"
        "🚀 **Empire Tiers** (Self Session | Multi Module)\n"
        "• 15 Days ➔ **₹15** | 30 Days ➔ **₹35**\n\n"
        "🥇 **Ultra Premium** (We Provide Account ID)\n"
        "• Standard (15d) ➔ **₹50** | (30d) ➔ **₹95**\n"
        "• Empire (15d) ➔ **₹55** | (30d) ➔ **₹100**\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎁 **New User?** Claim your 24h Free Trial!\n"
        "👇 Select a plan to get payment details:"
    )

    buttons = [
        [Button.inline("💳 Standard (15d)", data="buy_std_15"), Button.inline("💳 Standard (30d)", data="buy_std_30")],
        [Button.inline("🚀 Empire (15d)", data="buy_emp_15"), Button.inline("🚀 Empire (30d)", data="buy_emp_30")],
        [Button.inline("🥇 Ultra Std (15d)", data="buy_u_std_15"), Button.inline("🥇 Ultra Std (30d)", data="buy_u_std_30")],
        [Button.inline("👑 Ultra Emp (15d)", data="buy_u_emp_15"), Button.inline("👑 Ultra Emp (30d)", data="buy_u_emp_30")],
        [Button.inline("🔙 Back to Menu", data="start_back")]
    ]

    if edit:
        await event.edit(plan_text, buttons=buttons)
    else:
        await event.reply(plan_text, buttons=buttons)

# --- COMMAND HANDLER: /plan ---
@bot.on(events.NewMessage(pattern=r'(?i)^/plan'))
async def plans_cmd(event):
    if not event.is_private: return
    if not await global_security_check(event): return
    await send_plans_menu(event, edit=False)

# --- BUTTON HANDLER: pay_now ---
@bot.on(events.CallbackQuery(data="pay_now"))
async def pay_callback(event):
    if not await global_security_check(event): return
    await send_plans_menu(event, edit=True)

# --- PLAN AVAILABILITY CHECKER ---
@bot.on(events.CallbackQuery(pattern=r"buy_(\w+)"))
async def check_and_pay(event):
    if not await global_security_check(event): return
    
    plan_key = event.data.decode("utf-8").replace("buy_", "")
    
    # 🔥 THE DISABLE LOGIC: Check if admin turned this off
    if not await is_plan_available(plan_key):
        return await event.edit(
            "⚠️ **Notice:** This specific plan is currently not available due to high demand.\n\n"
            "Kindly connect with us through the **Support & Feedback** menu for manual requests.",
            buttons=[[Button.inline("📢 Support & Feedback", data="support_main")], [Button.inline("🔙 View Other Plans", data="pay_now")]]
        )

    # Agar plan available hai, toh payment.py ke handler ko trigger karega
    # (Humein payment.py me button pattern match update karna hoga)
    from plugins.payment import show_payment_info
    await show_payment_info(event, plan_key)
