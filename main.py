import os
import asyncio
from hydrogram import Client
from hydrogram.errors import SessionPasswordNeeded

# Environment Variables থেকে ক্রেডেনশিয়াল গ্রহণ করবে
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ১. প্রধান বট ক্লায়েন্ট
bot = Client("main_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ২. নতুন ডিভাইস/সেশন যুক্ত করার ফাংশন
async def create_new_session():
    print("=== নতুন ডিভাইস / সেশন তৈরি করুন ===")
    phone_number = input("যে অ্যাকাউন্টে কাজ হবে সেটির ফোন নম্বর দিন (যেমন: +88017XXXXXXXX): ")
    
    # নতুন ডিভাইস সেশন তৈরি
    new_client = Client(f"session_{phone_number.replace('+', '')}", api_id=API_ID, api_hash=API_HASH)
    await new_client.connect()
    
    try:
        # টেলিগ্রামে OTP পাঠানোর রিকোয়েস্ট
        sent_code = await new_client.send_code(phone_number)
        print(f"OTP পাঠানো হয়েছে {phone_number} নম্বরে। (আপনার টেলিগ্রাম অ্যাপের অফিসিয়াল চ্যাট মেসেজ চেক করুন)")
        
        otp_code = input("টেলিগ্রামে পাওয়া 5 ডিজিটের OTP কোডটি লিখুন: ")
        
        try:
            # OTP দিয়ে লগইন
            await new_client.sign_in(phone_number, sent_code.phone_code_hash, otp_code)
        except SessionPasswordNeeded:
            # যদি Two-Step Verification (2FA) চালু থাকে
            two_step_pass = input("আপনার অ্যাকাউন্টের 2-Step Verification পাসওয়ার্ড দিন: ")
            await new_client.check_password(two_step_pass)
            
        # সেশন স্ট্রিং বের করা (যা দিয়ে পরবর্তীতে যেকোনো ডিভাইসে কাজ করা যাবে)
        string_session = await new_client.export_session_string()
        print("\n✅ সফলভাবে নতুন ডিভাইস সেশন যুক্ত হয়েছে!")
        print(f"আপনার নতুন String Session:\n\n{string_session}\n")
        
    except Exception as e:
        print(f"❌ এরর হয়েছে: {e}")
    finally:
        await new_client.disconnect()

if __name__ == "__main__":
    # সেশন তৈরি প্রসেস রান করার জন্য
    asyncio.run(create_new_session())
