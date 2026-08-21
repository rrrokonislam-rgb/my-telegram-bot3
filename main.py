import asyncio
from threading import Thread
from flask import Flask
from hydrogram import Client, filters
from hydrogram.types import Message

# -------------------------------------------------------------
# ⚠️ Python 3.14 Event Loop Fix (এই ৩টি লাইন এরর সমাধান করবে)
# -------------------------------------------------------------
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# -------------------------------------------------------------
# ১. আপনার ক্রেডেনশিয়াল
# -------------------------------------------------------------
API_ID = 36966114  # আপনার আসল API ID (সংখ্যা)
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"  # উদ্ধৃতি চিহ্নের ভেতরে
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"  # উদ্ধৃতি চিহ্নের ভেতরে

# -------------------------------------------------------------
# ২. Flask Web Server (Render App ২৪/৭ অ্যাক্টিভ রাখার জন্য)
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running perfectly!"

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

# /start কমান্ড হ্যান্ডলার
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    welcome_text = (
        f"👋 **হ্যালো {message.from_user.first_name}!**\n\n"
        "বটটি সফলভাবে সক্রিয় হয়েছে এবং ২৪/৭ চালু আছে।"
    )
    await message.reply_text(welcome_text)

# -------------------------------------------------------------
# ৪. মেইন এক্সিকিউশন
# -------------------------------------------------------------
if __name__ == "__main__":
    # ফ্ল্যাঙ্ক ওয়েব সার্ভার ব্যাকগ্রাউন্ডে চালু করা
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    print("🤖 Bot is starting...")
    bot.run()
