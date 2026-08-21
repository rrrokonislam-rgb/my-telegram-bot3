import os
import re
import asyncio
import zipfile
from threading import Thread
from flask import Flask
from hydrogram import Client, filters
from hydrogram.types import Message
from hydrogram.errors import SessionPasswordNeeded, AuthKeyUnregistered

# Python 3.14 Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# ১. আপনার ক্রেডেনশিয়াল (যে API ID দিয়ে সেশন বানানো সেটি ব্যবহার করুন)
# -------------------------------------------------------------
API_ID = 36966114  # আপনার আসল API ID
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"

user_sessions = {}

# -------------------------------------------------------------
# ২. Flask Web Server
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Active!"

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

bot = Client("main_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_sessions[message.chat.id] = {"step": "WAITING_FILE"}
    await message.reply_text(
        "👋 **Session Backup Bot**\n\n"
        "আপনার সেশনের `.session` অথবা `.zip` ফাইলটি পাঠান (Document হিসেবে)।"
    )

# ZIP এবং SESSION দুই ধরণের ফাইল রিসিভ করার হ্যান্ডলার
@bot.on_message(filters.private & filters.document)
async def handle_document(client: Client, message: Message):
    chat_id = message.chat.id
    file_name = message.document.file_name.lower()
    
    if not (file_name.endswith(".session") or file_name.endswith(".zip")):
        await message.reply_text("❌ অনুগ্রহ করে `.session` অথবা `.zip` ফাইল পাঠান!")
        return

    msg = await message.reply_text("📥 ফাইল প্রসেস করা হচ্ছে...")
    
    # ডিরেক্টরি তৈরি
    user_dir = f"dir_{chat_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    download_path = os.path.join(user_dir, message.document.file_name)
    await message.download(file_name=download_path)

    session_file_path = None

    # ZIP ফাইল এক্সট্র্যাক্ট করা
    if file_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall(user_dir)
            
            # ZIP এর ভেতর থেকে .session ফাইল খুঁজে বের করা
            for root, dirs, files in os.walk(user_dir):
                for f in files:
                    if f.endswith(".session"):
                        session_file_path = os.path.join(root, f)
                        break
            if not session_file_path:
                await msg.edit_text("❌ জিপ ফাইলের ভেতরে কোনো `.session` ফাইল পাওয়া যায়নি!")
                return
        except Exception as e:
            await msg.edit_text(f"❌ ZIP ফাইলটি আনজিপ করতে ব্যর্থ হয়েছে: `{e}`")
            return
    else:
        session_file_path = download_path

    # ফাইল ফাইন্ড সফল
    clean_session_name = session_file_path.replace(".session", "")

    user_sessions[chat_id] = {
        "step": "WAITING_2FA",
        "session_path": clean_session_name,
        "user_dir": user_dir
    }

    await msg.edit_text(
        "🔐 এই অ্যাকাউন্টে কি **2-Step Verification (2FA)** চালু আছে?\n\n"
        "• চালু থাকলে পাসওয়ার্ডটি লিখুন।\n"
        "• না থাকলে **`No`** লিখুন।"
    )

@bot.on_message(filters.private & filters.text & ~filters.command("start"))
async def process_cloning(client: Client, message: Message):
    chat_id = message.chat.id
    data = user_sessions.get(chat_id)

    if not data or data.get("step") != "WAITING_2FA":
        return

    password_input = message.text.strip()
    two_fa_pass = None if password_input.lower() == "no" else password_input
    
    msg = await message.reply_text("⚙️ প্রসেস শুরু হচ্ছে, সেশন চেক করা হচ্ছে...")

    session_name = data["session_path"]
    user_dir = data["user_dir"]
    new_session_name = os.path.join(user_dir, f"backup_{chat_id}")

    primary_client = Client(session_name, api_id=API_ID, api_hash=API_HASH)
    
    try:
        await primary_client.connect()
        me = await primary_client.get_me()
        phone_number = me.phone_number
        await msg.edit_text(f"✅ সেশন একটিভ আছে: `{phone_number}`\n⚡ ব্যাকআপ সেশন ফাইল তৈরি করা হচ্ছে...")
    except AuthKeyUnregistered:
        await msg.edit_text(
            "❌ **AUTH_KEY_UNREGISTERED এরর!**\n\n"
            "১. আপনার সেশনটি অন্য API ID দিয়ে তৈরি। কোডে একই `API_ID` ও `API_HASH` ব্যবহার করুন যা দিয়ে সেশনটি বানানো হয়েছে।\n"
            "২. সেশনটি এক্সপায়ার হয়ে গেছে।"
        )
        return
    except Exception as e:
        await msg.edit_text(f"❌ সেশনে সমস্যা ঘটেছে: `{e}`")
        return

    secondary_client = Client(new_session_name, api_id=API_ID, api_hash=API_HASH)
    await secondary_client.connect()
    
    try:
        sent_code = await secondary_client.send_code(phone_number)
        await msg.edit_text("📩 OTP অটো-রিড করা হচ্ছে...")
        
        await asyncio.sleep(4)
        otp_code = None

        async for nav_msg in primary_client.get_chat_history(777000, limit=3):
            if nav_msg.text:
                match = re.search(r'\b\d{5}\b', nav_msg.text)
                if match:
                    otp_code = match.group(0)
                    break

        if not otp_code:
            await msg.edit_text("❌ OTP রিড করা যায়নি।")
            await primary_client.disconnect()
            await secondary_client.disconnect()
            return

        try:
            await secondary_client.sign_in(phone_number, sent_code.phone_code_hash, otp_code)
        except SessionPasswordNeeded:
            if two_fa_pass:
                await secondary_client.check_password(two_fa_pass)
            else:
                await msg.edit_text("❌ 2FA পাসওয়ার্ড প্রয়োজন ছিল কিন্তু আপনি `No` দিয়েছিলেন।")
                await primary_client.disconnect()
                await secondary_client.disconnect()
                return

        await msg.edit_text("🎉 সফলভাবে ব্যাকআপ ডিভাইস ও সেশন তৈরি হয়ে গেছে!")

        await secondary_client.disconnect()
        await primary_client.disconnect()

        # ফাইল সেন্ড
        final_file = f"{new_session_name}.session"
        await message.reply_document(
            document=final_file,
            caption="✅ **নতুন ব্যাকআপ সেশন তৈরি সম্পন্ন!**"
        )

    except Exception as e:
        await msg.edit_text(f"❌ সমস্যা হয়েছে: `{e}`")

if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    bot.run()
