import os
import re
import json
import asyncio
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
        
        # Membersihkan spasi atau karakter newline tak terlihat di awal/akhir
        creds_cleaned = creds_raw.strip()
        
        # Pastikan string dimulai dengan { dan diakhiri dengan }
        if not (creds_cleaned.startswith('{') and creds_cleaned.endswith('}')):
            # Jika ada karakter sampah di luar kurung kurawal, coba ambil bagian tengahnya saja
            start_index = creds_cleaned.find('{')
            end_index = creds_cleaned.rfind('}') + 1
            if start_index != -1 and end_index != 0:
                creds_cleaned = creds_cleaned[start_index:end_index]

        # Parsing string JSON menjadi dictionary
        creds_info = json.loads(creds_cleaned)
        
        # Perbaikan krusial untuk JWT Signature
        if 'private_key' in creds_info:
            # Mengganti string literal "\n" menjadi karakter newline asli
            creds_info['private_key'] = creds_info['private_key'].replace('\\n', '\n')
        
        creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)
    except json.JSONDecodeError as je:
        print(f"❌ ERROR PARSING JSON: {je}")
        print(f"Data yang terbaca (5 karakter awal): '{creds_raw[:5] if creds_raw else 'N/A'}'")
        return None
    except Exception as e:
        print(f"❌ ERROR SETUP DRIVE: {e}")
        return None

# Inisialisasi awal
drive_service = get_drive_service()

# ===== FUNGSI FOLDER =====
def get_or_create_folder(folder_name):
    if not drive_service: return PARENT_FOLDER_ID
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

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot Aktif. Kirim foto dengan caption 'Kegiatan: Nama'")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    global drive_service
    
    # Coba koneksi ulang jika sebelumnya gagal parse
    if not drive_service:
        drive_service = get_drive_service()
        if not drive_service:
            await message.reply_text("❌ Kredensial Google Drive tidak valid. Cek Logs Railway.")
            return

    try:
        caption = message.caption or ""
        match = re.search(r'Kegiatan\s*:\s*(.*)', caption, re.IGNORECASE)
        kegiatan = match.group(1).strip() if match else "Tanpa_Nama"
        
        tanggal = datetime.now().strftime("%Y-%m-%d")
        clean_kegiatan = re.sub(r'[^\w\s-]', '', kegiatan).strip().replace(" ", "_")
        filename = f"{tanggal}_{clean_kegiatan}.jpg"

        status_msg = await message.reply_text("⏳ Memproses...")
        
        photo = message.photo[-1]
        tg_file = await photo.get_file()

        os.makedirs("downloads", exist_ok=True)
        local_path = os.path.join("downloads", filename)
        
        await tg_file.download_to_drive(local_path)

        folder_id = get_or_create_folder(tanggal)
        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(local_path, mimetype="image/jpeg", resumable=True)

        drive_service.files().create(body=file_metadata, media_body=media).execute()

        if os.path.exists(local_path):
            os.remove(local_path)

        await status_msg.edit_text(f"✅ Terupload ke Drive!\n📁 Folder: {tanggal}\n📄 Nama: {filename}")

    except Exception as e:
        print(f"❌ ERROR UPLOAD: {e}")
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
