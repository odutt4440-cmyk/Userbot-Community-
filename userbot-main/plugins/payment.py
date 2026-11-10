import asyncio
import os
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from spl_qr import SPLQR
from bot_instance import bot 
from core.session_manager import SessionManager
from config import ADMIN_ID, LOG_GROUP, SUDO_USERS, UPI_ID

from database import add_subscription, get_sudo_info, get_sub_info

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

# --- 1. SHOW PAYMENT INFO (Kurigram + Dynamic QR) ---
async def show_payment_info(message, plan_key):
    user_id = message.from_user.id
    plan = PLAN_MAP.get(plan_key)
    if not plan: return

    WAITING_FOR_PAYMENT[user_id] = plan_key
    
    if LOG_GROUP:
        try:
            user_name = message.from_user.first_name or "User"
            await bot.send_message(
                LOG_GROUP, 
                f"💸 **Payment Intent:** `{user_name}` is buying **{plan['name']} ({plan['days']}d)** for ₹{plan['price']}."
            )
        except: pass

    is_ultra = "Ultra" in plan['name']
    amount = plan['price']
    
    # 🔥 DYNAMIC QR (amount ke saath)
    qr_filename = f"qr_{user_id}_{plan_key}.png"
    try:
        qr = SPLQR(name="Empire Userbot", upi_id=UPI_ID)
        qr.generate(amount=amount)  # spl-qr amount ke saath QR banata hai [citation:13]
        # spl-qr default file save karta hai, rename karo
        if os.path.exists("qr.png"):
            os.rename("qr.png", qr_filename)
        elif os.path.exists(f"{UPI_ID}.png"): # kabhi kabhi UPI ID naam se save karta hai
            os.rename(f"{UPI_ID}.png", qr_filename)
    except Exception as e:
        print(f"QR Generate Error: {e}")
        qr_filename = None

    pay_text = (
        f"🎯 **Selected Plan:** {plan['name']}\n"
        f"⏳ **Duration:** {plan['days']} Days\n"
        f"💰 **Amount:** ₹{amount}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "**𝐏ᴧʏᴍᴇɴᴛ 𝐈ɴsᴛʀᴜᴄᴛɪᴏɴs:**\n"
        f"👉 UPI ID: `{UPI_ID}` (Tap to copy)\n\n"
        "✅ **After Payment:** Send the **Screenshot** here.\n"
        f"{'🎁 *Note: We will provide you an Account ID after verification.*' if is_ultra else ''}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    cancel_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel / Change Plan", callback_data="pay_now", style=ButtonStyle.DANGER)]
    ])

    try:
        await message.delete()
        
        if qr_filename and os.path.exists(qr_filename):
            await bot.send_photo(
                message.chat.id,
                qr_filename,
                caption=pay_text,
                reply_markup=cancel_btn
            )
            os.remove(qr_filename)  # Cleanup
        else:
            await bot.send_message(
                message.chat.id,
                pay_text + "\n\n⚠️ QR generation failed. Please use UPI ID above.",
                reply_markup=cancel_btn
            )
    except Exception as e:
        print(f"Payment Info Error: {e}")
        await bot.send_message(
            message.chat.id, 
            pay_text, 
            reply_markup=cancel_btn
        )

# --- 2. RECEIVE SCREENSHOT ---
@bot.on_message(filters.private & filters.photo)
async def receive_screenshot(client, message):
    user_id = message.from_user.id
    
    if user_id in WAITING_FOR_PAYMENT:
        plan_key = WAITING_FOR_PAYMENT[user_id]
        plan = PLAN_MAP[plan_key]
        user_name = message.from_user.first_name or "User"
        username = message.from_user.username or "N/A"
        
        await message.reply(
            f"✅ **Screenshot Received for {plan['name']}!**\n"
            "Admins are verifying your payment. You will be notified shortly."
        )
        
        is_ultra = "Ultra" in plan['name']
        admin_text = (
            f"{'🔥 **ULTRA ID REQUEST** 🔥' if is_ultra else '🔔 **NEW PAYMENT REQUEST**'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {user_name} (@{username})\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"💎 **Plan:** `{plan['name']}`\n"
            f"⏳ **Days:** `{plan['days']}`\n"
            f"💰 **Amount:** `₹{plan['price']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'⚠️ **ACTION:** Provide ID after approving!' if is_ultra else 'Verify and approve below:'}"
        )
        
        if LOG_GROUP:
            # Native Kurigram colored buttons — photo ke saath ek hi message
            admin_buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"✅ Approve {plan['days']}d", 
                    callback_data=f"appr_{plan_key}_{user_id}",
                    style=ButtonStyle.SUCCESS  # Green [citation:1]
                )],
                [InlineKeyboardButton(
                    "❌ Reject", 
                    callback_data=f"reject_{user_id}",
                    style=ButtonStyle.DANGER   # Red [citation:1]
                )]
            ])
            
            try:
                await bot.send_photo(
                    LOG_GROUP,
                    message.photo.file_id,
                    caption=admin_text,
                    reply_markup=admin_buttons
                )
            except Exception as e:
                print(f"Admin Log Error: {e}")
                # Fallback: text only
                await bot.send_message(LOG_GROUP, admin_text, reply_markup=admin_buttons)
        
        del WAITING_FOR_PAYMENT[user_id]

# --- 3. SUDO APPROVAL LOGIC ---
@bot.on_callback_query(filters.regex(r"^appr_(\w+)_(\d+)$"))
async def approve_payment(client, query):
    if not await can_user_approve(query.from_user.id):
        await query.answer("⚠️ You don't have 'Pay' permission.", show_alert=True)
        return

    match = query.matches[0]
    plan_key = match.group(1)
    target_user_id = int(match.group(2))

    status, _ = await get_sub_info(target_user_id)
    if status == "Active":
        return await query.answer(
            "⚠️ This user already has an active premium plan!\n\n"
            "Kindly use /cancel first to remove the current plan before approving a new one.", 
            show_alert=True
        )

    plan_info = PLAN_MAP.get(plan_key)
    if not plan_info:
        return await query.answer("❌ Error: Invalid Plan Key.", show_alert=True)

    admin_name = query.from_user.first_name or "Admin"
    plan_name = plan_info['name'] 
    plan_days = plan_info['days'] 

    expiry = await add_subscription(
        target_user_id, 
        plan_type=plan_name, 
        days=plan_days
    )
    
    await query.message.edit_text(
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
        await bot.send_message(
            target_user_id, 
            success_msg, 
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚙️ Open Modules", callback_data="modules_main", style=ButtonStyle.PRIMARY)]
            ])
        )
    except: pass

# --- 4. SUDO REJECT LOGIC ---
@bot.on_callback_query(filters.regex(r"^reject_(\d+)$"))
async def reject_payment(client, query):
    if not await can_user_approve(query.from_user.id):
        await query.answer("⚠️ Access Denied.", show_alert=True)
        return
    
    target_user_id = int(query.matches[0].group(1))
    admin_name = query.from_user.first_name or "Admin"
    
    await query.message.edit_text(
        f"❌ **Payment Rejected**\n"
        f"🆔 User: `{target_user_id}`\n"
        f"👮 Admin: {admin_name}"
    )
    try:
        await bot.send_message(
            target_user_id, 
            "⚠️ **Rejected:** Your screenshot was invalid. Please try again."
        )
    except: pass
