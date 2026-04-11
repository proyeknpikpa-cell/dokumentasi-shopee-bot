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
# ⚙️ GLOBAL STATE
# ======================
RESPONSE_MODE = "full"
ITEMS_PER_PAGE = 10

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
sheet_photo = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Proyek_NPI")
sheet_doc = client.open_by_key(GOOGLE_SHEET_ID).worksheet("Dokumen_PDF")

# ======================
# 🛠️ HELPER
# ======================
def clean_text(text):
    """Pembersihan nama file untuk public_id Cloudinary"""
    # Hapus ekstensi umum sebelum cleaning
    exts = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt']
    text = text.lower()
    for ext in exts:
        if text.endswith(ext):
            text = text.replace(ext, "")
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = "_".join(text.split())
    return text[:80]

def get_file_category(filename):
    """Kategorisasi jenis file berdasarkan ekstensi"""
    fn = filename.lower()
    if fn.endswith('.pdf'): return 'PDF', '📕'
    if fn.endswith(('.doc', '.docx')): return 'WORD', '📘'
    if fn.endswith(('.xls', '.xlsx')): return 'EXCEL', '📗'
    if fn.endswith(('.ppt', '.pptx')): return 'PPT', '📙'
    return 'LAINNYA', '📄'

# ======================
# 📊 SAVE TO SHEET
# ======================
def save_photo_to_sheet(date, time, month, sender, caption, url):
    sheet_photo.append_row([date, time, month, sender, caption, url])

def save_doc_to_sheet(date, time, month, sender, filename, category, url):
    # Struktur: Tanggal, Jam, Bulan, Pengirim, Caption (Nama File), Jenis File, Link
    sheet_doc.append_row([date, time, month, sender, filename, category, url])

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
        
        # Logika penamaan file foto
        if caption_raw.strip():
            caption_final = caption_raw
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
        save_photo_to_sheet(date, time, month, sender, caption_final, url)

        # Respon sesuai mode
        if RESPONSE_MODE == "simple":
            await message.reply_text("✅ Foto berhasil diupload")
        else:
            await message.reply_text(f"✅ FOTO BERHASIL\n👤 {sender}\n📝 {caption_final}\n🔗 {url}")

    except Exception as e:
        await message.reply_text(f"❌ ERROR FOTO: {str(e)}")

# ======================
# 📄 HANDLE DOKUMEN (ALL)
# ======================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        original_name = doc.file_name or f"file_{timestamp}"
        category, icon = get_file_category(original_name)
        
        # Cloudinary setup
        folder_name = f"Dokumen_Proyek/{category}/{date}"
        safe_name = clean_text(original_name)
        public_id_final = f"{safe_name}_{timestamp}"

        file = await context.bot.get_file(doc.file_id)
        temp_path = f"/tmp/{timestamp}_{original_name}"
        await file.download_to_drive(temp_path)

        result = cloudinary.uploader.upload(
            temp_path,
            folder=folder_name,
            public_id=public_id_final,
            resource_type="raw"
        )

        url = result["secure_url"]
        save_doc_to_sheet(date, time, month, sender, original_name, category, url)

        # OPSI 1: Minimalist & Clean Response
        await message.reply_text(
            f"✅ **Berhasil diupload!**\n"
            f"{icon} `{original_name}` ({category})\n"
            f"🔗 [Buka Dokumen]({url})",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

        if os.path.exists(temp_path):
            os.remove(temp_path)

    except Exception as e:
        await message.reply_text(f"❌ ERROR DOKUMEN: {str(e)}")

# ======================
# 📋 COMMANDS
# ======================
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📄 Cek Dokumen", callback_data="menu_doc")],
        [InlineKeyboardButton("📊 Statistik Foto", callback_data="jumlah")],
        [InlineKeyboardButton("👨‍💻 Developer", callback_data="dev")]
    ]
    await update.message.reply_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))

