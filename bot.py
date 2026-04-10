import os
from datetime import datetime
import cloudinary.uploader
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ======================
# 🔐 ENV VARIABLE (WAJIB DI RAILWAY)
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan di environment variable!")

# ======================
# ☁️ CLOUDINARY CONFIG
# ======================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ======================
# 🧠 FUNCTION HANDLE FOTO
# ======================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message

        # ======================
        # 🕒 AMBIL WAKTU TELEGRAM
        # ======================
        msg_time = message.date  # UTC time dari Telegram
        date_folder = msg_time.strftime("%Y-%m-%d")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")

        # ======================
        # 🏷️ CAPTION LOGIC
        # ======================
        caption = message.caption

        if caption and caption.strip():
            # ambil caption + timestamp
            clean_caption = caption.strip().replace(" ", "_")
            filename = f"{clean_caption}_{timestamp}.jpg"
            folder_name = f"Civil_Project/{date_folder}"
        else:
            # tidak ada caption
            filename = f"tanpa_keterangan_{timestamp}.jpg"
            folder_name = f"Civil_Project/{date_folder}/tanpa_caption"

        # ======================
        # 📷 AMBIL FILE FOTO TERBAIK
        # ======================
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_path = f"/tmp/{filename}"
        await file.download_to_drive(file_path)

        # ======================
        # ☁️ UPLOAD KE CLOUDINARY
        # ======================
        result = cloudinary.uploader.upload(
            file_path,
            folder=folder_name,
            public_id=filename.replace(".jpg", ""),
            resource_type="image"
        )

        # ======================
        # 📤 RESPONSE KE USER
        # ======================
        await message.reply_text(
            f"✅ BERHASIL UPLOAD\n\n"
            f"📁 Folder: {folder_name}\n"
            f"📄 File: {filename}\n"
            f"🔗 {result['secure_url']}"
        )

    except Exception as e:
        await message.reply_text(f"❌ ERROR: {str(e)}")


# ======================
# 🚀 MAIN BOT
# ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Bot sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
