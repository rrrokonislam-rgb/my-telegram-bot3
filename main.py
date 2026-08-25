import os
import re
import asyncio
import zipfile
import shutil
import random
from threading import Thread
from flask import Flask, jsonify
from hydrogram import Client as BotClient, filters
from hydrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PasswordHashInvalidError,
    AuthKeyUnregisteredError,
    UserDeactivatedError
)

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# Credentials
# -------------------------------------------------------------
API_ID = 36966114
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"

MAX_CONCURRENT_TASKS = 25  

user_states = {}

DEVICE_PROFILES = [
    {"model": "Samsung Galaxy S24 Ultra", "sys": "Android 14", "app": "10.8.1"},
    {"model": "Xiaomi 14 Pro", "sys": "Android 14", "app": "10.7.0"},
    {"model": "OnePlus 12", "sys": "Android 14", "app": "10.8.0"},
    {"model": "Google Pixel 8 Pro", "sys": "Android 14", "app": "10.9.0"},
    {"model": "iPhone 15 Pro Max", "sys": "iOS 17.4", "app": "10.8.2"}
]

# -------------------------------------------------------------
# Flask Server
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Ultra Fast Backup Engine Active!"

@web_app.route('/ping')
def ping():
    return jsonify({"status": "ok"}), 200

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

bot = BotClient("ultra_fast_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# -------------------------------------------------------------
# Helper Function for Cleanup & Cancellation
# -------------------------------------------------------------
async def cancel_user_process(chat_id):
    if chat_id in user_states:
        user_states[chat_id]["is_cancelled"] = True
        
        # চলমান সব টাস্ক বন্ধ করা
        tasks = user_states[chat_id].get("active_tasks", [])
        for task in tasks:
            if not task.done():
                task.cancel()

        user_dir = user_states[chat_id].get("user_dir")
        if user_dir and os.path.exists(user_dir):
            shutil.rmtree(user_dir, ignore_errors=True)
            
        user_states.pop(chat_id, None)

# -------------------------------------------------------------
# Bot Commands & Message Handlers
# -------------------------------------------------------------
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client: BotClient, message: Message):
    await cancel_user_process(message.chat.id)
    user_states[message.chat.id] = {"step": "WAITING_ZIP"}
    await message.reply_text(
        "⚡ **Ultra Fast 1-Sec Session Backup Engine**\n\n"
        "Please send your **.zip** file containing `.session` files."
    )

@bot.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client: BotClient, message: Message):
    chat_id = message.chat.id
    if chat_id in user_states:
        await cancel_user_process(chat_id)
        await message.reply_text("❌ **All Operations Cancelled!**")
    else:
        await message.reply_text("ℹ️ No active process to cancel.")

@bot.on_callback_query(filters.regex("cancel_process"))
async def handle_cancel_callback(client: BotClient, callback: CallbackQuery):
    chat_id = callback.message.chat.id
    await cancel_user_process(chat_id)
    await callback.answer("🚫 Process Cancelled!", show_alert=True)
    await callback.message.edit_text("❌ **All Operations Cancelled!**")

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
        "user_dir": user_dir,
        "is_cancelled": False,
        "active_tasks": []
    }

    await msg.edit_text(
        "🔐 **2-Step Verification (2FA) Setup:**\n\n"
        "• If accounts share a 2FA password, enter it now.\n"
        "• If accounts do not have 2FA, reply with **`no`**."
    )

# -------------------------------------------------------------
# Worker Processing Function
# -------------------------------------------------------------
async def process_single_session_fast(chat_id, semaphore, session_path, success_dir, failed_dir, wrong_2fa_dir, two_fa_pass):
    if user_states.get(chat_id, {}).get("is_cancelled", False):
        return "cancelled"

    async with semaphore:
        if user_states.get(chat_id, {}).get("is_cancelled", False):
            return "cancelled"

        file_name = os.path.basename(session_path)
        dev = random.choice(DEVICE_PROFILES)

        p_client = TelegramClient(
            session_path.replace(".session", ""),
            API_ID,
            API_HASH,
            device_model=dev["model"],
            system_version=dev["sys"],
            app_version=dev["app"]
        )

        try:
            await asyncio.wait_for(p_client.connect(), timeout=10)
            if user_states.get(chat_id, {}).get("is_cancelled", False):
                await p_client.disconnect()
                return "cancelled"

            if not await p_client.is_user_authorized():
                shutil.copy(session_path, os.path.join(failed_dir, file_name))
                return "failed"

            me = await p_client.get_me()
            phone = me.phone

            temp_session_name = f"backup_{file_name}"
            temp_session_path = os.path.join(user_states[chat_id]["user_dir"], temp_session_name)
            
            s_client = TelegramClient(
                temp_session_path.replace(".session", ""),
                API_ID,
                API_HASH,
                device_model=dev["model"],
                system_version=dev["sys"],
                app_version=dev["app"]
            )

            await asyncio.wait_for(s_client.connect(), timeout=10)
            await s_client.send_code_request(phone)

            otp_code = None
            for _ in range(4):
                if user_states.get(chat_id, {}).get("is_cancelled", False):
                    await p_client.disconnect()
                    await s_client.disconnect()
                    if os.path.exists(temp_session_path):
                        os.remove(temp_session_path)
                    return "cancelled"

                await asyncio.sleep(2.5)
                async for nav_msg in p_client.iter_messages(777000, limit=5):
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
                if os.path.exists(temp_session_path):
                    os.remove(temp_session_path)
                shutil.copy(session_path, os.path.join(failed_dir, file_name))
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
                        if os.path.exists(temp_session_path):
                            os.remove(temp_session_path)
                        shutil.copy(session_path, os.path.join(wrong_2fa_dir, file_name))
                        return "wrong_2fa"
                else:
                    await p_client.disconnect()
                    await s_client.disconnect()
                    if os.path.exists(temp_session_path):
                        os.remove(temp_session_path)
                    shutil.copy(session_path, os.path.join(wrong_2fa_dir, file_name))
                    return "wrong_2fa"

            await p_client.disconnect()
            await s_client.disconnect()

            final_success_path = os.path.join(success_dir, temp_session_name)
            if os.path.exists(temp_session_path):
                shutil.move(temp_session_path, final_success_path)

            return "success"

        except Exception:
            shutil.copy(session_path, os.path.join(failed_dir, file_name))
            return "failed"
        finally:
            if p_client.is_connected():
                await p_client.disconnect()

