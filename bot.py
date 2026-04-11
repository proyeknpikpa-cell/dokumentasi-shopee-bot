import os
from datetime import datetime
from zoneinfo import ZoneInfo
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

OWNER_USERNAME = os.getenv("OWNER_USERNAME")

SHEET_URL = os.getenv("SHEET_URL")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

# ======================
# ⚙️ MODE RESPONSE
# ======================
RESPONSE_MODE = "full"

def is_owner(user):
    if not user.username:
        return False
    return user.username.lower() == OWNER_USERNAME.replace("@", "").lower()

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

sheet_pdf = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Dokumen_PDF")

# ======================
# 📊 SAVE SHEET
# ======================
def save_to_sheet(date, time, month, sender, caption, url):
    sheet.append_row([
        date,
        time,
        month,
        sender,
        caption,
        url
    ])

def save_pdf_to_sheet(date, time, month, sender, filename, url):
    sheet_pdf.append_row([
        date,
        time,
        month,
        sender,
        filename,
        url
    ])

# ======================
# 🔥 FIX CLOUDINARY PUBLIC ID
# ======================
def clean_public_id(text):
    import re
    text = text.lower()
    text = re.sub(r'\.[a-z0-9]+$', '', text)
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text[:80]

# ======================
# 📷 HANDLE FOTO
# ======================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message

        msg_time = message.date.astimezone(ZoneInfo("Asia/Jakarta"))

        date = msg_time.strftime("%d-%m-%Y")
        time = msg_time.strftime("%H:%M:%S")
        month = msg_time.strftime("%B %Y")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")

        folder_name = f"Proyek_NPI/{date}"

        user = message.from_user
        sender = f"@{user.username}" if user.username else user.full_name

        import re

        caption_raw = message.caption or ""

        def clean_text(text):
            text = text.lower()
            text = re.sub(r'[^a-z0-9\s]', ' ', text)
            text = "_".join(text.split())
            return text[:80]

        if caption_raw.strip():
            kegiatan_match = re.search(r'kegiatan\s*:\s*(.*)', caption_raw, re.IGNORECASE)
            lokasi_match = re.search(r'lokasi\s*:\s*(.*)', caption_raw, re.IGNORECASE)

            kegiatan_text = kegiatan_match.group(1).strip() if kegiatan_match else ""
            lokasi_text = lokasi_match.group(1).strip() if lokasi_match else ""

            if kegiatan_text or lokasi_text:
                nama_file = f"kegiatan_{kegiatan_text}_lokasi_{lokasi_text}"
                base_name = f"{clean_text(nama_file)}_{timestamp}"
            else:
                base_name = f"{clean_text(caption_raw)}_{timestamp}"
        else:
            base_name = f"foto_{timestamp}"
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

        save_to_sheet(date, time, month, sender, caption_raw or "-", url)

        await message.reply_text(f"✅ Upload foto berhasil\n🔗 {url}")

    except Exception as e:
        await message.reply_text(f"❌ ERROR: {str(e)}")

# ======================
# 📄 HANDLE PDF / WORD / EXCEL / PPT
# ======================
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        document = message.document

        msg_time = message.date.astimezone(ZoneInfo("Asia/Jakarta"))

        date = msg_time.strftime("%d-%m-%Y")
        time = msg_time.strftime("%H:%M:%S")
        month = msg_time.strftime("%B %Y")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")

        folder_name = f"Dokumen_PDF/{date}"

        user = message.from_user
        sender = f"@{user.username}" if user.username else user.full_name

        filename = document.file_name or f"dokumen_{timestamp}"

        file = await context.bot.get_file(document.file_id)
        file_path = f"/tmp/{filename}"
        await file.download_to_drive(file_path)

        # 🔥 FIX: aman untuk semua file
        public_id = clean_public_id(filename)

        result = cloudinary.uploader.upload(
            file_path,
            folder=folder_name,
            public_id=public_id,
            resource_type="raw"
        )

        url = result["secure_url"]

        save_pdf_to_sheet(
            date,
            time,
            month,
            sender,
            filename,
            url
        )

        await message.reply_text("📄 File berhasil diupload")

    except Exception as e:
        await message.reply_text(f"❌ ERROR PDF: {str(e)}")

# ======================
# (SEMUA BAGIAN LAIN TETAP SAMA - TIDAK DIUBAH)
# ======================
# info_command, sheet_command, button_handler, saran_command, mode_command, main
# tetap seperti kode kamu sebelumnya
