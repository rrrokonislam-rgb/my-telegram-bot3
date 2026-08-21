import os
import re
import asyncio
from threading import Thread
from flask import Flask
from hydrogram import Client, filters
from hydrogram.types import Message
from hydrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid

# Python 3.14 Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# ১. আপনার ক্রেডেনশিয়াল (কোটেশনের ভেতরে আপনার ডাটা বসান)
# -------------------------------------------------------------
API_ID = 36966114  # আপনার আসল API ID (সংখ্যা)
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"

# ইউজারের ডাটা ধরে রাখার স্থান
user_sessions = {}

# -------------------------------------------------------------
# ২. Flask Web Server (Render 24/7 অন রাখার জন্য)
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Session Backup & Cloner Bot is Active!"

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

# -------------------------------------------------------------
# ৩. Main Bot Client
# -------------------------------------------------------------
bot = Client(
    "main_backup_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# /start কমান্ড
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_sessions[message.chat.id] = {"step": "WAITING_FILE"}
    await message.reply_text(
        "👋 **Session Backup & Device Cloner Bot**\n\n"
        "আপনার রানিং অ্যাকাউন্টের একটি `.session` ফাইল পাঠাল (Document হিসেবে)।"
    )

# ফাইল গ্রহণ হ্যান্ডলার
@bot.on_message(filters.private & filters.document)
async def handle_document(client: Client, message: Message):
    chat_id = message.chat.id
    
    if not message.document.file_name.endswith(".session"):
        await message.reply_text("❌ অনুগ্রহ করে শুধু মাত্র `.session` ফাইল পাঠান!")
        return

    msg = await message.reply_text("📥 ফাইল ডাউনলোড করা হচ্ছে...")
    file_path = f"input_{chat_id}.session"
    await message.download(file_name=file_path)

    user_sessions[chat_id] = {
        "step": "WAITING_2FA",
        "file_path": file_path
    }

    await msg.edit_text(
        "🔐 এই অ্যাকাউন্টে কি **2-Step Verification (2FA)** চালু আছে?\n\n"
        "• চালু থাকলে পাসওয়ার্ডটি মেসেজে পাঠান।\n"
        "• চালু না থাকলে **`No`** লিখে পাঠান।"
    )

# 2FA এবং অটো-ক্লোনিং প্রসেস
@bot.on_message(filters.private & filters.text & ~filters.command("start"))
async def process_cloning(client: Client, message: Message):
    chat_id = message.chat.id
    data = user_sessions.get(chat_id)

    if not data or data.get("step") != "WAITING_2FA":
        return

    password_input = message.text.strip()
    two_fa_pass = None if password_input.lower() == "no" else password_input
    
    msg = await message.reply_text("⚙️ প্রসেস শুরু হচ্ছে, সেশন চেক করা হচ্ছে...")

    input_file = data["file_path"]
    session_name = input_file.replace(".session", "")
    new_session_name = f"backup_{chat_id}"
    new_session_file = f"{new_session_name}.session"

    # ১. ইউজার থেকে পাওয়া সেশন চালু করা
    primary_client = Client(session_name, api_id=API_ID, api_hash=API_HASH)
    
    try:
        await primary_client.connect()
        me = await primary_client.get_me()
        phone_number = me.phone_number
        await msg.edit_text(f"✅ সেশন পাওয়ার গেছে: `{phone_number}`\n⚡ নতুন ব্যাকআপ সেশন ফাইল তৈরি করা হচ্ছে...")
    except Exception as e:
        await msg.edit_text(f"❌ ইনপুট সেশন ফাইলটি অকার্যকর বা এক্সপায়ার হয়ে গেছে!\nএরর: `{e}`")
        if os.path.exists(input_file): os.remove(input_file)
        user_sessions.pop(chat_id, None)
        return

    # ২. ব্যাকগ্রাউন্ডে নতুন ক্লায়েন্ট তৈরি করে OTP রিকোয়েস্ট পাঠানো
    secondary_client = Client(new_session_name, api_id=API_ID, api_hash=API_HASH)
    await secondary_client.connect()
    
    try:
        sent_code = await secondary_client.send_code(phone_number)
        await msg.edit_text("📩 টেলিগ্রাম থেকে OTP পাঠানো হয়েছে। আগের সেশন থেকে অটো-রিড করা হচ্ছে...")
        
        # ৩. আগের সেশন থেকে অটোমেটিক OTP রিড করার লজিক (777000 Service Chat)
        await asyncio.sleep(4) # মেসেজ আসার জন্য ছোট বিরতি
        otp_code = None

        async for nav_msg in primary_client.get_chat_history(777000, limit=3):
            if nav_msg.text:
                # ৫ ডিজিটের কোড বের করার Regex Match
                match = re.search(r'\b\d{5}\b', nav_msg.text)
                if match:
                    otp_code = match.group(0)
                    break

        if not otp_code:
            await msg.edit_text("❌ OTP অটো-রিড করা যায়নি! প্রসেস বাতিল করা হলো।")
            await primary_client.disconnect()
            await secondary_client.disconnect()
            return

        # ৪. নতুন সেশনে OTP জমা দিয়ে লগইন করা
        try:
            await secondary_client.sign_in(phone_number, sent_code.phone_code_hash, otp_code)
        except SessionPasswordNeeded:
            if two_fa_pass:
                await secondary_client.check_password(two_fa_pass)
            else:
                await msg.edit_text("❌ অ্যাকাউন্টে 2FA চালু ছিল কিন্তু আপনি `No` দিয়েছিলেন। সঠিক পাসওয়ার্ড দিয়ে আবার চেষ্টা করুন।")
                await primary_client.disconnect()
                await secondary_client.disconnect()
                return

        await msg.edit_text("🎉 সফলভাবে ব্যাকআপ ডিভাইস ও সেশন তৈরি হয়ে গেছে! ফাইল পাঠানো হচ্ছে...")

        # ৫. সংযোগ বিচ্ছিন্ন করে নতুন ব্যাকআপ ফাইলটি ইউজারকে পাঠানো
        await secondary_client.disconnect()
        await primary_client.disconnect()

        await message.reply_document(
            document=new_session_file,
            caption=(
                "✅ **নতুন ব্যাকআপ সেশন তৈরি সম্পন্ন!**\n\n"
                "• এই ফাইলটি আলাদা ব্যাকআপ ডিভাইস হিসেবে কাজ করবে।\n"
                "• আগের ফাইলটি নষ্ট হয়ে গেলেও এটি দিয়ে অ্যাকাউন্ট রিকভার করা যাবে।"
            )
        )

    except Exception as e:
        await msg.edit_text(f"❌ প্রসেসে ত্রুটি ঘটেছে: `{e}`")
        if primary_client.is_connected: await primary_client.disconnect()
        if secondary_client.is_connected: await secondary_client.disconnect()

    finally:
        # ফাইল ও ডাটা ক্লিনআপ করা
        for f in [input_file, new_session_file]:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass
        user_sessions.pop(chat_id, None)

# -------------------------------------------------------------
# ৪. বট রানিং পার্ট
# -------------------------------------------------------------
if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    print("🤖 Backup & Auto-Cloner Bot is running...")
    bot.run()