def create_zip_from_dir(source_dir, output_zip_path):
    files = [f for f in os.listdir(source_dir) if f.endswith(".session")]
    if not files:
        return False
    with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            zipf.write(os.path.join(source_dir, file), arcname=file)
    return True

# -------------------------------------------------------------
# Main Text Process Handler
# -------------------------------------------------------------
@bot.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]))
async def start_bulk_process(client: BotClient, message: Message):
    chat_id = message.chat.id
    data = user_states.get(chat_id)

    if not data or data.get("step") != "WAITING_2FA":
        return

    user_input = message.text.strip()
    two_fa_pass = None if user_input.lower() == "no" else user_input

    cancel_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Cancel Processing", callback_data="cancel_process")]
    ])

    msg = await message.reply_text("⚡ Processing fast archive extraction...", reply_markup=cancel_keyboard)

    user_dir = data["user_dir"]
    zip_path = data["zip_path"]
    extract_dir = os.path.join(user_dir, "extracted")
    
    success_dir = os.path.join(user_dir, "success_dir")
    failed_dir = os.path.join(user_dir, "failed_dir")
    wrong_2fa_dir = os.path.join(user_dir, "wrong_2fa_dir")

    os.makedirs(extract_dir, exist_ok=True)
    os.makedirs(success_dir, exist_ok=True)
    os.makedirs(failed_dir, exist_ok=True)
    os.makedirs(wrong_2fa_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        await msg.edit_text(f"❌ Corrupt ZIP: `{e}`")
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
        await msg.edit_text("❌ No `.session` files found.")
        shutil.rmtree(user_dir, ignore_errors=True)
        user_states.pop(chat_id, None)
        return

    await msg.edit_text(f"🚀 Running Turbo Engine for {total_files} accounts...", reply_markup=cancel_keyboard)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    tasks = [
        asyncio.create_task(
            process_single_session_fast(chat_id, semaphore, s, success_dir, failed_dir, wrong_2fa_dir, two_fa_pass)
        )
        for s in session_files
    ]
    
    user_states[chat_id]["active_tasks"] = tasks

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        return

    if user_states.get(chat_id, {}).get("is_cancelled", False):
        return

    success_count = results.count("success")
    failed_count = results.count("failed")
    wrong_2fa_count = results.count("wrong_2fa")

    report = (
        "📊 **Batch Backup Report**\n\n"
        f"• **Total Accounts:** `{total_files}`\n"
        f"• **Successfully Backed Up:** `{success_count}`\n"
        f"• **Failed / Expired:** `{failed_count}`\n"
        f"• **2FA Mismatch:** `{wrong_2fa_count}`\n"
    )

    await msg.edit_text(f"{report}\n📦 Sending categorized files...")

    if success_count > 0:
        success_zip = os.path.join(user_dir, "Success_Sessions.zip")
        if create_zip_from_dir(success_dir, success_zip):
            await message.reply_document(
                document=success_zip,
                file_name="Success_Sessions.zip",
                caption=f"✅ **Success Sessions ({success_count})**"
            )

    if failed_count > 0:
        failed_zip = os.path.join(user_dir, "Failed_Invalid_Sessions.zip")
        if create_zip_from_dir(failed_dir, failed_zip):
            await message.reply_document(
                document=failed_zip,
                file_name="Failed_Invalid_Sessions.zip",
                caption=f"❌ **Failed / Invalid Sessions ({failed_count})**"
            )

    if wrong_2fa_count > 0:
        wrong_2fa_zip = os.path.join(user_dir, "Wrong_2FA_Sessions.zip")
        if create_zip_from_dir(wrong_2fa_dir, wrong_2fa_zip):
            await message.reply_document(
                document=wrong_2fa_zip,
                file_name="Wrong_2FA_Sessions.zip",
                caption=f"🔐 **Wrong 2FA Password Sessions ({wrong_2fa_count})**"
            )

    shutil.rmtree(user_dir, ignore_errors=True)
    user_states.pop(chat_id, None)

if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

    print("🤖 Turbo Engine Active with Fixed Cancel Command & Buttons...")
    bot.run()
