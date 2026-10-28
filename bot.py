import os
import time
import sqlite3
import secrets
import string
import threading
from flask import Flask
import telebot
from telebot import types

# --- কনফিগারেশন ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
VERIFY_URL = "https://urlbit.pro/wVLnd"
DB_NAME = "files.db"
REQUIRED_WAIT_SECONDS = 10  # লিঙ্কে যাওয়ার পর ন্যূনতম অপেক্ষার সময়

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ইউজার কখন ভেরিফাই শুরু করেছে তা ট্র্যাকিং করার ডিকশনারি
verification_tracker = {}

# --- ডাটাবেস হ্যান্ডলার (SQLite3) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # user_id কলাম যোগ করা হয়েছে যাতে ইউজার নিজের ফাইল দেখতে পারে
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            unique_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_name TEXT,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_file(unique_id, user_id, file_id, file_type, file_name, caption):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO files (unique_id, user_id, file_id, file_type, file_name, caption) VALUES (?, ?, ?, ?, ?, ?)",
        (unique_id, user_id, file_id, file_type, file_name, caption)
    )
    conn.commit()
    conn.close()

def get_file(unique_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_type, caption, user_id FROM files WHERE unique_id = ?", (unique_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"file_id": row[0], "type": row[1], "caption": row[2], "user_id": row[3]}
    return None

def get_user_files(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT unique_id, file_type, file_name FROM files WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_user_file(unique_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM files WHERE unique_id = ? AND user_id = ?", (unique_id, user_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def generate_random_id(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

# --- Flask Server (Render Keep-Alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# মেনু তৈরির ফাংশন
def main_menu_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_upload = types.InlineKeyboardButton("📤 Upload File", callback_data="upload_mode")
    btn_my_files = types.InlineKeyboardButton("📁 My Files", callback_data="my_files")
    markup.add(btn_upload, btn_my_files)
    return markup

# --- কমান্ড হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    text_data = message.text.split()
    user_id = message.from_user.id
    
    # ইউজার যদি কোনো শেয়ার লিঙ্ক নিয়ে আসে (/start <unique_id>)
    if len(text_data) > 1:
        unique_id = text_data[1]
        file_info = get_file(unique_id)
        
        if file_info:
            # ভেরিফিকেশন শুরু হওয়ার সময় রেকর্ড করা
            verification_tracker[(user_id, unique_id)] = time.time()
            
            markup = types.InlineKeyboardMarkup()
            btn_link = types.InlineKeyboardButton("🔗 ১. এই লিঙ্কে যান", url=VERIFY_URL)
            btn_verify = types.InlineKeyboardButton("✅ ২. ১০ সেকেন্ড পর ফাইল নিন", callback_data=f"verify_{unique_id}")
            markup.add(btn_link)
            markup.add(btn_verify)
            
            bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "⚠️ **ভিডিও বা ফাইলটি পেতে নিচের নিয়মে সম্পন্ন করুন:**\n\n"
                    f"১. প্রথমে [এখানে ক্লিক করে লিঙ্কে যান]({VERIFY_URL})\n"
                    f"২. লিঙ্কে গিয়ে কমপক্ষে **{REQUIRED_WAIT_SECONDS} সেকেন্ড** অপেক্ষা করুন।\n"
                    "৩. অপেক্ষা শেষ হলে নিচের **'১০ সেকেন্ড পর ফাইল নিন'** বাটনে চাপ দিন।",
                ),
                reply_markup=markup,
                disable_web_page_preview=True
            )
            return
        else:
            bot.send_message(message.chat.id, "❌ ফাইলটি খুঁজে পাওয়া যায়নি অথবা লিঙ্কটির মেয়াদ শেষ।")
            return

    # সাধারণ হোম মেনু
    bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"👋 হ্যালো **{message.from_user.first_name}**!\n\n"
            "ফাইল শেয়ারিং বটে আপনাকে স্বাগতম। আপনি সহজেই ফাইল আপলোড করে শেয়ার লিঙ্ক তৈরি ও ম্যানেজ করতে পারবেন।"
        ),
        reply_markup=main_menu_keyboard()
    )

