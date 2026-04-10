import os
import re
import json
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# GOOGLE DRIVE
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Ambil Token dari Railway Variables
TOKEN = os.getenv("BOT_TOKEN")

# ===== ID FOLDER UTAMA =====
# Ganti dengan ID folder tujuanmu di Google Drive
PARENT_FOLDER_ID = "1T21xh7g-uLrMYUHsi_mqYay-jRsTwCOU"

# ===== SETUP GOOGLE DRIVE =====
SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = None
drive_service = None

try:
    # Membaca kredensial dari Environment Variable GOOGLE_CREDS
    creds_json = os.getenv("GOOGLE_CREDS")
    
    if creds_json:
        creds_info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
        drive_service = build("drive", "v3", credentials=creds)
        print("✅ Google Drive siap (Mode Environment Variable)")
    else:
        print("❌ ERROR: Variable GOOGLE_CREDS tidak ditemukan di Railway")

except Exception as e:
    print(f"❌ ERROR SETUP GOOGLE DRIVE: {e}")

# ===== FUNGSI FOLDER =====
def get_or_create_folder(folder_name):
    try:
        query = f"name='{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        results = drive_service.files().list(q=query).execute()
        files = results.get("files", [])

        if files:
            return files[0]["id"]

        # Jika folder belum ada, buat baru
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [PARENT_FOLDER_ID]
        }

        folder = drive_service.files().create(body=file_metadata, fields="id").execute()
        return folder["id"]
    except Exception as e:
        print(f"Error saat membuat folder: {e}")
        return PARENT_FOLDER_ID

# ===== FUNGSI PARSE CAPTION =====
def extract_kegiatan(text):
    if not text:
        return None
    # Mencari teks setelah kata "Kegiatan :"
    match = re.search(r'Kegiatan\s*:\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_date(text):
    # Default ke tanggal hari ini
    now = datetime.now()
    try:
        # Mencari format tanggal (misal: 10 April 2026 atau 10-04-2026)
        match = re.search(r'(\d{1,2}[-/ ]\w+[-/ ]\d{4})', text)
        if match:
            # Jika ingin lebih canggih bisa pakai dateparser, 
            # ini versi sederhana menggunakan hari ini jika gagal parse spesifik
            return now.strftime("%Y-%m-%d")
    except:
        pass
    return now.strftime("%Y-%m-%d")

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot aktif! Kirimkan gambar dengan caption 'Kegiatan: Nama Kegiatan' untuk upload ke Drive.")

# ===== HANDLE FOTO =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not drive_service:
        await message.reply_text("❌ Google Drive belum siap (Cek Logs Railway)")
        return

    try:
        caption = message.caption or ""
        kegiatan = extract_kegiatan(caption)
        tanggal = extract_date(caption)

        # Membuat nama file
        if kegiatan and kegiatan != "0%":
            # Ganti spasi dengan underscore dan hapus karakter ilegal
            clean_kegiatan = re.sub(r'[^\w\s-]', '', kegiatan).strip().replace(" ", "_")
            base_name = clean_kegiatan
        else:
            base_name = datetime.now().strftime("%H-%M-%S")

        filename = f"{tanggal}_{base_name}.jpg"

        # Proses Download dari Telegram
        await message.reply_text("⏳ Sedang memproses gambar...")
        photo = message.photo[-1] # Ambil resolusi tertinggi
        tg_file = await photo.get_file()

        os.makedirs("downloads", exist_ok=True)
        local_path = f"downloads/{filename}"
        await tg_file.download_to_drive(local_path)

        # Proses Upload ke Google Drive
        folder_id = get_or_create_folder(tanggal)

        file_metadata = {
            "name": filename,
            "parents": [folder_id]
        }

        media = MediaFileUpload(local_path, mimetype="image/jpeg", resumable=True)

        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        # Hapus file lokal setelah berhasil upload agar storage Railway tidak penuh
        if os.path.exists(local_path):
            os.remove(local_path)

        await message.reply_text(f"✅ Berhasil diunggah ke Drive!\n📁 Folder: {tanggal}\n📄 File: {filename}")

    except Exception as e:
        print(f"❌ ERROR UPLOAD: {e}")
        await message.reply_text(f"❌ Gagal upload: {str(e)}")

# ===== RUN BOT =====
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: BOT_TOKEN tidak ditemukan di Environment Variables!")
    else:
        app = ApplicationBuilder().token(TOKEN).build()

        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

        print("🚀 Bot Telegram sedang berjalan...")
        app.run_polling(drop_pending_updates=True)
