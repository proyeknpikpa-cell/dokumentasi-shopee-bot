import os
import re
import cloudinary
import cloudinary.uploader
from datetime import datetime
from telegram.ext import Updater, MessageHandler, Filters

# ================= CONFIG =================
TELEGRAM_TOKEN = "ISI_TOKEN_BOT_KAMU"

cloudinary.config(
    cloud_name="ISI_CLOUD_NAME",
    api_key="ISI_API_KEY",
    api_secret="ISI_API_SECRET"
)
# ==========================================

def parse_caption(caption):
    try:
        # Contoh caption:
        # Kegiatan: Pengecoran 20% - 10 April 2026

        kegiatan_match = re.search(r'Kegiatan:\s*(.*?)\s*-', caption, re.IGNORECASE)
        tanggal_match = re.search(r'-\s*(.*)', caption)

        kegiatan = kegiatan_match.group(1).strip() if kegiatan_match else "tanpa_kegiatan"
        tanggal_text = tanggal_match.group(1).strip() if tanggal_match else ""

        tanggal = datetime.strptime(tanggal_text, "%d %B %Y")
        tanggal_format = tanggal.strftime("%Y-%m-%d")

        # bersihin nama file
        kegiatan = kegiatan.lower().replace(" ", "_")

        return kegiatan, tanggal_format

    except:
        return "unknown", datetime.now().strftime("%Y-%m-%d")


def handle_photo(update, context):
    message = update.message
    caption = message.caption or ""

    kegiatan, tanggal = parse_caption(caption)

    # Ambil file terbesar
    photo = message.photo[-1]
    file = photo.get_file()

    # Download sementara
    file_path = "temp.jpg"
    file.download(file_path)

    # Nama file baru
    filename = f"{tanggal}_{kegiatan}.jpg"

    # Upload ke Cloudinary
    response = cloudinary.uploader.upload(
        file_path,
        public_id=f"{tanggal}/{filename}",
        folder="dokumentasi_proyek"
    )

    # Hapus file lokal
    os.remove(file_path)

    update.message.reply_text(
        f"✅ Upload berhasil!\n\n"
        f"📁 Folder: {tanggal}\n"
        f"📄 File: {filename}"
    )


def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.photo, handle_photo))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
