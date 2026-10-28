import os
import sqlite3
import secrets
import string
import threading
from flask import Flask
import telebot
from telebot import types

# --- কনফিগারেশন ---
# Render Environment Variables থেকে টোকেন নেবে
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
VERIFY_URL = "https://urlbit.pro/wVLnd"
DB_NAME = "files.db"

# টেলিগ্রাম বট ক্লায়েন্ট
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

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

# --- Flask Server (Render Port Binding & Health Check) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running smoothly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- Bot Command & Message Handlers ---

# /start হ্যান্ডলার
@bot.message_handler(commands=['start'])
def handle_start(message):
    text_data = message.text.split()
    
    # ইউজার যদি শেয়ার লিঙ্ক দিয়ে আসে (/start <unique_id>)
    if len(text_data) > 1:
        unique_id = text_data[1]
        file_info = get_file(unique_id)
        
        if file_info:
            markup = types.InlineKeyboardMarkup()
            btn_link = types.InlineKeyboardButton("🔗 এই লিঙ্কে ক্লিক করুন", url=VERIFY_URL)
            btn_verify = types.InlineKeyboardButton("✅ আমি ক্লিক করেছি (ফাইল দিন)", callback_data=f"verify_{unique_id}")
            markup.add(btn_link)
            markup.add(btn_verify)
            
            bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "⚠️ **ভিডিও বা ফাইলটি পেতে নিচের লিঙ্কে ক্লিক করেন:**\n\n"
                    f"👉 [এখানে ক্লিক করুন]({VERIFY_URL})\n\n"
                    "লিঙ্কে যাওয়া শেষ হলে নিচের **'আমি ক্লিক করেছি'** বাটনে চাপ দিন।"
                ),
                reply_markup=markup,
                disable_web_page_preview=True
            )
            return
        else:
            bot.send_message(message.chat.id, "❌ ফাইলটি খুঁজে পাওয়া যায়নি অথবা লিঙ্কটির মেয়াদ শেষ।")
            return

    # সাধারণ স্টার্ট মেনু
    markup = types.InlineKeyboardMarkup()
    btn_upload = types.InlineKeyboardButton("📤 Upload File", callback_data="upload_mode")
    markup.add(btn_upload)

    bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"👋 হ্যালো **{message.from_user.first_name}**!\n\n"
            "ফাইল শেয়ার করার জন্য নিচের **Upload File** বাটনে চাপ দিন অথবা সরাসরি যেকোনো ভিডিও/ছবি/ডকুমেন্ট এখানে সেন্ড করুন।"
        ),
        reply_markup=markup
    )

# বাটন ক্লিক হ্যান্ডলার
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data == "upload_mode":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📥 এখন যেকোনো ভিডিও, ছবি বা ফাইল এখানে পাঠান। সাথে সাথে শেয়ার লিঙ্ক পেয়ে যাবেন।"
        )

    elif call.data.startswith("verify_"):
        unique_id = call.data.split("_")[1]
        file_info = get_file(unique_id)

        if file_info:
            file_id = file_info["file_id"]
            file_type = file_info["type"]
            caption = file_info.get("caption") or ""

            bot.answer_callback_query(call.id, text="ভেরিফিকেশন সফল! ফাইল পাঠানো হচ্ছে...")

            if file_type == "video":
                bot.send_video(call.message.chat.id, file_id, caption=caption)
            elif file_type == "document":
                bot.send_document(call.message.chat.id, file_id, caption=caption)
            elif file_type == "photo":
                bot.send_photo(call.message.chat.id, file_id, caption=caption)
            elif file_type == "audio":
                bot.send_audio(call.message.chat.id, file_id, caption=caption)
        else:
            bot.answer_callback_query(call.id, text="ফাইলটি ডাটাবেসে নেই!", show_alert=True)

# ফাইল রিসিভ ও শেয়ার লিঙ্ক তৈরি
@bot.message_handler(content_types=['video', 'document', 'photo', 'audio'])
def handle_files(message):
    file_id = None
    file_type = None

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"

    if not file_id:
        return

    unique_id = generate_random_id()
    caption = message.caption or ""

    save_file(unique_id, file_id, file_type, caption)

    bot_info = bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start={unique_id}"

    response_text = (
        "✅ **আপনার ফাইলটি সেভ হয়েছে!**\n\n"
        "🔗 **শেয়ার লিঙ্ক (নিচের কোডে ক্লিক করলেই কপি হবে):**\n"
        f"`{share_link}`\n\n"
        "এই লিঙ্ক যাকে দেবেন সে ক্লিক করলে প্রথমে ভেরিফিকেশন লিঙ্ক দেখতে পাবে।"
    )

    bot.reply_to(message, response_text, disable_web_page_preview=True)

# --- মূল এক্সিকিউশন ---
if __name__ == "__main__":
    init_db()

    # Flask ব্যাকগ্রাউন্ড থ্রেডে রান
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print(">>> Flask server is running.")
    bot_info = bot.get_me()
    print(f">>> Telegram Bot is ONLINE: @{bot_info.username}")

    # কোনো পেন্ডিং ওয়েবহুক থাকলে ড্রপ করে ফ্রেশ পোলিং চালু
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
