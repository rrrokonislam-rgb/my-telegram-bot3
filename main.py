import os
import re
import asyncio
import zipfile
from threading import Thread
from flask import Flask
from hydrogram import Client as BotClient, filters
from hydrogram.types import Message
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# Python 3.14 Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# ১. আপনার ক্রেডেনশিয়াল (আপনার API ID, Hash ও Token বসান)
# -------------------------------------------------------------
API_ID = 36966114  # আপনার আসল API ID (সংখ্যা)
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"

user_sessions = {}

# -------------------------------------------------------------
# ২. Flask Server (Render 24/7 চালু রাখার জন্য)
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Active!"

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

# প্রধান বট (Hydrogram)
bot = BotClient("main_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: BotClient, message: Message):
    user_sessions[message.chat.id] = {"step": "WAITING_FILE"}
    await message.reply_text(
        "👋 **Session Backup & Device Cloner Bot**\n\n"
        "আপনার `.session` অথবা `.zip` ফাইলটি পাঠান (Document হিসেবে)।"
    )

# ফাইল গ্রহণ
@bot.on_message(filters.private & filters.document)
async def handle_document(client: BotClient, message: Message):
    chat_id = message.chat.id
    file_name = message.document.file_name.lower()
    
    if not (file_name.endswith(".session") or file_name.endswith(".zip")):
        await message.reply_text("❌ অনুগ্রহ করে `.session` অথবা `.zip` ফাইল পাঠান!")
        return

    msg = await message.reply_text("📥 ফাইল ডাউনলোড ও আনজিপ করা হচ্ছে...")
    
    user_dir = f"dir_{chat_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    download_path = os.path.join(user_dir, message.document.file_name)
    await message.download(file_name=download_path)

    session_file_path = None

    if file_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall(user_dir)
            
            for root, dirs, files in os.walk(user_dir):
                for f in files:
                    if f.endswith(".session"):
                        session_file_path = os.path.join(root, f)
                        break
            if not session_file_path:
                await msg.edit_text("❌ জিপের ভেতরে কোনো `.session` ফাইল পাওয়া যায়নি!")
                return
        except Exception as e:
            await msg.edit_text(f"❌ ZIP আনজিপ করা যায়নি: `{e}`")
            return
    else:
        session_file_path = download_path

    user_sessions[chat_id] = {
        "step": "WAITING_2FA",
        "session_path": session_file_path,
        "user_dir": user_dir
    }

    await msg.edit_text(
        "🔐 এই অ্যাকাউন্টে কি **2-Step Verification (2FA)** চালু আছে?\n\n"
        "• চালু থাকলে পাসওয়ার্ড লিখুন।\n"
        "• না থাকলে **`No`** লিখে পাঠান।"
    )

# ব্যাকআপ জেনারেট প্রসেস (Telethon দিয়ে)
@bot.on_message(filters.private & filters.text & ~filters.command("start"))
async def process_cloning(client: BotClient, message: Message):
    chat_id = message.chat.id
    data = user_sessions.get(chat_id)

    if not data or data.get("step") != "WAITING_2FA":
        return

    password_input = message.text.strip()
    two_fa_pass = None if password_input.lower() == "no" else password_input
    
    msg = await message.reply_text("⚙️ প্রসেস শুরু হচ্ছে, সেশন চেক করা হচ্ছে...")

    session_file = data["session_path"]
    user_dir = data["user_dir"]
    new_session_path = os.path.join(user_dir, f"backup_{chat_id}.session")

    # Telethon Client ব্যবহার
    primary_client = TelegramClient(session_file.replace(".session", ""), API_ID, API_HASH)
    
    try:
        await primary_client.connect()
        if not await primary_client.is_user_authorized():
            await msg.edit_text("❌ সেশন ফাইলটি এক্সপায়ার বা অকার্যকর!")
            await primary_client.disconnect()
            return

        me = await primary_client.get_me()
        phone_number = me.phone
        await msg.edit_text(f"✅ সেশন একটিভ: `{phone_number}`\n⚡ ব্যাকআপ সেশন ফাইল তৈরি হচ্ছে...")

        # নতুন ক্লায়েন্ট চালু করা
        secondary_client = TelegramClient(new_session_path.replace(".session", ""), API_ID, API_HASH)
        await secondary_client.connect()
        
        sent_code = await secondary_client.send_code_request(phone_number)
        await msg.edit_text("📩 OTP অটো-রিড করা হচ্ছে (777000 থেকে)...")
        
        await asyncio.sleep(4)
        otp_code = None

        # 777000 চ্যাট থেকে অটোমেটিক OTP পড়া
        async for nav_msg in primary_client.iter_messages(777000, limit=3):
            if nav_msg.text:
                match = re.search(r'\b\d{5}\b', nav_msg.text)
                if match:
                    otp_code = match.group(0)
                    break

        if not otp_code:
            await msg.edit_text("❌ OTP অটো-রিড করা যায়নি!")
            await primary_client.disconnect()
            await secondary_client.disconnect()
            return

        # নতুন সেশনে সাইন ইন
        try:
            await secondary_client.sign_in(phone_number, otp_code)
        except SessionPasswordNeededError:
            if two_fa_pass:
                await secondary_client.sign_in(password=two_fa_pass)
            else:
                await msg.edit_text("❌ 2FA পাসওয়ার্ড প্রয়োজন কিন্তু আপনি `No` দিয়েছিলেন।")
                await primary_client.disconnect()
                await secondary_client.disconnect()
                return

        await msg.edit_text("🎉 সফলভাবে ব্যাকআপ সেশন তৈরি হয়েছে! ফাইল সেন্ড করা হচ্ছে...")

        await secondary_client.disconnect()
        await primary_client.disconnect()

        # ব্যাকআপ ফাইল ইউজারের কাছে পাঠানো
        await message.reply_document(
            document=new_session_path,
            caption="✅ **নতুন ব্যাকআপ সেশন ফাইল তৈরি সম্পন্ন!**"
        )

    except Exception as e:
        await msg.edit_text(f"❌ সমস্যা হয়েছে: `{e}`")

    finally:
        user_sessions.pop(chat_id, None)

if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    bot.run()
