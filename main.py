import os
import secrets
import string
import threading
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery
)

# --- কনফিগারেশন ---
# এগুলো Render-এর Environment Variables থেকে নেবে অথবা সরাসরি বসাতে পারেন
API_ID = int(os.environ.get("API_ID", "1234567"))          # my.telegram.org থেকে
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")  # my.telegram.org থেকে
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token_here") # @BotFather থেকে

# যে ভেরিফিকেশন লিঙ্কটি ইউজারকে ভিজিট করতে হবে
VERIFY_URL = "https://urlbit.pro/wVLnd"

# ইন-মেমোরি ফাইল ডেটা স্টোর (প্রোডাকশনে MongoDB বা SQLite ব্যবহার করতে পারেন)
# ফাইল আইডি ও টাইপ ট্র্যাক করার জন্য
file_database = {}

# ইউজার স্টেট ট্র্যাকিং (কে আপলোড করতে চাচ্ছে)
user_states = {}

# --- Flask Server (Render Port Binding & Health Check) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- Pyrogram Client ---
bot = Client(
    "file_share_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def generate_random_id(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

# /start হ্যান্ডলার (ডিপ-লিঙ্কিং সহ)
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    text_data = message.text.split()
    
    # ইউজার যদি কোনো শেয়ার লিঙ্ক নিয়ে আসে (/start <unique_id>)
    if len(text_data) > 1:
        unique_id = text_data[1]
        
        if unique_id in file_database:
            # ভেরিফিকেশন মেসেজ দেখানো হবে
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 এই লিঙ্কে ক্লিক করুন", url=VERIFY_URL)],
                [InlineKeyboardButton("✅ আমি ক্লিক করেছি (ফাইল দিন)", callback_data=f"verify_{unique_id}")]
            ])
            await message.reply_text(
                "⚠️ **ভিডিও/ফাইল পেতে আগে এই লিঙ্কে ক্লিক করেন:**\n\n"
                f"👉 [এখানে ক্লিক করুন]({VERIFY_URL})\n\n"
                "লিঙ্কে যাওয়া শেষ হলে নিচের **'আমি ক্লিক করেছি'** বাটনে চাপ দিন।",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            return
        else:
            await message.reply_text("❌ ফাইলটি পাওয়া যায়নি অথবা লিঙ্কটির মেয়াদ শেষ হয়ে গেছে।")
            return

    # সাধারণ স্টার্ট মেনু
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload File", callback_data="upload_mode")]
    ])
    await message.reply_text(
        f"👋 হ্যালো **{message.from_user.first_name}**!\n\n"
        "এটি একটি ফাইল শেয়ারিং বট। আপনি এখানে ফাইল আপলোড করে শেয়ারেবল লিঙ্ক তৈরি করতে পারবেন।",
        reply_markup=keyboard
    )

# বাটন কলব্যাক হ্যান্ডলার
@bot.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data

    if data == "upload_mode":
        user_states[query.from_user.id] = "waiting_for_file"
        await query.message.edit_text(
            "📥 এখন যেকোনো ভিডিও, অডিও, ডকুমেন্ট বা ছবি এখানে পাঠান। আমি একটি শেয়ার লিঙ্ক তৈরি করে দেব।"
        )
        await query.answer()

    elif data.startswith("verify_"):
        unique_id = data.split("_")[1]
        
        if unique_id in file_database:
            file_info = file_database[unique_id]
            file_id = file_info["file_id"]
            file_type = file_info["type"]
            caption = file_info.get("caption", "Here is your file!")

            await query.answer("ভেরিফিকেশন সফল! ফাইল পাঠানো হচ্ছে...", show_alert=False)

            # ফাইলের ধরন অনুযায়ী সেন্ড করা
            if file_type == "video":
                await client.send_video(query.from_user.id, video=file_id, caption=caption)
            elif file_type == "document":
                await client.send_document(query.from_user.id, document=file_id, caption=caption)
            elif file_type == "photo":
                await client.send_photo(query.from_user.id, photo=file_id, caption=caption)
            elif file_type == "audio":
                await client.send_audio(query.from_user.id, audio=file_id, caption=caption)
        else:
            await query.answer("ফাইলটি আর নেই!", show_alert=True)

# ফাইল রিসিভ ও লিঙ্ক জেনারেটর
@bot.on_message((filters.video | filters.document | filters.photo | filters.audio) & filters.private)
async def handle_incoming_file(client: Client, message: Message):
    user_id = message.from_user.id
    
    # ফাইল টাইপ এবং ফাইল আইডি চিহ্নিত করা
    file_id = None
    file_type = None

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.photo:
        file_id = message.photo.file_id
        file_type = "photo"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"

    if not file_id:
        return

    # ইউনিক কি জেনারেট এবং ডাটাবেসে সেভ
    unique_id = generate_random_id()
    file_database[unique_id] = {
        "file_id": file_id,
        "type": file_type,
        "caption": message.caption or ""
    }

    # বটের ইউজারনেম বের করা
    bot_info = await client.get_me()
    share_link = f"https://t.me/{bot_info.username}?start={unique_id}"

    # মেসেজের ভেতরে লিঙ্কটি ক্লিক করলে যাতে স্বয়ংক্রিয় কপি হয় (ক্লিক টু কপি মনোটাইপ টেক্সট)
    response_text = (
        "✅ **আপনার ফাইলটি সংরক্ষিত হয়েছে!**\n\n"
        "🔗 **শেয়ার লিঙ্ক (নিচের কোডে ক্লিক করলে কপি হবে):**\n"
        f"`{share_link}`\n\n"
        "যেকোনো ব্যবহারকারী এই লিঙ্কে গেলে আগে ভেরিফিকেশন লিঙ্ক সম্পন্ন করতে বলা হবে।"
    )

    await message.reply_text(
        text=response_text,
        disable_web_page_preview=True
    )

    # আপলোড স্টেট ক্লিয়ার করা
    user_states.pop(user_id, None)

# --- রান স্ক্রিপ্ট ---
if __name__ == "__main__":
    # ব্যাকগ্রাউন্ড থ্রেডে Flask রান করা (Render পোর্ট বাইন্ডের জন্য)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # বট শুরু
    bot.run()
