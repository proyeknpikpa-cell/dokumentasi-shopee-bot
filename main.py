import os
import re
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

TOKEN = os.getenv("BOT_TOKEN")

# ===== ID FOLDER UTAMA =====
PARENT_FOLDER_ID = "1T21xh7g-uLrMYUHsi_mqYay-jRsTwCOU"

# ===== SETUP GOOGLE DRIVE =====
SCOPES = ["https://www.googleapis.com/auth/drive"]

creds = None
drive_service = None

try:
    creds = service_account.Credentials.from_service_account_file(
        "creds.json", scopes=SCOPES
    )

    drive_service = build("drive", "v3", credentials=creds)

    print("✅ Google Drive siap")

except Exception as e:
    print("❌ ERROR GOOGLE CREDS:", e)

# ===== FOLDER =====
def get_or_create_folder(folder_name):
    query = f"name='{folder_name}' and '{PARENT_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'"
    
    results = drive_service.files().list(q=query).execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    file_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [PARENT_FOLDER_ID]
    }

    folder = drive_service.files().create(body=file_metadata).execute()
    return folder["id"]

# ===== PARSE =====
def extract_kegiatan(text):
    if not text:
        return None

    match = re.search(r'Kegiatan\s*:\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_date(text):
    try:
        match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', text)
        if match:
            date_obj = datetime.strptime(match.group(1), "%d %B %Y")
            return date_obj.strftime("%Y-%m-%d")
    except:
        pass

    return datetime.now().strftime("%Y-%m-%d")

# ===== COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot aktif")

# ===== HANDLE FOTO =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not drive_service:
        await message.reply_text("❌ Google Drive belum siap")
        return

    try:
        caption = message.caption or ""

        kegiatan = extract_kegiatan(caption)
        tanggal = extract_date(caption)

        if kegiatan and kegiatan != "0%":
            base_name = kegiatan.replace(" ", "_")
        else:
            base_name = datetime.now().strftime("%H-%M-%S")

        filename = f"{tanggal}_{base_name}.jpg"

        # download
        photo = message.photo[-1]
        file = await photo.get_file()

        os.makedirs("downloads", exist_ok=True)
        path = f"downloads/{filename}"

        await file.download_to_drive(path)

        # upload
        folder_id = get_or_create_folder(tanggal)

        file_metadata = {
            "name": filename,
            "parents": [folder_id]
        }

        media = MediaFileUpload(path, mimetype="image/jpeg")

        drive_service.files().create(
            body=file_metadata,
            media_body=media
        ).execute()

        await message.reply_text(f"📁 Upload:\n{filename}")

    except Exception as e:
        print("ERROR:", e)
        await message.reply_text("❌ Gagal upload")

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

print("Bot running...")

app.run_polling(drop_pending_updates=True)
