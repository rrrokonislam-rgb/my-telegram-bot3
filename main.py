import os
import asyncio
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact
from telethon.errors import FloodWaitError

# -------------------------------------------------------------
# Render Live Keep-Alive Server
# -------------------------------------------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Phone Checker Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# -------------------------------------------------------------
# Bot Configurations
# -------------------------------------------------------------
# BotFather থেকে পাওয়া তোর আসল টোকেনটি বসা
BOT_TOKEN = "8983719162:AAH3tyQ29g19y7TK63-9L29bGZNQwwLyaaY"  

# my.telegram.org থেকে পাওয়া তোর নিজস্ব API ID এবং API HASH বসা
API_ID = 36966114  # তোর নিজস্ব API ID (ইনটেজার নম্বরে)
API_HASH = "5b4e9d0389efb9117afa0ee26bb790d5" # তোর নিজস্ব API HASH (স্ট্রিং হিসেবে)

bot = TelegramClient('checker_bot_session', API_ID, API_HASH)

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    await event.respond(
        "🔎 **Telegram Number Status Checker Bot**\n\n"
        "যে নম্বরটি চেক করতে চাস, সেটি কান্ট্রি কোড সহ লিখে পাঠা।\n"
        "উদাহরণ: `+88017XXXXXXXX` বা `+13214567890`"
    )

@bot.on(events.NewMessage)
async def check_number_handler(event):
    if event.text.startswith('/'):
        return

    phone_number = event.text.strip()
    
    if not phone_number.startswith('+'):
        await event.respond("❌ নম্বরটি অবশ্যই `+` এবং কান্ট্রি কোড সহ পাঠাতে হবে। যেমন: `+88017XXXXXXXX`")
        return

    await event.respond(f"🔍 **Checking Telegram Server for:** `{phone_number}`...")

    # কন্টাক্ট ইমপোর্ট করে দেখার লজিক
    temp_contact = InputPhoneContact(
        client_id=0,
        phone=phone_number,
        first_name="Check",
        last_name="Temp"
    )

    try:
        # টেলিগ্রাম সার্ভারে কন্টাক্ট ক্যোয়েরি
        result = await bot(ImportContactsRequest([temp_contact]))

        # ১. নম্বরটিতে যদি আগে থেকেই অ্যাকাউন্ট খোলা থাকে
        if result.users:
            user = result.users[0]
            
            first_name = user.first_name or "N/A"
            last_name = user.last_name or ""
            full_name = f"{first_name} {last_name}".strip()
            username = f"@{user.username}" if user.username else "No Username Set"
            user_id = user.id

            # ডাটা পরিষ্কার করা
            await bot(DeleteContactsRequest(id=[user.id]))

            response = (
                "⚠️ **ALREADY REGISTERED ACCOUNT!**\n\n"
                f"📱 **Phone:** `{phone_number}`\n"
                f"👤 **Name:** {full_name}\n"
                f"🆔 **User ID:** `{user_id}`\n"
                f"🔗 **Username:** {username}\n"
                "📌 *Status: এই নম্বরে আগে থেকেই টেলিগ্রাম অ্যাকাউন্ট খোলা আছে।*"
            )
            await event.respond(response)

        # ২. নম্বরটি যদি একদম ফুল ফ্রেশ হয়
        else:
            response = (
                "✨ **FULL FRESH NUMBER!**\n\n"
                f"📱 **Phone:** `{phone_number}`\n"
                "📌 *Status: এই নম্বরে কখনোই কোনো টেলিগ্রাম অ্যাকাউন্ট খোলা হয়নি।*"
            )
            await event.respond(response)

    except FloodWaitError as e:
        await event.respond(f"⏳ Rate Limit hit! Wait {e.seconds} seconds and try again.")
    except Exception as e:
        await event.respond(f"❌ **Error:** `{str(e)}`")

# -------------------------------------------------------------
# Main Execution
# -------------------------------------------------------------
async def main():
    Thread(target=run_flask, daemon=True).start()
    await bot.start(bot_token=BOT_TOKEN)
    print("🤖 Checker Bot Active & Running!")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
