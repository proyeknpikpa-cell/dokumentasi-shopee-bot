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
PARENT_FOLDER_ID = "1T21xh7g-uLrMYUHsi_mqYay-jRsTwCOU"

# ===== SETUP GOOGLE DRIVE =====
SCOPES = ["https://www.googleapis.com/auth/drive"]

def get_drive_service():
    try:
        creds_raw = os.getenv("GOOGLE_CREDS")
        if not creds_raw:
            print("❌ ERROR: Variable GOOGLE_CREDS kosong!")
            return None
        
        # Membersihkan karakter aneh yang sering muncul saat copy-paste di Windows/Railway
        creds_cleaned = creds_raw.strip()
        
        # Parsing string JSON menjadi dictionary
        creds_info = json.loads(creds_cleaned)
        
        # Memastikan private_key terformat dengan benar (mengganti literal \n dengan newline asli)
        if 'private_key' in creds_info:
            creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
        
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ ERROR PARSING JSON: {e}")
        return None

drive_service = get_drive_service()
if drive_service:
    print("✅ Google Drive siap")

# ===== FUNGSI FOLDER =====
def get_or_create_folder(folder_name):
    try:
        query = f"name='{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = drive_service.files().list(q=query).execute()
        files = results.get("files", [])

        if files:
            return files[0]["id"]

        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [PARENT_FOLDER_ID]
        }
        folder = drive_service.files().create(body=file_metadata, fields="id").execute()
        return folder["id"]
    except Exception as e:
        print(f"Error folder: {e}")
        return PARENT_FOLDER_ID

# ===== PARSE CAPTION =====
def extract_kegiatan(text):
    if not text: return None
    match = re.search(r'Kegiatan\s*:\s*(.*)', text, re.IGNORECASE)
    return match.group(1).strip() if match else None

def extract_date(text):
    now = datetime.now()
    return now.strftime("%Y-%m-%d")

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot Aktif. Kirim foto dengan caption 'Kegiatan: Nama'")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    # Cek koneksi ulang jika sebelumnya gagal
    global drive_service
    if not drive_service:
        drive_service = get_drive_service()
        if not drive_service:
            await message.reply_text("❌ Sistem Google Drive bermasalah.")
            return

    try:
        caption = message.caption or ""
        kegiatan = extract_kegiatan(caption)
        tanggal = extract_date(caption)
        
        clean_kegiatan = re.sub(r'[^\w\s-]', '', kegiatan or "Tanpa_Nama").strip().replace(" ", "_")
        filename = f"{tanggal}_{clean_kegiatan}.jpg"

        await message.reply_text("⏳ Mengunggah ke Drive...")
        
        photo = message.photo[-1]
        tg_file = await photo.get_file()

        os.makedirs("downloads", exist_ok=True)
        local_path = f"downloads/{filename}"
        await tg_file.download_to_drive(local_path)

        folder_id = get_or_create_folder(tanggal)
        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(local_path, mimetype="image/jpeg", resumable=True)

        drive_service.files().create(body=file_metadata, media_body=media).execute()

        if os.path.exists(local_path):
            os.remove(local_path)

        await message.reply_text(f"✅ Terupload: {filename}")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        await message.reply_text(f"❌ Gagal: {str(e)}")

# ===== RUN =====
if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: BOT_TOKEN Kosong")
    else:
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        print("🚀 Bot Running...")
        app.run_polling(drop_pending_updates=True)
