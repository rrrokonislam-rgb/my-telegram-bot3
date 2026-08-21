import os
import re
import asyncio
import zipfile
import shutil
import random
from threading import Thread
from flask import Flask, jsonify
from hydrogram import Client as BotClient, filters
from hydrogram.types import Message
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PasswordHashInvalidError,
    AuthKeyUnregisteredError,
    UserDeactivatedError
)

# Python 3.14 Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# Credentials Setup
# -------------------------------------------------------------
API_ID = 36966114
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"

user_states = {}

# Official Multi-Device Profiles
DEVICE_PROFILES = [
    {"model": "Samsung Galaxy S24 Ultra", "sys": "Android 14", "app": "10.8.1"},
    {"model": "Xiaomi 14 Pro", "sys": "Android 14", "app": "10.7.0"},
    {"model": "OnePlus 12", "sys": "Android 14", "app": "10.8.0"},
    {"model": "Google Pixel 8 Pro", "sys": "Android 14", "app": "10.9.0"},
    {"model": "iPhone 15 Pro Max", "sys": "iOS 17.4", "app": "10.8.2"}
]

# -------------------------------------------------------------
# Flask Web Server for UptimeRobot Active Ping
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "100% Success Backup Engine Active!"

# UptimeRobot এর জন্য জেনুইন Ping Route
@web_app.route('/ping')
def ping():
    return jsonify({"status": "ok", "message": "Bot is alive and running!"}), 200

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

bot = BotClient("main_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: BotClient, message: Message):
    user_states[message.chat.id] = {"step": "WAITING_ZIP"}
    await message.reply_text(
        "⚡ **Unlimited Guaranteed Session Backup Engine**\n\n"
        "Please send your **.zip** file containing `.session` files."
    )

@bot.on_message(filters.private & filters.document)
async def handle_zip(client: BotClient, message: Message):
    chat_id = message.chat.id
    if not message.document.file_name.lower().endswith(".zip"):
        await message.reply_text("❌ Invalid format! Please send a `.zip` archive.")
        return

    msg = await message.reply_text("📥 Receiving ZIP archive...")
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
        "🔐 **2-Step Verification (2FA) Setup:**\n\n"
        "• If accounts share a 2FA password, enter it now.\n"
        "• If accounts do not have 2FA, reply with **`no`**."
    )

# -------------------------------------------------------------
# Worker Logic
# -------------------------------------------------------------
async def process_single_session(session_path, out_dir, two_fa_pass):
    file_name = os.path.basename(session_path)
    new_session_path = os.path.join(out_dir, f"backup_{file_name}")

    dev = random.choice(DEVICE_PROFILES)

    p_client = TelegramClient(
        session_path.replace(".session", ""),
        API_ID,
        API_HASH,
        device_model=dev["model"],
        system_version=dev["sys"],
        app_version=dev["app"]
    )
    
    s_client = TelegramClient(
        new_session_path.replace(".session", ""),
        API_ID,
        API_HASH,
        device_model=dev["model"],
        system_version=dev["sys"],
        app_version=dev["app"]
    )

    try:
        await p_client.connect()
        if not await p_client.is_user_authorized():
            return "failed"

        me = await p_client.get_me()
        phone = me.phone

        await s_client.connect()
        await s_client.send_code_request(phone)

        otp_code = None
        for _ in range(6):  # Checks up to 30 seconds for global accounts
            await asyncio.sleep(5)
            async for nav_msg in p_client.iter_messages(777000, limit=10):
                if nav_msg.text:
                    match = re.search(r'(?<!\d)\d{4,6}(?!\d)', nav_msg.text)
                    if match:
                        otp_code = match.group(0)
                        break
            if otp_code:
                break

        if not otp_code:
            await p_client.disconnect()
            await s_client.disconnect()
            return "failed"

        try:
            await s_client.sign_in(phone, otp_code)
        except SessionPasswordNeededError:
            if two_fa_pass:
                try:
                    await s_client.sign_in(password=two_fa_pass)
                except PasswordHashInvalidError:
                    await p_client.disconnect()
                    await s_client.disconnect()
                    if os.path.exists(new_session_path):
                        os.remove(new_session_path)
                    return "wrong_2fa"
            else:
                await p_client.disconnect()
                await s_client.disconnect()
                if os.path.exists(new_session_path):
                    os.remove(new_session_path)
                return "wrong_2fa"

        await p_client.disconnect()
        await s_client.disconnect()
        return "success"

    except (AuthKeyUnregisteredError, UserDeactivatedError):
        return "failed"
    except Exception:
        return "failed"
    finally:
        if p_client.is_connected():
            await p_client.disconnect()
        if s_client.is_connected():
            await s_client.disconnect()

# -------------------------------------------------------------
# Main Handler
# -------------------------------------------------------------
@bot.on_message(filters.private & filters.text & ~filters.command("start"))
async def start_bulk_process(client: BotClient, message: Message):
    chat_id = message.chat.id
    data = user_states.get(chat_id)

    if not data or data.get("step") != "WAITING_2FA":
        return

    user_input = message.text.strip()
    two_fa_pass = None if user_input.lower() == "no" else user_input

    msg = await message.reply_text("⚡ Unpacking archive and launching deep backup workers...")

    user_dir = data["user_dir"]
    zip_path = data["zip_path"]
    extract_dir = os.path.join(user_dir, "extracted")
    output_dir = os.path.join(user_dir, "output")

    os.makedirs(extract_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        await msg.edit_text(f"❌ Corrupt ZIP file: `{e}`")
        shutil.rmtree(user_dir, ignore_errors=True)
        user_states.pop(chat_id, None)
        return

    session_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.endswith(".session"):
                session_files.append(os.path.join(root, f))

    total_files = len(session_files)
    if total_files == 0:
        await msg.edit_text("❌ No `.session` files detected inside the archive.")
        shutil.rmtree(user_dir, ignore_errors=True)
        user_states.pop(chat_id, None)
        return

    await msg.edit_text(f"🚀 Backup process active for {total_files} accounts...")

    tasks = [process_single_session(s, output_dir, two_fa_pass) for s in session_files]
    results = await asyncio.gather(*tasks)

    success_count = results.count("success")
    failed_count = results.count("failed")
    wrong_2fa_count = results.count("wrong_2fa")

    report = (
        "📊 **Batch Backup Status Report**\n\n"
        f"• **Total Accounts:** `{total_files}`\n"
        f"• **Successfully Backed Up:** `{success_count}`\n"
        f"• **Failed / Expired:** `{failed_count}`\n"
        f"• **2FA Mismatch / Missing:** `{wrong_2fa_count}`\n"
    )

    if success_count == 0:
        await msg.edit_text(f"{report}\n❌ Process failed! No active accounts were backed up.")
        shutil.rmtree(user_dir, ignore_errors=True)
        user_states.pop(chat_id, None)
        return

    out_zip_path = os.path.join(user_dir, "Backup_Sessions.zip")
    with zipfile.ZipFile(out_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_dir):
            for file in files:
                zipf.write(os.path.join(root, file), arcname=file)

    await msg.edit_text(f"{report}\n📦 Uploading backup archive...")

    await message.reply_document(
        document=out_zip_path,
        file_name="Backup_Sessions.zip",
        caption=report
    )

    shutil.rmtree(user_dir, ignore_errors=True)
    user_states.pop(chat_id, None)

if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    print("🤖 Unstoppable Backup Engine Online...")
    bot.run()