async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Respon Minimalis untuk perintah /sheet
    await update.message.reply_text(
        f"📊 **Link Dokumentasi**\n"
        f"🔗 [Klik untuk Membuka Sheet]({SHEET_URL})",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# ======================
# 🎯 CALLBACK HANDLER (PAGINATION)
# ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "menu_doc":
        kb = [
            [InlineKeyboardButton("📕 PDF", callback_data="list_PDF_0")],
            [InlineKeyboardButton("📘 WORD", callback_data="list_WORD_0")],
            [InlineKeyboardButton("📗 EXCEL", callback_data="list_EXCEL_0")],
            [InlineKeyboardButton("📙 PPT", callback_data="list_PPT_0")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="back_main")]
        ]
        await query.edit_message_text("Pilih jenis dokumen yang ingin dicari:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("list_"):
        # Format data: list_KATEGORI_OFFSET
        _, category, offset = data.split("_")
        offset = int(offset)
        
        all_rows = sheet_doc.get_all_values()[1:] # Skip header
        # Filter berdasarkan kategori (Kolom F / Indeks 5)
        filtered = [r for r in all_rows if len(r) > 5 and r[5] == category]
        filtered.reverse() # Terbaru di atas

        total = len(filtered)
        start = offset
        end = offset + ITEMS_PER_PAGE
        current_list = filtered[start:end]

        if not current_list:
            await query.edit_message_text(f"📭 Belum ada dokumen {category}", 
                                         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="menu_doc")]]))
            return

        text = f"📂 **DAFTAR DOKUMEN {category}**\n"
        text += f"_(Menampilkan {start+1}-{min(end, total)} dari {total} file)_\n\n"

        for i, row in enumerate(current_list, start=1):
            name = row[4] # Kolom E (Caption/Nama File)
            link = row[6] # Kolom G (Link)
            text += f"{i}. **{name}**\n🔗 [Buka Dokumen]({link})\n\n"

        buttons = []
        nav_row = []
        if end < total:
            nav_row.append(InlineKeyboardButton("⬅️ Sebelumnya (Lama)", callback_data=f"list_{category}_{end}"))
        if offset > 0:
            nav_row.append(InlineKeyboardButton("➡️ Terbaru", callback_data=f"list_{category}_{max(0, offset-ITEMS_PER_PAGE)}"))
        
        if nav_row: buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("🔙 Pilih Jenis Lain", callback_data="menu_doc")])

        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("📄 Cek Dokumen", callback_data="menu_doc")],
            [InlineKeyboardButton("📊 Statistik Foto", callback_data="jumlah")],
            [InlineKeyboardButton("👨‍💻 Developer", callback_data="dev")]
        ]
        await query.edit_message_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "jumlah":
        today = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d-%m-%Y")
        rows = sheet_photo.get_all_values()
        count = sum(1 for r in rows if r and r[0] == today)
        await query.edit_message_text(f"📊 Hari ini ada {count} foto diupload.\n\n🔙 Klik /info untuk menu lain.")

    elif data == "dev":
        await query.edit_message_text(f"👨‍💻 Developer: {OWNER_USERNAME}\n\n🔙 Klik /info untuk menu lain.")

# ======================
# 💬 SARAN & MODE
# ======================
async def saran_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❗ Tulis saran setelah /saran")
        return
    sender = f"@{user.username}" if user.username else user.full_name
    await update.message.reply_text("✅ Saran terkirim ke log!")
    print(f"SARAN dari {sender}: {text}")

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RESPONSE_MODE
    user = update.message.from_user
    if not is_owner(user):
        await update.message.reply_text("❌ Akses ditolak.")
        return
    if not context.args:
        await update.message.reply_text("Gunakan: /mode full | simple")
        return
    mode = context.args[0].lower()
    RESPONSE_MODE = mode
    await update.message.reply_text(f"✅ Respon mode: {mode}")

# ======================
# 🚀 MAIN
# ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("saran", saran_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("sheet", sheet_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Aktif (NPI Project)...")
    app.run_polling()

if __name__ == "__main__":
    main()
