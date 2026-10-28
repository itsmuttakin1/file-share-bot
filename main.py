import os
import sqlite3
import secrets
import string
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# --- কনফিগারেশন ---
# Render Environment এ শুধু BOT_TOKEN দিলেই হবে
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
VERIFY_URL = "https://urlbit.pro/wVLnd"
DB_NAME = "files.db"

# --- ডাটাবেস হ্যান্ডলার (SQLite) ---
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

# --- Flask Server (Render Port Binding) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- Telegram Bot Handlers ---

# /start কমান্ড হ্যান্ডলার
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # ইউজার যদি শেয়ার করা লিঙ্ক দিয়ে আসে (/start <unique_id>)
    if args and len(args) > 0:
        unique_id = args[0]
        file_info = get_file(unique_id)

        if file_info:
            keyboard = [
                [InlineKeyboardButton("🔗 এই লিঙ্কে ক্লিক করুন", url=VERIFY_URL)],
                [InlineKeyboardButton("✅ আমি ক্লিক করেছি (ফাইল দিন)", callback_data=f"verify_{unique_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "⚠️ **ভিডিও বা ফাইলটি পেতে নিচের লিঙ্কে ক্লিক করেন:**\n\n"
                f"👉 [এখানে ক্লিক করুন]({VERIFY_URL})\n\n"
                "লিঙ্কে যাওয়া শেষ হলে নিচের **'আমি ক্লিক করেছি'** বাটনে চাপ দিন।",
                reply_markup=reply_markup,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            return
        else:
            await update.message.reply_text("❌ ফাইলটি খুঁজে পাওয়া যায়নি বা লিঙ্কটি অবৈধ।")
            return

    # সাধারণ স্টার্ট মেনু
    keyboard = [
        [InlineKeyboardButton("📤 Upload File", callback_data="upload_mode")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 হ্যালো **{user.first_name}**!\n\n"
        "ফাইল শেয়ার করার জন্য নিচের **Upload File** বাটনে চাপ দিন অথবা সরাসরি যেকোনো ভিডিও/ফাইল এখানে পাঠান।",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# বাটন ক্লিক হ্যান্ডলার
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "upload_mode":
        await query.edit_message_text(
            "📥 এখন যেকোনো ভিডিও, অডিও, ডকুমেন্ট বা ছবি এখানে পাঠান। সাথে সাথে শেয়ার লিঙ্ক পেয়ে যাবেন।"
        )

    elif data.startswith("verify_"):
        unique_id = data.split("_")[1]
        file_info = get_file(unique_id)

        if file_info:
            file_id = file_info["file_id"]
            file_type = file_info["type"]
            caption = file_info.get("caption") or ""

            chat_id = query.from_user.id

            if file_type == "video":
                await context.bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
            elif file_type == "document":
                await context.bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
            elif file_type == "photo":
                await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
            elif file_type == "audio":
                await context.bot.send_audio(chat_id=chat_id, audio=file_id, caption=caption)
        else:
            await query.edit_message_text("❌ ফাইলটি আর ডাটাবেসে নেই!")

# ফাইল রিসিভ ও শেয়ার লিঙ্ক তৈরি
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
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

    # ডাটাবেসে ফাইল সংরক্ষণ
    save_file(unique_id, file_id, file_type, caption)

    # বটের ইউজারনেম দিয়ে লিঙ্ক তৈরি
    bot_info = await context.bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start={unique_id}"

    response_text = (
        "✅ **আপনার ফাইলটি সেভ হয়েছে!**\n\n"
        "🔗 **শেয়ার লিঙ্ক (নিচের কোডে ক্লিক করলেই কপি হবে):**\n"
        f"`{share_link}`\n\n"
        "এই লিঙ্ক যাকে দেবেন সে লিঙ্কে ক্লিক করলে আগে ভেরিফিকেশন লিঙ্ক দেখতে পাবে।"
    )

    await message.reply_text(
        text=response_text,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# --- মূল রানার ---
if __name__ == "__main__":
    init_db()

    # Flask ব্যাকগ্রাউন্ডে চালু
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print(">>> Flask server started.")
    print(">>> Starting Telegram Bot...")

    # Telegram Application তৈরি ও রান
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.ALL | filters.PHOTO | filters.AUDIO,
            handle_file
        )
    )

    application.run_polling()
