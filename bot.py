import os
import logging
import re
import cloudinary
import cloudinary.uploader

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ================= CONFIG ENV =================
TELEGRAM_TOKEN = os.getenv("8716037244:AAHhdKh6dZFh1iCHzPWKeyMp3ErhhsCzgc0")

CLOUDINARY_CLOUD_NAME = os.getenv("drt9op6uh")
CLOUDINARY_API_KEY = os.getenv("415159293348757")
CLOUDINARY_API_SECRET = os.getenv("dh-MAaIMlvZBlQlp1zFjbp6sU84")

# ================= CHECK TOKEN =================
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan di environment variable!")

# ================= CLOUDINARY CONFIG =================
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)

# ================= PARSE CAPTION =================
def parse_caption(caption: str):
    if not caption:
        return ("tanpa_keterangan", "tanpa_tanggal")

    # coba ambil tanggal YYYY-MM-DD
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", caption)
    tanggal = date_match.group(0) if date_match else "tanpa_tanggal"

    # ambil kata pertama sebagai kegiatan
    words = caption.split()
    kegiatan = words[0] if len(words) > 0 else "kegiatan"

    # bersihkan nama file
    kegiatan = re.sub(r"[^a-zA-Z0-9_]", "_", kegiatan)

    return kegiatan, tanggal

# ================= HANDLER FOTO =================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        caption = message.caption or ""

        photo_file = await message.photo[-1].get_file()

        await message.reply_text("⏳ Sedang proses upload...")

        # parse caption
        kegiatan, tanggal = parse_caption(caption)

        public_id = f"{tanggal}_{kegiatan}"
        folder_name = f"Civil_Project/{tanggal}"

        # download file dari telegram
        photo_bytes = await photo_file.download_as_bytearray()

        file_path = f"/tmp/{public_id}.jpg"

        with open(file_path, "wb") as f:
            f.write(photo_bytes)

        # upload ke cloudinary
        upload_result = cloudinary.uploader.upload(
            file_path,
            folder=folder_name,
            public_id=public_id,
            resource_type="image"
        )

        file_url = upload_result.get("secure_url")

        await message.reply_text(
            "✅ BERHASIL UPLOAD\n\n"
            f"📂 Folder: {folder_name}\n"
            f"📄 File: {public_id}.jpg\n"
            f"🔗 {file_url}"
        )

    except Exception as e:
        logging.error(f"Upload error: {e}")
        await message.reply_text("❌ Gagal upload foto.")

# ================= MAIN =================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot jalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
