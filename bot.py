import os
import re
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
    sheet.append_row([date, time, month, sender, caption, url])

def save_pdf_to_sheet(date, time, month, sender, filename, url):
    sheet_pdf.append_row([date, time, month, sender, filename, url])

# ======================
# 🛠️ HELPER
# ======================
def clean_text(text):
    """Membersihkan teks agar aman digunakan sebagai nama file/public_id"""
    text = text.lower()
    # Menghapus ekstensi .pdf di akhir jika ada sebelum cleaning
    if text.endswith(".pdf"):
        text = text[:-4]
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = "_".join(text.split())
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

        caption_raw = message.caption or ""

        if caption_raw.strip():
            caption_final = caption_raw
            kegiatan_match = re.search(r'kegiatan\s*:\s*(.*)', caption_raw, re.IGNORECASE)
            lokasi_match = re.search(r'lokasi\s*:\s*(.*)', caption_raw, re.IGNORECASE)

            kegiatan_text = kegiatan_match.group(1).strip() if kegiatan_match else ""
            lokasi_text = lokasi_match.group(1).strip() if lokasi_match else ""

            if kegiatan_text or lokasi_text:
                nama_file = f"kegiatan_{kegiatan_text}_lokasi_{lokasi_text}"
                clean_name = clean_text(nama_file)
                base_name = f"{clean_name}_{timestamp}"
            else:
                clean = clean_text(caption_raw)
                base_name = f"{clean}_{timestamp}"
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
        save_to_sheet(date, time, month, sender, caption_final, url)

        # Response logic
        if RESPONSE_MODE == "simple":
            await message.reply_text("✅ Upload berhasil")
        elif RESPONSE_MODE == "caption":
            await message.reply_text(f"✅ Upload berhasil\n📝 {caption_final}")
        elif RESPONSE_MODE == "link":
            await message.reply_text(f"✅ Upload berhasil\n🔗 {url}")
        else:
            await message.reply_text(
                f"✅ BERHASIL UPLOAD\n\n📅 {date} | ⏰ {time}\n"
                f"👤 {sender}\n📝 {caption_final}\n📂 {folder_name}\n🔗 {url}"
            )

    except Exception as e:
        await message.reply_text(f"❌ ERROR: {str(e)}")

# ======================
# 📄 HANDLE PDF (FIXED)
# ======================
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        document = message.document

        if not document.mime_type == "application/pdf":
            return

        msg_time = message.date.astimezone(ZoneInfo("Asia/Jakarta"))
        date = msg_time.strftime("%d-%m-%Y")
        time = msg_time.strftime("%H:%M:%S")
        month = msg_time.strftime("%B %Y")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")

        folder_name = f"Dokumen_PDF/{date}"
        user = message.from_user
        sender = f"@{user.username}" if user.username else user.full_name

        original_filename = document.file_name or f"dokumen_{timestamp}.pdf"
        
        # PERBAIKAN: Bersihkan nama file agar valid untuk public_id Cloudinary
        # Cloudinary tidak suka spasi atau karakter khusus seperti % dalam public_id
        safe_name = clean_text(original_filename)
        public_id_final = f"{safe_name}_{timestamp}"

        file = await context.bot.get_file(document.file_id)
        # Simpan file di /tmp dengan nama asli agar tidak bentrok
        temp_file_path = f"/tmp/{timestamp}_{original_filename}"
        await file.download_to_drive(temp_file_path)

        result = cloudinary.uploader.upload(
            temp_file_path,
            folder=folder_name,
            public_id=public_id_final,
            resource_type="raw"  # Wajib 'raw' untuk non-image seperti PDF
        )

        url = result["secure_url"]
        save_pdf_to_sheet(date, time, month, sender, original_filename, url)

        await message.reply_text(
            f"📄 PDF BERHASIL DIUPLOAD\n\n"
            f"📁 Nama: {original_filename}\n"
            f"👤 Oleh: {sender}\n"
            f"🔗 Link: {url}"
        )

        # Hapus file temporary
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

    except Exception as e:
        await message.reply_text(f"❌ ERROR PDF: {str(e)}")

# ======================
# Sisanya (info, sheet, button, saran, mode, main) tetap sama
# ======================
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Jumlah Foto Hari Ini", callback_data="jumlah")],
        [InlineKeyboardButton("👨‍💻 Developer", callback_data="dev")],
        [InlineKeyboardButton("💬 Masukan", callback_data="saran")]
    ]
    await update.message.reply_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))

async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📊 Link Dokumentasi:\n{SHEET_URL}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "jumlah":
        today = datetime.now().strftime("%d-%m-%Y")
        rows = sheet.get_all_values()
        count = sum(1 for r in rows if r and r[0] == today)
        await query.edit_message_text(f"📊 Hari ini ada {count} foto")
    elif data == "dev":
        await query.edit_message_text(f"👨‍💻 Developer: {OWNER_USERNAME}")
    elif data == "saran":
        await query.edit_message_text("💬 Kirim saran:\n\n/saran isi pesan kamu")

async def saran_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❗ Tulis saran setelah /saran")
        return
    sender = f"@{user.username}" if user.username else user.full_name
    await update.message.reply_text("✅ Saran dikirim!")
    # Kirim ke owner (asumsi owner username adalah target)
    print(f"Saran dari {sender}: {text}")

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RESPONSE_MODE
    user = update.message.from_user
    if not is_owner(user):
        await update.message.reply_text("❌ Kamu bukan owner")
        return
    if not context.args:
        await update.message.reply_text("Gunakan:\n/mode full | simple | caption | link")
        return
    mode = context.args[0].lower()
    if mode not in ["full", "simple", "caption", "link"]:
        await update.message.reply_text("❌ Mode tidak valid")
        return
    RESPONSE_MODE = mode
    await update.message.reply_text(f"✅ Mode diubah ke: {mode}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("saran", saran_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("sheet", sheet_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Bot jalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
