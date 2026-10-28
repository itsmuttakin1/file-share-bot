import os
import sys
import asyncio
import sqlite3
import secrets
import string
import threading
from flask import Flask

# --- ফিক্স: Python 3.12/3.14 এ Pyrogram ইমপোর্টের আগেই ইভেন্ট লুপ নিশ্চিত করা ---
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery
)

# --- কনফিগারেশন ---
# Render Environment Variables থেকে মান নেবে
API_ID = int(os.environ.get("API_ID", "1234567"))
API_HASH = os.environ.get("API_HASH", "your_api_hash_here")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token_here")

# রিডাইরেক্ট বা ট্র্যাকিং লিঙ্ক
VERIFY_URL = "https://urlbit.pro/wVLnd"
DB_NAME = "files.db"

# --- ডাটাবেস হ্যান্ডলার (SQLite3) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            unique_id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_file(unique_id, file_id, file_type, caption):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO files (unique_id, file_id, file_type, caption) VALUES (?, ?, ?, ?)",
        (unique_id, file_id, file_type, caption)
    )
    conn.commit()
    conn.close()

def get_file(unique_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_type, caption FROM files WHERE unique_id = ?", (unique_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"file_id": row[0], "type": row[1], "caption": row[2]}
    return None

def generate_random_id(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

# --- Flask Server (Render Keep-Alive & Port Binding) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

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

# /start হ্যান্ডলার
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    text_parts = message.text.split()

    # ব্যবহারকারী শেয়ার লিঙ্ক নিয়ে এলে (/start <unique_id>)
    if len(text_parts) > 1:
        unique_id = text_parts[1]
        file_info = get_file(unique_id)

        if file_info:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 এই লিঙ্কে ক্লিক করুন", url=VERIFY_URL)],
                [InlineKeyboardButton("✅ আমি ক্লিক করেছি (ফাইল দিন)", callback_data=f"verify_{unique_id}")]
            ])
            await message.reply_text(
                "⚠️ **ভিডিও বা ফাইলটি পেতে নিচের লিঙ্কে প্রবেশ করুন:**\n\n"
                f"👉 [এখানে ক্লিক করুন]({VERIFY_URL})\n\n"
                "লিঙ্কে যাওয়া শেষ হলে নিচের **'আমি ক্লিক করেছি'** বাটনে চাপ দিন।",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
            return
        else:
            await message.reply_text("❌ ফাইলটি খুঁজে পাওয়া যায়নি বা এটি মুছে ফেলা হয়েছে।")
            return

    # সাধারণ হোম মেনু
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload File", callback_data="upload_mode")]
    ])
    await message.reply_text(
        f"👋 হ্যালো **{message.from_user.first_name}**!\n\n"
        "ফাইল শেয়ার করার জন্য নিচের **Upload File** বাটনে চাপ দিন অথবা সরাসরি যেকোনো ফাইল এখানে পাঠান।",
        reply_markup=keyboard
    )

# বাটন হ্যান্ডলার
@bot.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data

    if data == "upload_mode":
        await query.message.edit_text(
            "📥 এখন যেকোনো ভিডিও, অডিও, ডকুমেন্ট বা ছবি এখানে সেন্ড করুন। সঙ্গে সঙ্গে শেয়ার লিঙ্ক পেয়ে যাবেন।"
        )
        await query.answer()

    elif data.startswith("verify_"):
        unique_id = data.split("_")[1]
        file_info = get_file(unique_id)

        if file_info:
            file_id = file_info["file_id"]
            file_type = file_info["type"]
            caption = file_info.get("caption") or ""

            await query.answer("ভেরিফিকেশন সম্পন্ন! ফাইল পাঠানো হচ্ছে...", show_alert=False)

            if file_type == "video":
                await client.send_video(query.from_user.id, video=file_id, caption=caption)
            elif file_type == "document":
                await client.send_document(query.from_user.id, document=file_id, caption=caption)
            elif file_type == "photo":
                await client.send_photo(query.from_user.id, photo=file_id, caption=caption)
            elif file_type == "audio":
                await client.send_audio(query.from_user.id, audio=file_id, caption=caption)
        else:
            await query.answer("ফাইলটি আর ডাটাবেসে নেই!", show_alert=True)

# ফাইল রিসিভ ও শেয়ার লিঙ্ক তৈরি
@bot.on_message((filters.video | filters.document | filters.photo | filters.audio) & filters.private)
async def handle_incoming_file(client: Client, message: Message):
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

    unique_id = generate_random_id()
    caption = message.caption or ""

    # ডাটাবেসে ফাইল সেভ
    save_file(unique_id, file_id, file_type, caption)

    # বটের ইউজারনেম দিয়ে লিঙ্ক প্রস্তুত
    bot_info = await client.get_me()
    share_link = f"https://t.me/{bot_info.username}?start={unique_id}"

    # কোড ব্লক (``) ব্যবহারের ফলে টেলিগ্রামে ট্যাপ করলেই পুরো লিঙ্কটি কপি হয়ে যাবে
    response_text = (
        "✅ **আপনার ফাইলটি সংরক্ষিত হয়েছে!**\n\n"
        "🔗 **শেয়ার লিঙ্ক (নিচের কোডে ক্লিক করলেই কপি হবে):**\n"
        f"`{share_link}`\n\n"
        "এই লিঙ্ক যাকে দেবেন সে লিঙ্কে ক্লিক করলে আগে ভেরিফিকেশন পেজ দেখতে পাবে।"
    )

    await message.reply_text(
        text=response_text,
        disable_web_page_preview=True
    )

# --- মেইন এক্সিকিউশন ---
if __name__ == "__main__":
    # ডাটাবেস টেবিল তৈরি
    init_db()

    # Flask সার্ভার ব্যাকগ্রাউন্ড থ্রেডে রান
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Pyrogram ক্লায়েন্ট চালু
    bot.run()