# --- বাটন কলব্যাক হ্যান্ডলার ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    # ১. আপলোড মোড
    if data == "upload_mode":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"))
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📥 এখন যেকোনো ভিডিও, ছবি, অডিও বা ফাইল এখানে পাঠান। সাথে সাথে শেয়ার লিঙ্ক পেয়ে যাবেন।",
            reply_markup=markup
        )

    # ২. মেনুতে ব্যাক
    elif data == "back_to_menu":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="🏠 **মেইন মেনু:**\nএকটি অপশন বেছে নিন:",
            reply_markup=main_menu_keyboard()
        )

    # ৩. মাই ফাইলস লিস্ট
    elif data == "my_files":
        bot.answer_callback_query(call.id)
        files = get_user_files(user_id)
        
        if not files:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📤 Upload File Now", callback_data="upload_mode"))
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu"))
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="📭 আপনি এখনও কোনো ফাইল আপলোড করেননি।",
                reply_markup=markup
            )
            return

        markup = types.InlineKeyboardMarkup()
        for u_id, f_type, f_name in files:
            btn_title = f"{f_type.capitalize()}: {f_name[:20]}"
            markup.add(types.InlineKeyboardButton(btn_title, callback_data=f"manage_{u_id}"))
        
        markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📁 **আপনার আপলোড করা ফাইলসমূহ:**\nযেকোনো ফাইলের বিস্তারিত ও লিঙ্ক দেখতে নামের ওপর চাপ দিন:",
            reply_markup=markup
        )

    # ৪. নির্দিষ্ট ফাইল ম্যানেজ করা (লিঙ্ক কপি ও ডিলিট বাটন)
    elif data.startswith("manage_"):
        unique_id = data.split("_")[1]
        file_info = get_file(unique_id)

        if not file_info:
            bot.answer_callback_query(call.id, "ফাইলটি খুঁজে পাওয়া যায়নি!", show_alert=True)
            return

        bot_info = bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start={unique_id}"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🗑 Delete File", callback_data=f"del_{unique_id}"))
        markup.add(types.InlineKeyboardButton("🔙 Back to My Files", callback_data="my_files"))

        text = (
            f"📄 **ফাইলের বিবরণ:**\n"
            f"• **ধরন:** {file_info['type'].capitalize()}\n\n"
            f"🔗 **শেয়ার লিঙ্ক (নিচের কোডে ক্লিক করলে কপি হবে):**\n"
            f"`{share_link}`\n\n"
            "ফাইলটি মুছতে চাইলে নিচের **Delete** বাটনে চাপ দিন।"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)

    # ৫. ফাইল ডিলিট কনফার্মেশন
    elif data.startswith("del_"):
        unique_id = data.split("_")[1]
        success = delete_user_file(unique_id, user_id)
        
        if success:
            bot.answer_callback_query(call.id, "✅ ফাইলটি সফলভাবে ডিলিট করা হয়েছে!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ ফাইলটি ডিলিট করা সম্ভব হয়নি।", show_alert=True)

        # ডিলিট শেষে আবার My Files পেজ দেখানো
        files = get_user_files(user_id)
        markup = types.InlineKeyboardMarkup()
        for u_id, f_type, f_name in files:
            markup.add(types.InlineKeyboardButton(f"{f_type.capitalize()}: {f_name[:20]}", callback_data=f"manage_{u_id}"))
        markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📁 **আপনার বর্তমান ফাইলসমূহ:**",
            reply_markup=markup
        )

    # ৬. ভেরিফিকেশন ও ফাইল ডেলিভারি (১০ সেকেন্ড চেকার)
    elif data.startswith("verify_"):
        unique_id = data.split("_")[1]
        file_info = get_file(unique_id)

        if not file_info:
            bot.answer_callback_query(call.id, "ফাইলটি আর নেই!", show_alert=True)
            return

        # ইউজার কখন ভেরিফিকেশন শুরু করেছিল তা যাচাই
        start_time = verification_tracker.get((user_id, unique_id))
        current_time = time.time()

        if not start_time:
            # প্রথমবার ট্র্যাকার রেকর্ড করে ১০ সেকেন্ড কাউন্ট শুরু
            verification_tracker[(user_id, unique_id)] = current_time
            bot.answer_callback_query(
                call.id,
                f"⏳ অনুগ্রহ করে লিঙ্কে প্রবেশ করে {REQUIRED_WAIT_SECONDS} সেকেন্ড অপেক্ষা করুন!",
                show_alert=True
            )
            return

        elapsed = current_time - start_time
        if elapsed < REQUIRED_WAIT_SECONDS:
            remaining = int(REQUIRED_WAIT_SECONDS - elapsed)
            bot.answer_callback_query(
                call.id,
                f"⏳ দয়া করে আরও {remaining} সেকেন্ড অপেক্ষা করে আবার চাপ দিন!",
                show_alert=True
            )
            return

        # ১০ সেকেন্ড সফলভাবে অতিবাহিত হলে ফাইল পাঠানো
        bot.answer_callback_query(call.id, "✅ ভেরিফিকেশন সফল! ফাইল পাঠানো হচ্ছে...")

        file_id = file_info["file_id"]
        file_type = file_info["type"]
        caption = file_info.get("caption") or ""

        if file_type == "video":
            bot.send_video(chat_id, file_id, caption=caption)
        elif file_type == "document":
            bot.send_document(chat_id, file_id, caption=caption)
        elif file_type == "photo":
            bot.send_photo(chat_id, file_id, caption=caption)
        elif file_type == "audio":
            bot.send_audio(chat_id, file_id, caption=caption)

        # ট্র্যাকার থেকে মুছে ফেলা
        verification_tracker.pop((user_id, unique_id), None)

