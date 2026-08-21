import os
import re
import asyncio
import zipfile
import shutil
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

API_ID = 12345678  # আপনার আসল API ID (সংখ্যা)
API_HASH = "YOUR_API_HASH_HERE"
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

user_states = {}

# Flask Keep-Alive Server
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Fast Session Backup Bot Active!"
def run_flask(): web_app.run(host="0.0.0.0", port=10000)

bot = BotClient("main_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: BotClient, message: Message):
    user_states[message.chat.id] = {"step": "WAITING_ZIP"}
    await message.reply_text(
        "⚡ **High-Speed Bulk Backup Bot**\n\n"
        "আপনার একাধিক `.session` ফাইল সমৃদ্ধ **.zip** ফাইলটি পাঠান।"
    )

@bot.on_message(filters.private & filters.document)
async def handle_zip(client: BotClient, message: Message):
    chat_id = message.chat.id
    if not message.document.file_name.lower().endswith(".zip"):
        await message.reply_text("❌ অনুগ্রহ করে শুধু **.zip** ফাইল পাঠান!")
        return

    msg = await message.reply_text("📥 ZIP ফাইল গ্রহণ করা হয়েছে...")
    user_dir = f"dir_{chat_id}"
    os.makedirs(user_dir, exist_ok=True)
    
    zip_path = os.path.join(user_dir, message.document.file_name)
    await message.download(file_name=zip_path)

    user_states[chat_id] = {
        "step": "WAITING_2FA",
        "zip_path": zip_path,
        "user_dir": user_dir
    }

    await msg.edit_text(
        "🔐 **2FA পাসওয়ার্ড সেটআপ:**\n\n"
        "• সব অ্যাকাউন্টে যদি একই 2FA পাসওয়ার্ড থাকে তবে তা লিখুন।\n"
        "• পাসওয়ার্ড না থাকলে **`no`** লিখে পাঠান।"
    )

# একক সেশন প্রসেসিং ফাংশন (Fast Async Task)
async def process_single_session(session_path, out_dir, two_fa_pass):
    file_name = os.path.basename(session_path)
    new_session_path = os.path.join(out_dir, f"backup_{file_name}")
    
    p_client = TelegramClient(session_path.replace(".session", ""), API_ID, API_HASH)
    s_client = TelegramClient(new_session_path.replace(".session", ""), API_ID, API_HASH)

    try:
        await p_client.connect()
        if not await p_client.is_user_authorized():
            return False

        me = await p_client.get_me()
        phone = me.phone

        await s_client.connect()
        await s_client.send_code_request(phone)

        await asyncio.sleep(2) # ওটিপি মেসেজ আসার সময়
        otp_code = None

        async for nav_msg in p_client.iter_messages(777000, limit=2):
            if nav_msg.text:
                match = re.search(r'\b\d{5}\b', nav_msg.text)
                if match:
                    otp_code = match.group(0)
                    break

        if not otp_code:
            return False

        try:
            await s_client.sign_in(phone, otp_code)
        except SessionPasswordNeededError:
            if two_fa_pass:
                await s_client.sign_in(password=two_fa_pass)
            else:
                return False

        await p_client.disconnect()
        await s_client.disconnect()
        return True

    except Exception:
        if p_client.is_connected(): await p_client.disconnect()
        if s_client.is_connected(): await s_client.disconnect()
        return False

# একাধিক সেশন একসাথে প্যারালালি প্রসেস করার হ্যান্ডলার
@bot.on_message(filters.private & filters.text & ~filters.command("start"))
async def start_bulk_process(client: BotClient, message: Message):
    chat_id = message.chat.id
    data = user_states.get(chat_id)

    if not data or data.get("step") != "WAITING_2FA":
        return

    two_fa_pass = None if message.text.strip().lower() == "no" else message.text.strip()
    msg = await message.reply_text("⚡ ব্যাকআপ প্রসেস শুরু হচ্ছে! জিপ আনপ্যাক করা হচ্ছে...")

    user_dir = data["user_dir"]
    zip_path = data["zip_path"]
    extract_dir = os.path.join(user_dir, "extracted")
    output_dir = os.path.join(user_dir, "output")
    
    os.makedirs(extract_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(extract_dir)

    # সেশন ফাইল সংগ্রহ
    session_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.endswith(".session"):
                session_files.append(os.path.join(root, f))

    total_files = len(session_files)
    if total_files == 0:
        await msg.edit_text("❌ ZIP ফাইলের ভেতর কোনো `.session` পাওয়া যায়নি!")
        return

    await msg.edit_text(f"🚀 মোট {total_files} টি সেশন পাওয়া গেছে। অতি দ্রুত প্যারালাল ব্যাকআপ শুরু হচ্ছে...")

    # সব সেশন একসাথে সমান্তরালভাবে প্রসেস করা (Parallel Execution)
    tasks = [process_single_session(s, output_dir, two_fa_pass) for s in session_files]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for r in results if r)

    if success_count == 0:
        await msg.edit_text("❌ ব্যাকআপ ব্যর্থ হয়েছে! সেশনগুলো এক্সপায়ার বা ইনভ্যালিড ছিল।")
        shutil.rmtree(user_dir, ignore_errors=True)
        user_states.pop(chat_id, None)
        return

    # নতুন ব্যাকআপ ZIP ফাইল বানানো
    out_zip_path = os.path.join(user_dir, f"BackedUp_Sessions_{chat_id}.zip")
    with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                zipf.write(os.path.join(root, file), arcname=file)

    await msg.edit_text(f"🎉 ব্যাকআপ সম্পূর্ণ!\n\nমোট: {total_files} টি\nসাকসেস: {success_count} টি\n\nZIP তৈরি হচ্ছে...")

    # ব্যাকআপ জিপ ফাইল পাঠানো
    await message.reply_document(
        document=out_zip_path,
        caption=f"✅ **ব্যাকআপ সম্পন্ন ZIP ফাইল!**\n\nস্বয়ংক্রিয়ভাবে ব্যাকআপ করা {success_count} টি সেশন এই ZIP-এর ভেতর রয়েছে।"
    )

    # ডিরেক্টরি ক্লিনআপ
    shutil.rmtree(user_dir, ignore_errors=True)
    user_states.pop(chat_id, None)

if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    bot.run()
