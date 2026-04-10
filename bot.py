import os
from datetime import datetime
import cloudinary
import cloudinary.uploader

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# ======================
# 🔐 ENV
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CLIENT_EMAIL = os.getenv("GOOGLE_CLIENT_EMAIL")
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY")

OWNER_USERNAME = os.getenv("OWNER_USERNAME")  # <-- username kamu

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

# ======================
# ☁️ CLOUDINARY
# ======================
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

# ======================
# 📊 GOOGLE SHEET
# ======================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

private_key = GOOGLE_PRIVATE_KEY.replace("\\n", "\n")

creds = Credentials.from_service_account_info({
    "type": "service_account",
    "client_email": GOOGLE_CLIENT_EMAIL,
    "private_key": private_key,
    "token_uri": "https://oauth2.googleapis.com/token"
}, scopes=scope)

client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Proyek_NPI")

# ======================
# 📊 SAVE SHEET
# ======================
def save_to_sheet(date, time, caption, url):
    sheet.append_row([date, time, caption, url])

# ======================
# 📷 HANDLE FOTO
# ======================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        msg_time = message.date

        date = msg_time.strftime("%Y-%m-%d")
        time = msg_time.strftime("%H:%M:%S")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")

        folder_name = f"Proyek_NPI/{date}"

        caption_raw = message.caption or ""

        if caption_raw.strip():
            if "kegiatan" in caption_raw.lower():
                base_name = f"Kegiatan_{date}_{time}"
            else:
                clean = caption_raw.strip().replace(" ", "_")[:30]
                base_name = f"{clean}_{timestamp}"
            caption_final = caption_raw
        else:
            base_name = f"tanpa_keterangan_{timestamp}"
            caption_final = "-"

        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        file_path = f"/tmp/{base_name}.jpg"
        await file.download_to_drive(file_path)

        result = cloudinary.uploader.upload(
            file_path,
            folder=folder_name,
            public_id=base_name,
            overwrite=True
        )

        url = result["secure_url"]

        save_to_sheet(date, time, caption_final, url)

        await message.reply_text(
            f"✅ BERHASIL UPLOAD\n\n"
            f"📅 {date} | ⏰ {time}\n"
            f"📝 {caption_final}\n"
            f"📂 {folder_name}\n"
            f"🔗 {url}"
        )

    except Exception as e:
        await message.reply_text(f"❌ ERROR: {str(e)}")

# ======================
# 📋 /info MENU
# ======================
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Jumlah Foto Hari Ini", callback_data="jumlah")],
        [InlineKeyboardButton("👨‍💻 Developer", callback_data="dev")],
        [InlineKeyboardButton("💬 Masukan", callback_data="saran")]
    ]

    await update.message.reply_text(
        "📋 Menu Bot:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ======================
# 🎯 HANDLE BUTTON
# ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "jumlah":
        today = datetime.now().strftime("%Y-%m-%d")
        rows = sheet.get_all_values()
        count = sum(1 for r in rows if r and r[0] == today)

        await query.edit_message_text(f"📊 Hari ini ada {count} foto")

    elif data == "dev":
        await query.edit_message_text(f"👨‍💻 Developer: {OWNER_USERNAME}")

    elif data == "saran":
        await query.edit_message_text(
            "💬 Kirim saran:\n\n/saran isi pesan kamu"
        )

# ======================
# 💬 /saran
# ======================
async def saran_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = " ".join(context.args)

    if not text:
        await update.message.reply_text("❗ Tulis saran setelah /saran")
        return

    await update.message.reply_text("✅ Saran dikirim!")

    await update.message.reply_text(
        f"📩 Saran dari @{user.username}:\n\n{text}\n\n👉 {OWNER_USERNAME}"
    )

# ======================
# 🚀 MAIN
# ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("saran", saran_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot jalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