# --- ফাইল গ্রহণ ও সংরক্ষণ ---
@bot.message_handler(content_types=['video', 'document', 'photo', 'audio'])
def handle_files(message):
    user_id = message.from_user.id
    file_id = None
    file_type = None
    file_name = "Shared File"

    if message.video:
        file_id = message.video.file_id
        file_type = "video"
        file_name = message.video.file_name or f"Video_{secrets.token_hex(3)}"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        file_name = message.document.file_name or f"Doc_{secrets.token_hex(3)}"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
        file_name = f"Photo_{secrets.token_hex(3)}"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
        file_name = message.audio.file_name or f"Audio_{secrets.token_hex(3)}"

    if not file_id:
        return

    unique_id = generate_random_id()
    caption = message.caption or ""

    # ডাটাবেসে সেভ
    save_file(unique_id, user_id, file_id, file_type, file_name, caption)

    bot_info = bot.get_me()
    share_link = f"https://t.me/{bot_info.username}?start={unique_id}"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📁 My Files এ যান", callback_data="my_files"))

    response_text = (
        "✅ **আপনার ফাইলটি সংরক্ষিত হয়েছে!**\n\n"
        f"📂 **ফাইলের নাম:** `{file_name}`\n"
        "🔗 **শেয়ার লিঙ্ক (নিচের কোডে ক্লিক করলে কপি হবে):**\n"
        f"`{share_link}`\n\n"
        "যেকেউ এই লিঙ্কে ক্লিক করলে ১০ সেকেন্ড অপেক্ষার পর ফাইল পাবে।"
    )

    bot.reply_to(message, response_text, reply_markup=markup, disable_web_page_preview=True)

# --- মূল এক্সিকিউশন ---
if __name__ == "__main__":
    init_db()

    # Flask ব্যাকগ্রাউন্ড থ্রেড
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print(">>> Flask server is running.")
    bot_info = bot.get_me()
    print(f">>> Telegram Bot is ONLINE: @{bot_info.username}")

    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
