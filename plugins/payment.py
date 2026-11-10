import asyncio
import os
import glob
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle
from spl_qr import SPLQR
from bot_instance import bot 
from core.session_manager import SessionManager
from config import ADMIN_ID, LOG_GROUP, SUDO_USERS, UPI_ID, START_PIC

from database import (
    add_subscription, 
    get_sudo_info, 
    get_sub_info,
    get_plan
)

# 🔥 DEBUG: Ye log build mein dikhega
print("[DEBUG] ✅ PAYMENT.PY LOADED - NEW CODE ACTIVE")

# Tracking users: {user_id: plan_key}
WAITING_FOR_PAYMENT = {}

# --- HELPER: CHECK PAYMENT POWER ---
async def can_user_approve(user_id):
    if user_id == ADMIN_ID: return True
    info = await get_sudo_info(user_id)
    if info and info[1] == 1: # can_pay column
        return True
    return False

# --- 1. SHOW PAYMENT INFO (Kurigram + Dynamic QR from DB) ---
async def show_payment_info(message, plan_key):
    print(f"[DEBUG] show_payment_info called for user: {message.from_user.id}, plan: {plan_key}")
    user_id = message.from_user.id
    
    # 🔥 DB se plan fetch karo (no more hardcoded PLAN_MAP)
    plan = await get_plan(plan_key)
    if not plan or not plan.get("active", True):
        await message.reply("⚠️ This plan is currently unavailable.")
        return

    WAITING_FOR_PAYMENT[user_id] = plan_key
    
    if LOG_GROUP:
        try:
            # User ka naam nikalna (button click karne wale ka)
            user_name = message.from_user.first_name or "User"
            username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
            
            await bot.send_message(
                LOG_GROUP, 
                f"💸 **Payment Intent:**\n"
                f"👤 **User:** {user_name} ({username})\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"💎 **Plan:** {plan['name']} ({plan['days']}d)\n"
                f"💰 **Amount:** ₹{plan['price']}"
            )
        except Exception as e:
            print(f"Log Group Error: {e}")

    is_ultra = "Ultra" in plan['name']
    amount = plan['price']
    
    # 🔥 DYNAMIC QR (Auto-Detect File Name)
    qr_filename = f"qr_{user_id}_{plan_key}.png"
    try:
        # Pehle purani .png files saaf karo (taaki nayi file easily mile)
        for f in glob.glob("*.png"):
            if f != START_PIC:
                try: os.remove(f)
                except: pass

        qr = SPLQR(name="Empire Userbot", upi_id=UPI_ID)
        qr.generate(amount=amount)
        
        # Ab check karo kaunsi nayi file bani
        png_files = glob.glob("*.png")
        if png_files:
            generated_file = png_files[0]
            os.rename(generated_file, qr_filename)
        else:
            print("QR Generate Error: Library ne koi file save nahi ki.")
            qr_filename = None
            
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
            os.remove(qr_filename)
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
@bot.on_message(filters.private & filters.photo, group=-3)
async def receive_screenshot(client, message):
    print(f"[DEBUG] 🔥 PHOTO RECEIVED from user: {message.from_user.id}")
    user_id = message.from_user.id
    
    if user_id in WAITING_FOR_PAYMENT:
        plan_key = WAITING_FOR_PAYMENT[user_id]
        plan = await get_plan(plan_key)
        if not plan:
            return
        user_name = message.from_user.first_name or "User"
        username = f"@{message.from_user.username}" if message.from_user.username else "N/A"
        
        await message.reply(
            f"✅ **Screenshot Received for {plan['name']}!**\n"
            "Admins are verifying your payment. You will be notified shortly."
        )
        
        is_ultra = "Ultra" in plan['name']
        admin_text = (
            f"{'🔥 **ULTRA ID REQUEST** 🔥' if is_ultra else '🔔 **NEW PAYMENT REQUEST**'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {user_name} ({username})\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"💎 **Plan:** `{plan['name']}`\n"
            f"⏳ **Days:** `{plan['days']}`\n"
            f"💰 **Amount:** `₹{plan['price']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'⚠️ **ACTION:** Provide ID after approving!' if is_ultra else 'Verify and approve below:'}"
        )
        
        if LOG_GROUP:
            admin_buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"✅ Approve {plan['days']}d", 
                    callback_data=f"appr_{plan_key}_{user_id}",
                    style=ButtonStyle.SUCCESS
                )],
                [InlineKeyboardButton(
                    "❌ Reject", 
                    callback_data=f"reject_{user_id}",
                    style=ButtonStyle.DANGER
                )]
            ])
            
            try:
                print(f"[DEBUG] Sending photo to LOG_GROUP: {LOG_GROUP}")
                await bot.send_photo(
                    LOG_GROUP,
                    message.photo.file_id,
                    caption=admin_text,
                    reply_markup=admin_buttons
                )
                print("[DEBUG] ✅ Photo successfully sent to LOG_GROUP")
            except Exception as e:
                print(f"[DEBUG] ❌ Admin Log Error: {e}")
                await bot.send_message(LOG_GROUP, admin_text, reply_markup=admin_buttons)
        
        del WAITING_FOR_PAYMENT[user_id]
    else:
        print(f"[DEBUG] ⚠️ User {user_id} sent photo but is not in WAITING_FOR_PAYMENT")

# --- 3. SUDO APPROVAL LOGIC (DB-connected) ---
@bot.on_callback_query(filters.regex(r"^appr_(\w+)_(\d+)$"))
async def approve_payment(client, query):
    print(f"[DEBUG] Approve button clicked by: {query.from_user.id}")
    if not await can_user_approve(query.from_user.id):
        return await query.answer("⚠️ You don't have 'Pay' permission.", show_alert=True)

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

    plan_info = await get_plan(plan_key)
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
    print(f"[DEBUG] Reject button clicked by: {query.from_user.id}")
    if not await can_user_approve(query.from_user.id):
        return await query.answer("⚠️ Access Denied.", show_alert=True)
    
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
