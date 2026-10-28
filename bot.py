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
CHANNEL_LINK = "https://t.me/+L97S6UnnMdg3ZTE1"
DB_NAME = "files.db"

ADMIN_ID = 5140546628

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ইউজার ট্র্যাকার
verification_tracker = {}

# --- ডাটাবেস হ্যান্ডলার (SQLite3) ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # ফাইল টেবিল
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
    
    # ইউজার ট্র্যাকিং টেবিল (অ্যাক্টিভ ইউজার ও ব্রডকাস্টের জন্য)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            last_active REAL NOT NULL
        )
    """)
    
    # বটের সেটিংস টেবিল
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wait_seconds', '10')")
    
    conn.commit()
    conn.close()

def log_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (user_id, last_active) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET last_active = ?",
        (user_id, time.time(), time.time())
    )
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # টোটাল ইউজার
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # অ্যাক্টিভ ইউজার (গত ২৪ ঘণ্টায় সক্রিয়)
    one_day_ago = time.time() - 86400
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active >= ?", (one_day_ago,))
    active_users = cursor.fetchone()[0]
    
    # টোটাল ফাইল
    cursor.execute("SELECT COUNT(*) FROM files")
    total_files = cursor.fetchone()[0]
    
    conn.close()
    return total_users, active_users, total_files

def get_all_user_ids():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_wait_seconds():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'wait_seconds'")
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else 10

def set_wait_seconds(seconds):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'wait_seconds'", (str(seconds),))
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

# --- Flask Server ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running perfectly!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def main_menu_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_upload = types.InlineKeyboardButton("📤 Upload File", callback_data="upload_mode")
    btn_my_files = types.InlineKeyboardButton("📁 My Files", callback_data="my_files")
    markup.add(btn_upload, btn_my_files)
    return markup

# --- অ্যাডমিন প্যানেল (/ad) ---
@bot.message_handler(commands=['ad', 'admin'])
def handle_admin(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⛔ আপনার এই প্যানেল ব্যবহারের অনুমতি নেই।")
        return

    current_wait = get_wait_seconds()
    total_users, active_users, total_files = get_stats()
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    btn_5 = types.InlineKeyboardButton("5s", callback_data="set_time_5")
    btn_10 = types.InlineKeyboardButton("10s", callback_data="set_time_10")
    btn_15 = types.InlineKeyboardButton("15s", callback_data="set_time_15")
    btn_20 = types.InlineKeyboardButton("20s", callback_data="set_time_20")
    btn_30 = types.InlineKeyboardButton("30s", callback_data="set_time_30")
    btn_custom = types.InlineKeyboardButton("✏️ Custom Time", callback_data="set_custom_time")
    
    btn_broadcast = types.InlineKeyboardButton("📢 Send Broadcast", callback_data="start_broadcast")
    btn_refresh = types.InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_admin")
    
    markup.add(btn_5, btn_10, btn_15)
    markup.add(btn_20, btn_30, btn_custom)
    markup.add(btn_broadcast)
    markup.add(btn_refresh)

    admin_text = (
        "⚙️ **Admin Control Panel**\n\n"
        f"👥 **মোট ইউজার:** `{total_users}` জন\n"
        f"🟢 **সক্রিয় ইউজার (২৪ ঘণ্টা):** `{active_users}` জন\n"
        f"📂 **মোট আপলোড করা ফাইল:** `{total_files}` টি\n"
        f"⏱ **বর্তমান ওয়েটিং টাইম:** `{current_wait}` সেকেন্ড\n\n"
        "টাইম পরিবর্তন বা ব্রডকাস্ট পাঠাতে নিচের বাটন ব্যবহার করুন:"
    )
    bot.send_message(message.chat.id, admin_text, reply_markup=markup)

# কাস্টম টাইম প্রসেসর
def process_custom_time(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_seconds = int(message.text.strip())
        if new_seconds < 0:
            bot.reply_to(message, "❌ সময় ০ বা তার বেশি হতে হবে।")
            return
        
        set_wait_seconds(new_seconds)
        bot.reply_to(message, f"✅ সফলভাবে সময় পরিবর্তন করে **{new_seconds}** সেকেন্ড নির্ধারণ করা হয়েছে!")
    except ValueError:
        bot.reply_to(message, "❌ অবৈধ ইনপুট! শুধু সংখ্যা (যেমন: 15, 25) লিখুন।")

# ব্রডকাস্ট এক্সিকিউটর
def process_broadcast(message):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text and message.text.lower() == "/cancel":
        bot.reply_to(message, "❌ ব্রডকাস্ট বাতিল করা হয়েছে।")
        return

    users = get_all_user_ids()
    if not users:
        bot.reply_to(message, "📭 ব্রডকাস্ট করার মতো কোনো ইউজার পাওয়া যায়নি।")
        return

    status_msg = bot.reply_to(message, f"🚀 ব্রডকাস্ট শুরু হচ্ছে... মোট ইউজার: {len(users)}")
    
    success = 0
    blocked = 0

    for u_id in users:
        try:
            bot.copy_message(chat_id=u_id, from_chat_id=message.chat.id, message_id=message.message_id)
            success += 1
            time.sleep(0.04)  # টেলিগ্রাম রেট লিমিট এড়াতে
        except Exception:
            blocked += 1

    report_text = (
        "📢 **ব্রডকাস্ট সম্পন্ন হয়েছে!**\n\n"
        f"✅ **সফলভাবে গেছে:** `{success}` জনের কাছে\n"
        f"❌ **ফেইল্ড/ব্লক করেছে:** `{blocked}` জন"
    )
    bot.edit_message_text(chat_id=message.chat.id, message_id=status_msg.message_id, text=report_text)

# --- /start কমান্ড হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    log_user(user_id)  # ইউজার ডাটাবেসে সেভ ও অ্যাক্টিভ টাইম রেকর্ড
    
    text_data = message.text.split()
    
    # শেয়ার লিঙ্ক হ্যান্ডলিং
    if len(text_data) > 1:
        unique_id = text_data[1]
        file_info = get_file(unique_id)
        
        if file_info:
            current_wait = get_wait_seconds()
            verification_tracker[(user_id, unique_id)] = time.time()
            
            markup = types.InlineKeyboardMarkup()
            btn_channel = types.InlineKeyboardButton("📢 Step 1: চ্যানেলে জয়েন করুন", url=CHANNEL_LINK)
            btn_link = types.InlineKeyboardButton("🔗 Step 2: এই লিঙ্কে যান", url=VERIFY_URL)
            btn_verify = types.InlineKeyboardButton(f"✅ {current_wait} সেকেন্ড পর ভিডিও নিন", callback_data=f"verify_{unique_id}")
            
            markup.add(btn_channel)
            markup.add(btn_link)
            markup.add(btn_verify)
            
            bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "⚠️ **ভিডিও পেতে নিচের ধাপগুলো সম্পন্ন করুন:**\n\n"
                    f"১. প্রথমে [আমাদের চ্যানেলে জয়েন করুন]({CHANNEL_LINK})\n"
                    f"২. এরপর [এই লিঙ্কে ক্লিক করুন]({VERIFY_URL}) এবং কমপক্ষে **{current_wait} সেকেন্ড** অপেক্ষা করুন।\n"
                    f"৩. সময় শেষ হলে নিচে **'{current_wait} সেকেন্ড পর ভিডিও নিন'** বাটনে চাপ দিন।",
                ),
                reply_markup=markup,
                disable_web_page_preview=True
            )
            return
        else:
            bot.send_message(message.chat.id, "❌ ফাইলটি খুঁজে পাওয়া যায়নি অথবা লিঙ্কটির মেয়াদ শেষ।")
            return

    # হোম মেনু
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
    
    log_user(user_id)

    # অ্যাডমিন রিফ্রেশ
    if data == "refresh_admin":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "অনুমতি নেই!", show_alert=True)
            return
        bot.answer_callback_query(call.id, "স্ট্যাটাস আপডেট করা হয়েছে!")
        current_wait = get_wait_seconds()
        total_users, active_users, total_files = get_stats()
        
        markup = call.message.reply_markup
        admin_text = (
            "⚙️ **Admin Control Panel**\n\n"
            f"👥 **মোট ইউজার:** `{total_users}` জন\n"
            f"🟢 **সক্রিয় ইউজার (২৪ ঘণ্টা):** `{active_users}` জন\n"
            f"📂 **মোট আপলোড করা ফাইল:** `{total_files}` টি\n"
            f"⏱ **বর্তমান ওয়েটিং টাইম:** `{current_wait}` সেকেন্ড\n\n"
            "টাইম পরিবর্তন বা ব্রডকাস্ট পাঠাতে নিচের বাটন ব্যবহার করুন:"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=admin_text, reply_markup=markup)
        return

    # ব্রডকাস্ট শুরু
    elif data == "start_broadcast":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "অনুমতি নেই!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            chat_id,
            "📝 **ব্রডকাস্ট করতে চাওয়া মেসেজটি এখানে সেন্ড করুন:**\n\n"
            "(টেক্সট, ছবি, ভিডিও বা ফরোয়ার্ড করা মেসেজ দিতে পারেন। বাতিল করতে `/cancel` লিখুন)"
        )
        bot.register_next_step_handler(msg, process_broadcast)
        return

    # টাইম বাটন
    elif data.startswith("set_time_"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "অনুমতি নেই!", show_alert=True)
            return
        new_time = int(data.split("_")[2])
        set_wait_seconds(new_time)
        bot.answer_callback_query(call.id, f"টাইম {new_time} সেকেন্ড করা হয়েছে!", show_alert=True)
        
        total_users, active_users, total_files = get_stats()
        admin_text = (
            "⚙️ **Admin Control Panel**\n\n"
            f"👥 **মোট ইউজার:** `{total_users}` জন\n"
            f"🟢 **সক্রিয় ইউজার (২৪ ঘণ্টা):** `{active_users}` জন\n"
            f"📂 **মোট আপলোড করা ফাইল:** `{total_files}` টি\n"
            f"⏱ **বর্তমান ওয়েটিং টাইম:** `{new_time}` সেকেন্ড\n\n"
            f"✅ **নতুন সময় সফলভাবে সেট করা হয়েছে!**"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=admin_text, reply_markup=call.message.reply_markup)
        return

    # কাস্টম টাইম
    elif data == "set_custom_time":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "অনুমতি নেই!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "⌨️ আপনি কত সেকেন্ড সেট করতে চান? শুধু সংখ্যাটি লিখে পাঠান (যেমন: 25):")
        bot.register_next_step_handler(msg, process_custom_time)
        return

    # আপলোড মোড
    elif data == "upload_mode":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"))
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📥 এখন যেকোনো ভিডিও, ছবি, অডিও বা ফাইল এখানে পাঠান। সাথে সাথে শেয়ার লিঙ্ক পেয়ে যাবেন।",
            reply_markup=markup
        )

    # মেনুতে ব্যাক
    elif data == "back_to_menu":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="🏠 **মেইন মেনু:**\nএকটি অপশন বেছে নিন:",
            reply_markup=main_menu_keyboard()
        )

    # মাই ফাইলস
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

    # ফাইল ম্যানেজ
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

    # ফাইল ডিলিট
    elif data.startswith("del_"):
        unique_id = data.split("_")[1]
        success = delete_user_file(unique_id, user_id)
        
        if success:
            bot.answer_callback_query(call.id, "✅ ফাইলটি সফলভাবে ডিলিট করা হয়েছে!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ ফাইলটি ডিলিট করা সম্ভব হয়নি।", show_alert=True)

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

    # ভেরিফিকেশন ও ফাইল ডেলিভারি
    elif data.startswith("verify_"):
        unique_id = data.split("_")[1]
        file_info = get_file(unique_id)

        if not file_info:
            bot.answer_callback_query(call.id, "ফাইলটি আর নেই!", show_alert=True)
            return

        current_wait = get_wait_seconds()
        start_time = verification_tracker.get((user_id, unique_id))
        now = time.time()

        if not start_time:
            verification_tracker[(user_id, unique_id)] = now
            bot.answer_callback_query(
                call.id,
                f"⏳ অনুগ্রহ করে ধাপগুলো সম্পন্ন করে {current_wait} সেকেন্ড অপেক্ষা করুন!",
                show_alert=True
            )
            return

        elapsed = now - start_time
        if elapsed < current_wait:
            remaining = int(current_wait - elapsed)
            bot.answer_callback_query(
                call.id,
                f"⏳ দয়া করে আরও {remaining} সেকেন্ড অপেক্ষা করে আবার চাপ দিন!",
                show_alert=True
            )
            return

        bot.answer_callback_query(call.id, "✅ ভেরিফিকেশন সফল! ভিডিও পাঠানো হচ্ছে...")

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

        verification_tracker.pop((user_id, unique_id), None)

# --- ফাইল গ্রহণ ও সংরক্ষণ ---
@bot.message_handler(content_types=['video', 'document', 'photo', 'audio'])
def handle_files(message):
    user_id = message.from_user.id
    log_user(user_id)
    
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
        "যেকেউ এই লিঙ্কে ক্লিক করলে চ্যানেল জয়েন ও লিঙ্কে অপেক্ষার পর ভিডিও পাবে।"
    )

    bot.reply_to(message, response_text, reply_markup=markup, disable_web_page_preview=True)

# --- মূল এক্সিকিউশন ---
if __name__ == "__main__":
    init_db()

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print(">>> Flask server running.")
    bot_info = bot.get_me()
    print(f">>> Telegram Bot ONLINE: @{bot_info.username}")

    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
