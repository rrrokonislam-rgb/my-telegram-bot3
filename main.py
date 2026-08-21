import asyncio
from threading import Thread
from flask import Flask
from hydrogram import Client, filters
from hydrogram.types import Message
from hydrogram.errors import SessionPasswordNeeded

# Python 3.14 Event Loop Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# ১. আপনার ক্রেডেনশিয়াল (আপনার তথ্যগুলো বসান)
# -------------------------------------------------------------
API_ID = 36966114  # আপনার আসল API ID (সংখ্যা)
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"

# পেন্ডিং সেশন ডাটা রাখার জন্য ডিকশনারি
user_states = {}

# -------------------------------------------------------------
# ২. Flask Web Server (Render App সক্রিয় রাখার জন্য)
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

# -------------------------------------------------------------
# ৩. Hydrogram Bot Client
# -------------------------------------------------------------
bot = Client(
    "my_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "নতুন ডিভাইস/সেশন যুক্ত করতে বা বানাতে লিখুন: `/login`"
    )

@bot.on_message(filters.command("login") & filters.private)
async def ask_phone(client: Client, message: Message):
    user_states[message.chat.id] = {"step": "WAITING_PHONE"}
    await message.reply_text("📱 যে অ্যাকাউন্টের নতুন ডিভাইস সেশন বানাবেন, সেটির **ফোন নম্বর** আন্তর্জাতিক ফরম্যাটে দিন:\n\nউদাহরণ: `+88017XXXXXXXX`")

@bot.on_message(filters.private & ~filters.command(["start", "login"]))
async def handle_inputs(client: Client, message: Message):
    chat_id = message.chat.id
    state = user_states.get(chat_id, {}).get("step")

    # ধাপ ১: ফোন নম্বর গ্রহণ ও OTP পাঠানো
    if state == "WAITING_PHONE":
        phone_number = message.text.strip()
        temp_client = Client(f"temp_{chat_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await temp_client.connect()
        
        try:
            sent_code = await temp_client.send_code(phone_number)
            user_states[chat_id] = {
                "step": "WAITING_OTP",
                "phone": phone_number,
                "client": temp_client,
                "hash": sent_code.phone_code_hash
            }
            await message.reply_text("📩 আপনার টেলিগ্রাম অ্যাপে **OTP কোড** পাঠানো হয়েছে।\n\nকোডটি নিচে লিখুন (যেমন: `1 2 3 4 5` বা `12345`):")
        except Exception as e:
            await message.reply_text(f"❌ সমস্যা হয়েছে: `{e}`")
            await temp_client.disconnect()
            user_states.pop(chat_id, None)

    # ধাপ ২: OTP গ্রহণ ও লগইন সম্পন্ন করা
    elif state == "WAITING_OTP":
        otp = message.text.replace(" ", "").strip()
        data = user_states.get(chat_id)
        temp_client = data["client"]
        
        try:
            await temp_client.sign_in(data["phone"], data["hash"], otp)
            string_session = await temp_client.export_session_string()
            
            await message.reply_text(
                "✅ **নতুন ডিভাইস/সেশন সফলভাবে যুক্ত হয়েছে!**\n\n"
                f"**String Session:**\n`{string_session}`"
            )
            await temp_client.disconnect()
            user_states.pop(chat_id, None)
            
        except SessionPasswordNeeded:
            user_states[chat_id]["step"] = "WAITING_2FA"
            await message.reply_text("🔐 অ্যাকাউন্টে 2-Step Verification অন করা আছে। আপনার **2FA পাসওয়ার্ডটি** লিখুন:")
        except Exception as e:
            await message.reply_text(f"❌ OTP ভুল বা সমস্যা হয়েছে: `{e}`")

    # ধাপ ৩: 2FA পাসওয়ার্ড গ্রহণ
    elif state == "WAITING_2FA":
        password = message.text.strip()
        data = user_states.get(chat_id)
        temp_client = data["client"]
        
        try:
            await temp_client.check_password(password)
            string_session = await temp_client.export_session_string()
            
            await message.reply_text(
                "✅ **নতুন ডিভাইস/সেশন সফলভাবে যুক্ত হয়েছে!**\n\n"
                f"**String Session:**\n`{string_session}`"
            )
            await temp_client.disconnect()
            user_states.pop(chat_id, None)
        except Exception as e:
            await message.reply_text(f"❌ পাসওয়ার্ড ভুল হয়েছে: `{e}`")

# -------------------------------------------------------------
# ৪. মেইন এক্সিকিউশন
# -------------------------------------------------------------
if __name__ == "__main__":
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    print("🤖 Bot is starting...")
    bot.run()
