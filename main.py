import asyncio
from threading import Thread
from flask import Flask
from hydrogram import Client, filters
from hydrogram.types import Message

# -------------------------------------------------------------
# ১. আপনার তথ্যগুলো নিচে উদ্ধৃতি চিহ্ন " " এর ভেতরে বসিয়ে দিন
# -------------------------------------------------------------
API_ID = 36966114  # এখানে আপনার API ID বসান (কোনো উদ্ধৃতি চিহ্ন ছাড়া)
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5"
BOT_TOKEN = "8775664193:AAEFe-x3jbPu2RJ8orQFERjJxewDFBI98qs"

# -------------------------------------------------------------
# ২. Flask Web Server (Render অ্যাপ সক্রিয় রাখার জন্য)
# -------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running 24/7!"

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

# /start কমান্ড
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    welcome_text = (
        f"👋 **হ্যালো {message.from_user.first_name}!**\n\n"
        "বটটি সফলভাবে সক্রিয় হয়েছে।\n"
        "নতুন ডিভাইস বা সেশন তৈরি করতে সাহায্য পেতে যোগাযোগ করুন।"
    )
    await message.reply_text(welcome_text)

# -------------------------------------------------------------
# ৪. মেইন এক্সিকিউশন
# -------------------------------------------------------------
if __name__ == "__main__":
    # সার্ভার চালু করা
    server_thread = Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    print("🤖 Bot is starting...")
    bot.run()
