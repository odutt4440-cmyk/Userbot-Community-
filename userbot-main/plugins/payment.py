import asyncio
import re
import os
from bot_instance import bot 
from telethon import events, Button
from core.session_manager import SessionManager
from config import ADMIN_ID, LOG_GROUP, SUDO_USERS
# UPI_ID aur PAY_QR config.py se uthayenge
try:
    from config import UPI_ID, PAY_QR
except ImportError:
    UPI_ID = "sparshbaniya@fam" # Fallback agar config me na ho
    PAY_QR = "assets/qr.jpg" # Local path

from database import add_subscription, get_sudo_info, global_security_check

# Mapping for all 8 plans: Price, Full Name, and Days
PLAN_MAP = {
    "std_15": {"name": "Standard", "price": 10, "days": 15},
    "std_30": {"name": "Standard", "price": 30, "days": 30},
    "emp_15": {"name": "Empire", "price": 15, "days": 15},
    "emp_30": {"name": "Empire", "price": 35, "days": 30},
    "u_std_15": {"name": "Ultra Standard", "price": 50, "days": 15},
    "u_std_30": {"name": "Ultra Standard", "price": 95, "days": 30},
    "u_emp_15": {"name": "Ultra Empire", "price": 55, "days": 15},
    "u_emp_30": {"name": "Ultra Empire", "price": 100, "days": 30},
}

# Tracking users: {user_id: plan_key}
WAITING_FOR_PAYMENT = {}

# --- HELPER: CHECK PAYMENT POWER ---
async def can_user_approve(user_id):
    if user_id == ADMIN_ID: return True
    info = await get_sudo_info(user_id)
    if info and info[1] == 1: # can_pay column
        return True
    return False

