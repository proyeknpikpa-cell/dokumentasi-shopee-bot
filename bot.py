import os
from datetime import datetime
import cloudinary
import cloudinary.uploader

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ======================
# 🔐 ENV (RAILWAY)
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

# ======================
# ☁️ CLOUDINARY CONFIG
# ======================
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

# ======================
# 📊 GOOGLE SHEET SETUP
# ======================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# file ini WAJIB kamu upload ke Railway
creds = Credentials.from_service_account_file("credentials.json", scopes=scope)
client = gspread.authorize(creds)

sheet = client.open("Proyek_NPI").sheet1


def save_to_sheet(date, time, month, caption, folder, url):
    sheet.append_row([
        date,
        time,
        month,
        caption,
        folder,
        url
    ])

# ======================
# 📷 HANDLE FOTO
# ======================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message

        # 🕒 waktu telegram
        msg_time = message.date

        date = msg_time.strftime("%Y-%m-%d")
        time = msg_time.strftime("%H:%M:%S")
        month = msg_time.strftime("%B %Y")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")

        # 📁 folder per hari
        folder_name = f"Proyek_NPI/{date}"

        # 🏷️ caption logic
        caption = message.caption
        if caption and caption.strip():
            clean_caption = caption.strip().replace(" ", "_")
            filename = f"{clean_caption}_{timestamp}.jpg"
        else:
            caption = "-"
            filename = f"tanpa_keterangan_{timestamp}.jpg"

        # 📥 download file telegram
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        file_path = f"/tmp/{filename}"
        await file.download_to_drive(file_path)

        # ☁️ upload cloudinary
        result = cloudinary.uploader.upload(
            file_path,
            folder=folder_name,
            public_id=filename.replace(".jpg", ""),
            resource_type="image"
        )

        url = result["secure_url"]

        # 📊 save ke google sheet
        save_to_sheet(
            date,
            time,
            month,
            caption,
            folder_name,
            url
        )

        # 📤 reply ke telegram
        await message.reply_text(
            f"✅ BERHASIL UPLOAD\n\n"
            f"📁 Folder: {folder_name}\n"
            f"📄 File: {filename}\n"
            f"🔗 {url}"
        )

    except Exception as e:
        await message.reply_text(f"❌ ERROR: {str(e)}")


# ======================
# 🚀 MAIN BOT
# ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Bot berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
