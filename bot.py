import os
import logging
from datetime import datetime
import re

# Library pihak ketiga
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import cloudinary
import cloudinary.uploader

# 1. KONFIGURASI LOGGING
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 2. KONFIGURASI CLOUDINARY
# Ganti dengan data dari dashboard Cloudinary Anda atau set di Environment Variables
cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_NAME"), 
    api_key = os.getenv("CLOUDINARY_API_KEY"), 
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure = True
)

# 3. FUNGSI PARSING CAPTION
def parse_caption(caption):
    """
    Mengambil data dari format: "Kegiatan: Pengecoran 20% - 10 April 2026"
    Output: (nama_kegiatan, tanggal_str)
    """
    if not caption:
        return "Tanpa_Nama", datetime.now().strftime("%Y-%m-%d")

    try:
        # Regex sederhana untuk memisahkan setelah titik dua (:) dan sebelum tanda pisah (-)
        # Contoh: "Kegiatan: Pengecoran - 10 April 2026"
        parts = re.split(r'[:\-]', caption)
        
        kegiatan = parts[1].strip() if len(parts) > 1 else "Dokumentasi"
        tanggal = parts[2].strip() if len(parts) > 2 else datetime.now().strftime("%Y-%m-%d")
        
        # Bersihkan karakter yang dilarang di nama file
        kegiatan = re.sub(r'[^\w\s-]', '', kegiatan).replace(' ', '_')
        tanggal = re.sub(r'[^\w\s-]', '', tanggal).replace(' ', '_')
        
        return kegiatan, tanggal
    except Exception:
        return "Error_Format", datetime.now().strftime("%Y-%m-%d")

# 4. HANDLER UNTUK FOTO
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    photo_file = await update.message.photo[-1].get_file() # Ambil kualitas tertinggi
    caption = update.message.caption
    
    # Notifikasi awal
    await update.message.reply_text("⏳ Sedang memproses dan mengunggah foto...")

    # Ekstrak info dari caption
    kegiatan, tanggal = parse_caption(caption)
    
    # Format nama file: [tanggal]_[kegiatan]
    public_id = f"{tanggal}_{kegiatan}"
    # Folder otomatis berdasarkan tanggal (Format YYYY-MM-DD)
    folder_name = f"Civil_Project/{datetime.now().strftime('%Y-%m-%d')}"

    try:
        # Download file sementara ke RAM (bukan disk agar aman di cloud)
        photo_bytes = await photo_file.download_as_bytearray()

        # Upload ke Cloudinary
        upload_result = cloudinary.uploader.upload(
            bytes(photo_bytes),
            public_id = public_id,
            folder = folder_name,
            resource_type = "image"
        )

        # Kirim balik link sukses
        file_url = upload_result.get("secure_url")
        msg = (
            f"✅ **Berhasil Disimpan!**\n\n"
            f"📂 Folder: `{folder_name}`\n"
            f"📄 Nama: `{public_id}.jpg`\n"
            f"🔗 Link: [Lihat Foto]({file_url})"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error upload: {e}")
        await update.message.reply_text("❌ Gagal menyimpan foto. Pastikan format caption benar.")

if __name__ == '__main__':
    # Token dari BotFather
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN tidak ditemukan di environment variable!")
        exit(1)

    application = ApplicationBuilder().token(TOKEN).build()
    
    # Handler: hanya terima pesan yang mengandung foto
    photo_handler = MessageHandler(filters.PHOTO, handle_photo)
    application.add_handler(photo_handler)
    
    print("Bot sedang berjalan...")
    application.run_polling()