# --- 1. SHOW PAYMENT INFO (Updated for QR Scanner & UPI) ---
async def show_payment_info(event, plan_key):
    user_id = event.sender_id
    plan = PLAN_MAP.get(plan_key)
    if not plan: return

    # Save state
    WAITING_FOR_PAYMENT[user_id] = plan_key
    
    # Log Intent to Admin GC
    if LOG_GROUP:
        try:
            user = await event.get_sender()
            await bot.send_message(LOG_GROUP, f"💸 **Payment Intent:** `{user.first_name}` is buying **{plan['name']} ({plan['days']}d)** for ₹{plan['price']}.")
        except: pass

    is_ultra = "Ultra" in plan['name']
    
    # UPI ID logic - Config se ya direct
    upi_to_show = UPI_ID 
    
    pay_text = (
        f"🎯 **Selected Plan:** {plan['name']}\n"
        f"⏳ **Duration:** {plan['days']} Days\n"
        f"💰 **Amount:** ₹{plan['price']}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "**𝐏ᴧʏᴍᴇɴᴛ 𝐈ɴsᴛʀᴜᴄᴛɪᴏɴs:**\n"
        f"👉 UPI ID: `{upi_to_show}` (Tap to copy)\n\n"
        "✅ **After Payment:** Send the **Screenshot** here.\n"
        f"{'🎁 *Note: We will provide you an Account ID after verification.*' if is_ultra else ''}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    # QR Scanner Image logic (Local Asset Support)
    # Railway/VPS par 'assets/qr.jpg' path check karega
    qr_file = PAY_QR if os.path.exists(PAY_QR) else PAY_QR 

    try:
        # Purana message delete karke naya Photo message bhejenge
        await event.delete()
        await bot.send_file(
            event.chat_id,
            qr_file,
            caption=pay_text,
            buttons=[Button.inline("❌ Cancel / Change Plan", data="pay_now")]
        )
    except Exception as e:
        # Fallback agar photo na mile toh sirf text bhej do
        print(f"QR Send Error: {e}")
        await bot.send_message(
            event.chat_id, 
            pay_text, 
            buttons=[Button.inline("❌ Cancel / Change Plan", data="pay_now")]
        )

# --- 2. RECEIVE SCREENSHOT ---
@bot.on(events.NewMessage)
async def receive_screenshot(event):
    if not event.is_private or not event.photo: return
    user_id = event.sender_id
    
    if user_id in WAITING_FOR_PAYMENT:
        plan_key = WAITING_FOR_PAYMENT[user_id]
        plan = PLAN_MAP[plan_key]
        user = await event.get_sender()
        
        await event.reply(
            f"✅ **Screenshot Received for {plan['name']}!**\n"
            "Admins are verifying your payment. You will be notified shortly."
        )
        
        is_ultra = "Ultra" in plan['name']
        admin_text = (
            f"{'🔥 **ULTRA ID REQUEST** 🔥' if is_ultra else '🔔 **NEW PAYMENT REQUEST**'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {user.first_name} (@{user.username if user.username else 'N/A'})\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"💎 **Plan:** `{plan['name']}`\n"
            f"⏳ **Days:** `{plan['days']}`\n"
            f"💰 **Amount:** `₹{plan['price']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'⚠️ **ACTION:** Provide ID after approving!' if is_ultra else 'Verify and approve below:'}"
        )
        
        if LOG_GROUP:
            await bot.send_file(
                LOG_GROUP,
                event.photo,
                caption=admin_text,
                buttons=[
                    [Button.inline(f"✅ Approve {plan['days']}d", data=f"appr_{plan_key}_{user_id}")],
                    [Button.inline("❌ Reject", data=f"reject_{user_id}")]
                ]
            )
        
        del WAITING_FOR_PAYMENT[user_id]

# --- 4. SUDO APPROVAL LOGIC ---
@bot.on(events.CallbackQuery(pattern=r"appr_(\w+)_(\d+)"))
async def approve_payment(event):
    if not await can_user_approve(event.sender_id):
        await event.answer("⚠️ You don't have 'Pay' permission.", alert=True)
        return

    data = event.data.decode("utf-8").split("_")
    target_user_id = int(data[-1])
    plan_key = "_".join(data[1:-1])

    from database import get_sub_info
    status, _ = await get_sub_info(target_user_id)
    if status == "Active":
        return await event.answer(
            "⚠️ This user already has an active premium plan!\n\n"
            "Kindly use /cancel first to remove the current plan before approving a new one.", 
            alert=True
        )

    plan_info = PLAN_MAP.get(plan_key)
    if not plan_info:
        return await event.answer("❌ Error: Invalid Plan Key.")

    admin_name = event.sender.first_name
    plan_name = plan_info['name'] 
    plan_days = plan_info['days'] 

    from database import add_subscription
    expiry = await add_subscription(
        target_user_id, 
        plan_type=plan_name, 
        days=plan_days
    )
    
    await event.edit(
        f"✅ **{plan_name} Activated**\n"
        f"🆔 **User:** `{target_user_id}`\n"
        f"⏳ **Duration:** {plan_days} Days\n"
        f"👮 **Admin:** {admin_name}\n"
        f"📅 **Expiry:** `{expiry.strftime('%Y-%m-%d %H:%M')}`"
    )
    
    try:
        feature_text = "⚠️ Standard: 1 module at a time." if "Standard" in plan_name else "🚀 Empire: All modules together!"
        success_msg = (
            f"🎉 **Premium Activated: {plan_name}**\n\n"
            f"Access granted for **{plan_days} days**.\n"
            f"Rule: {feature_text}\n\n"
            "Go to /modules and start your bot now!"
        )
        await bot.send_message(target_user_id, success_msg, buttons=[[Button.inline("⚙️ Open Modules", data="modules_main")]])
    except: pass

# --- SUDO REJECT LOGIC ---
@bot.on(events.CallbackQuery(pattern=r"reject_"))
async def reject_payment(event):
    if not await can_user_approve(event.sender_id):
        await event.answer("⚠️ Access Denied.", alert=True)
        return
    
    target_user_id = int(event.data.decode("utf-8").replace("reject_", ""))
    admin_name = event.sender.first_name
    await event.edit(f"❌ **Payment Rejected**\n🆔 User: `{target_user_id}`\n👮 Admin: {admin_name}")
    try:
        await bot.send_message(target_user_id, "⚠️ **Rejected:** Your screenshot was invalid. Please try again.")
    except: pass
