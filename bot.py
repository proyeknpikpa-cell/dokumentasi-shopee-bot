import os
import re
import asyncio
import logging
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
import cloudinary
import cloudinary.uploader

# Gunakan library Google GenAI terbaru
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ Library 'google-genai' belum terinstal. Jalankan: pip install google-genai")

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

# Konfigurasi Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PANDUAN_URL = "https://proyeknpikpa-cell.github.io/panduan-bot-npi/"

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

# ======================
# ⚙️ GLOBAL STATE & AI CONFIG
# ======================
RESPONSE_MODE = "full"
ITEMS_PER_PAGE = 10

# Inisialisasi SDK Gemini baru
client_ai = None
if GEMINI_API_KEY:
    try:
        client_ai = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("✅ Gemini AI SDK v2 berhasil dikonfigurasi.")
    except Exception as e:
        logger.error(f"⚠️ Gagal konfigurasi Gemini: {e}")

def is_owner(user):
    if not user.username:
        return False
    return user.username.lower() == OWNER_USERNAME.replace("@", "").lower()

def escape_markdown(text):
    """Menghindari error 'Can't parse entities' di Telegram MarkdownV2/Legacy"""
    # Karakter yang sering merusak Markdown Telegram
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', text)

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
try:
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    private_key = GOOGLE_PRIVATE_KEY.replace("\\n", "\n") if GOOGLE_PRIVATE_KEY else ""
    creds = Credentials.from_service_account_info({
        "type": "service_account",
        "client_email": GOOGLE_CLIENT_EMAIL,
        "private_key": private_key,
        "token_uri": "https://oauth2.googleapis.com/token"
    }, scopes=scope)
    client_sheet = gspread.authorize(creds)
    sheet_instance = client_sheet.open_by_key(GOOGLE_SHEET_ID)
    sheet_photo = sheet_instance.worksheet("Proyek_NPI")
    sheet_doc = sheet_instance.worksheet("Dokumen_PDF")
    logger.info("✅ Google Sheets berhasil terhubung.")
except Exception as e:
    logger.error(f"❌ Gagal inisialisasi Google Sheets: {e}")

# ======================
# 🛠️ HELPER & AI LOGIC
# ======================
def clean_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = "_".join(text.split())
    return text[:80]

async def ai_extract_caption(raw_caption):
    """
    Ekstraksi menggunakan SDK terbaru agar tidak 404.
    """
    if not client_ai or not raw_caption or len(raw_caption) < 5:
        return raw_caption
    
    prompt = f"""
    Tugas: Ekstrak 'Kegiatan' dan 'Lokasi' dari teks laporan proyek.
    Format wajib: Kegiatan: [isi] | Lokasi: [isi]
    Jangan beri penjelasan tambahan. Jika tidak ada tulis '-'.
    
    Teks: {raw_caption}
    """
    
    try:
        # Pemanggilan async dengan SDK baru
        response = await asyncio.to_thread(
            client_ai.models.generate_content,
            model="gemini-1.5-flash",
            contents=prompt
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        logger.warning(f"🤖 AI Error: {e}")
            
    return raw_caption

# ======================
# 📷 HANDLE FOTO
# ======================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = None
    try:
        message = update.message
        msg_time = message.date.astimezone(ZoneInfo("Asia/Jakarta"))
        date = msg_time.strftime("%d-%m-%Y")
        time = msg_time.strftime("%H:%M:%S")
        month = msg_time.strftime("%B %Y")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")
        
        user = message.from_user
        sender = f"@{user.username}" if user.username else user.full_name
        caption_raw = message.caption or ""
        
        # 1. AI Processing
        caption_final = await ai_extract_caption(caption_raw) if caption_raw else "-"
        
        # 2. Persiapan File
        photo = message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            file_path = tmp.name
            
        await tg_file.download_to_drive(file_path)
        
        # 3. Upload Cloudinary
        clean_name = clean_text(caption_raw[:20]) if caption_raw else "foto"
        public_id = f"{clean_name}_{timestamp}"
        result = cloudinary.uploader.upload(file_path, folder=f"Proyek_NPI/{date}", public_id=public_id)
        url = result["secure_url"]
        
        # 4. Save to Sheet
        sheet_photo.append_row([date, time, month, sender, caption_final, url])
        
        # 5. Response (Gunakan HTML agar lebih aman dari karakter khusus Markdown)
        if RESPONSE_MODE == "simple":
            await message.reply_text("✅ Foto berhasil diupload")
        else:
            # Menggunakan HTML parse mode lebih aman daripada Markdown untuk teks AI
            response_text = (
                f"✅ <b>FOTO BERHASIL</b>\n"
                f"👤 {sender}\n"
                f"📝 {caption_final}\n"
                f"🔗 <a href='{url}'>Lihat Foto</a>"
            )
            await message.reply_html(response_text, disable_web_page_preview=True)
            
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}", exc_info=True)
        # Fallback pesan jika terjadi error parsing
        await message.reply_text(f"❌ TERJADI KENDALA: Sistem mencatat data Anda namun gagal mengirim format pesan.")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

# ======================
# 📄 HANDLE DOKUMEN
# ======================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    temp_path = None
    try:
        message = update.message
        doc = message.document
        msg_time = message.date.astimezone(ZoneInfo("Asia/Jakarta"))
        date = msg_time.strftime("%d-%m-%Y")
        time = msg_time.strftime("%H:%M:%S")
        month = msg_time.strftime("%B %Y")
        timestamp = msg_time.strftime("%Y-%m-%d_%H-%M-%S")
        user = message.from_user
        sender = f"@{user.username}" if user.username else user.full_name
        
        original_name = doc.file_name or "document"
        ext = os.path.splitext(original_name)[1].lower()
        
        category = 'LAINNYA'
        icon = '📄'
        if ext == '.pdf': category, icon = 'PDF', '📕'
        elif ext in ['.doc', '.docx']: category, icon = 'WORD', '📘'
        elif ext in ['.xls', '.xlsx']: category, icon = 'EXCEL', '📗'
        
        tg_file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            temp_path = tmp.name
            
        await tg_file.download_to_drive(temp_path)
        
        safe_name = clean_text(original_name)
        result = cloudinary.uploader.upload(temp_path, folder=f"Dokumen_Proyek/{category}/{date}", 
                                           public_id=f"{safe_name}_{timestamp}", resource_type="raw")
        url = result["secure_url"]
        
        sheet_doc.append_row([date, time, month, sender, original_name, category, url])
        
        await message.reply_html(
            f"✅ <b>Dokumen Berhasil!</b>\n{icon} <code>{original_name}</code>\n🔗 <a href='{url}'>Link Dokumen</a>",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in handle_document: {e}")
        await update.message.reply_text("❌ Gagal upload dokumen.")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

# ======================
# 📋 COMMANDS
# ======================
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📊 Statistik", callback_data=f"jumlah|{user_id}")],
        [InlineKeyboardButton("📖 Panduan", url=PANDUAN_URL)],
        [InlineKeyboardButton("❌ Tutup", callback_data=f"close|{user_id}")]
    ]
    await update.message.reply_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split("|")[0]
    await query.answer()
    if data == "close": await query.delete_message()
    elif data == "jumlah":
        rows = sheet_photo.get_all_values()
        await query.edit_message_text(f"📊 Total foto: {len(rows)-1}")

# ======================
# 🚀 MAIN
# ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("🤖 Bot NPI (v2 Gemini) Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
