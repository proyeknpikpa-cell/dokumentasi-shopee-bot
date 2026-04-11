import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import cloudinary
import cloudinary.uploader

import gspread
from google.oauth2.service_account import Credentials

# Pastikan versi python-telegram-bot adalah v20.0 atau lebih tinggi untuk fitur WebApp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
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

# URL Panduan Web App
PANDUAN_WEB_URL = "https://proyeknpikpa-cell.github.io/panduan-bot-npi/"

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

try:
    private_key = GOOGLE_PRIVATE_KEY.replace("\\n", "\n")
    creds = Credentials.from_service_account_info({
        "type": "service_account",
        "client_email": GOOGLE_CLIENT_EMAIL,
        "private_key": private_key,
        "token_uri": "https://oauth2.googleapis.com/token"
    }, scopes=scope)

    client = gspread.authorize(creds)
    sheet_instance = client.open_by_key(GOOGLE_SHEET_ID)
    sheet_photo = sheet_instance.worksheet("Proyek_NPI")
    sheet_doc = sheet_instance.worksheet("Dokumen_PDF")
except Exception as e:
    print(f"❌ Gagal koneksi Google Sheet: {e}")

# ======================
# 🛠️ HELPER
# ======================
def clean_text(text):
    """Pembersihan nama file untuk public_id Cloudinary"""
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

async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghapus pesan perintah dari user agar grup tetap bersih"""
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except Exception:
        pass

# ======================
# 📊 SAVE TO SHEET
# ======================
def save_photo_to_sheet(date, time, month, sender, caption, url):
    sheet_photo.append_row([date, time, month, sender, caption, url])

def save_doc_to_sheet(date, time, month, sender, filename, category, url):
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
        if caption_raw.strip():
            caption_final = caption_raw
            clean = clean_text(caption_raw)
            base_name = f"{clean}_{timestamp}"
        else:
            base_name = f"foto_{timestamp}"
            caption_final = "-"
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_path = f"tmp_{timestamp}.jpg"
        await file.download_to_drive(file_path)
        result = cloudinary.uploader.upload(file_path, folder=folder_name, public_id=base_name, overwrite=True)
        url = result["secure_url"]
        save_photo_to_sheet(date, time, month, sender, caption_final, url)
        if os.path.exists(file_path): os.remove(file_path)
        
        if RESPONSE_MODE == "simple":
            await message.reply_text("✅ Foto berhasil diupload")
        else:
            await message.reply_text(f"✅ FOTO BERHASIL\n👤 {sender}\n📝 {caption_final}\n🔗 {url}")
    except Exception as e:
        await message.reply_text(f"❌ ERROR FOTO: {str(e)}")

# ======================
# 📄 HANDLE DOKUMEN
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
        folder_name = f"Dokumen_Proyek/{category}/{date}"
        safe_name = clean_text(original_name)
        public_id_final = f"{safe_name}_{timestamp}"
        file = await context.bot.get_file(doc.file_id)
        temp_path = f"tmp_{timestamp}_{original_name}"
        await file.download_to_drive(temp_path)
        result = cloudinary.uploader.upload(temp_path, folder=folder_name, public_id=public_id_final, resource_type="raw")
        url = result["secure_url"]
        save_doc_to_sheet(date, time, month, sender, original_name, category, url)
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
    try:
        user_id = update.effective_user.id
        keyboard = [
            # Fitur Baru: Tombol WebApp Panduan
            [InlineKeyboardButton("📖 Panduan Bot (Interaktif)", web_app=WebAppInfo(url=PANDUAN_WEB_URL))],
            [InlineKeyboardButton("📄 Cek Dokumen", callback_data=f"menu_doc|{user_id}")],
            [InlineKeyboardButton("📊 Statistik Foto", callback_data=f"jumlah|{user_id}")],
            [InlineKeyboardButton("👨‍💻 Developer", callback_data=f"dev|{user_id}")],
            [InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{user_id}")]
        ]
        await update.message.reply_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))
        await delete_user_command(update, context)
    except Exception as e:
        print(f"Error info_command: {e}")
        # Fallback jika WebAppInfo menyebabkan error karena versi library lama
        keyboard_basic = [
            [InlineKeyboardButton("📄 Cek Dokumen", callback_data=f"menu_doc|{user_id}")],
            [InlineKeyboardButton("❌ Tutup", callback_data=f"close|{user_id}")]
        ]
        await update.message.reply_text("📋 Menu Bot (Mode Terbatas):", reply_markup=InlineKeyboardMarkup(keyboard_basic))

async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **Link Dokumentasi**\n"
        f"🔗 [Klik untuk Membuka Sheet]({SHEET_URL})",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await delete_user_command(update, context)

async def akses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user):
        await update.message.reply_text("❌ Akses ditolak.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Gunakan format: `/akses email@gmail.com`")
        return
    email = context.args[0]
    try:
        sheet_instance.share(email, perm_type='user', role='writer', notify=True)
        await update.message.reply_text(f"✅ Berhasil! `{email}` sekarang menjadi Editor.")
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal: {str(e)}")
    await delete_user_command(update, context)

# ======================
# 🎯 CALLBACK HANDLER
# ======================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw_data = query.data
    parts = raw_data.split("|")
    action = parts[0]
    owner_id = int(parts[1]) if len(parts) > 1 else None
    
    if owner_id and query.from_user.id != owner_id:
        await query.answer("⚠️ Menu ini hanya untuk pemanggil perintah!", show_alert=True)
        return

    if action == "close":
        await query.delete_message()
        return

    await query.answer()

    if action == "menu_doc":
        kb = [
            [InlineKeyboardButton("📕 PDF", callback_data=f"list_PDF_0|{owner_id}")],
            [InlineKeyboardButton("📘 WORD", callback_data=f"list_WORD_0|{owner_id}")],
            [InlineKeyboardButton("📗 EXCEL", callback_data=f"list_EXCEL_0|{owner_id}")],
            [InlineKeyboardButton("📙 PPT", callback_data=f"list_PPT_0|{owner_id}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data=f"back_main|{owner_id}")]
        ]
        await query.edit_message_text("Pilih jenis dokumen:", reply_markup=InlineKeyboardMarkup(kb))

    elif action.startswith("list_"):
        _, category, offset = action.split("_")
        offset = int(offset)
        all_rows = sheet_doc.get_all_values()[1:]
        filtered = [r for r in all_rows if len(r) > 5 and r[5] == category]
        filtered.reverse()
        current_list = filtered[offset:offset+ITEMS_PER_PAGE]

        if not current_list:
            await query.edit_message_text(f"📭 Kosong", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_doc|{owner_id}")]]))
            return

        text = f"📂 **DAFTAR {category}**\n\n"
        for i, row in enumerate(current_list, offset+1):
            text += f"{i}. **{row[4]}**\n🔗 [Buka]({row[6]})\n\n"

        btns = []
        if offset + ITEMS_PER_PAGE < len(filtered):
            btns.append(InlineKeyboardButton("⬅️ Lama", callback_data=f"list_{category}_{offset+ITEMS_PER_PAGE}|{owner_id}"))
        if offset > 0:
            btns.append(InlineKeyboardButton("➡️ Baru", callback_data=f"list_{category}_{max(0, offset-ITEMS_PER_PAGE)}|{owner_id}"))
        
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([btns, [InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_doc|{owner_id}")]]), disable_web_page_preview=True)

    elif action == "back_main":
        user_id = query.from_user.id
        kb = [
            [InlineKeyboardButton("📖 Panduan Bot (Interaktif)", web_app=WebAppInfo(url=PANDUAN_WEB_URL))],
            [InlineKeyboardButton("📄 Cek Dokumen", callback_data=f"menu_doc|{user_id}")],
            [InlineKeyboardButton("📊 Statistik Foto", callback_data=f"jumlah|{user_id}")],
            [InlineKeyboardButton("👨‍💻 Developer", callback_data=f"dev|{user_id}")],
            [InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{user_id}")]
        ]
        await query.edit_message_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(kb))

    elif action == "jumlah":
        today = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d-%m-%Y")
        rows = sheet_photo.get_all_values()
        count = sum(1 for r in rows if r and r[0] == today)
        await query.edit_message_text(f"📊 Hari ini: {count} foto diupload.\n\n🔙 Klik /info untuk menu lain.",
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"back_main|{owner_id}")]]))

    elif action == "dev":
        await query.edit_message_text(f"👨‍💻 Dev: {OWNER_USERNAME}\n\n🔙 Kembali ke /info.",
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"back_main|{owner_id}")]]))

# ======================
# 💬 SARAN & MODE
# ======================
async def saran_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❗ Tulis saran setelah /saran")
        return
    await update.message.reply_text("✅ Saran terkirim!")
    await delete_user_command(update, context)

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RESPONSE_MODE
    if not is_owner(update.effective_user):
        await update.message.reply_text("❌ Akses ditolak.")
        return
    if not context.args:
        await update.message.reply_text("Gunakan: /mode full | simple")
        return
    RESPONSE_MODE = context.args[0].lower()
    await update.message.reply_text(f"✅ Mode: {RESPONSE_MODE}")
    await delete_user_command(update, context)

# ======================
# 🚀 MAIN
# ======================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("saran", saran_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("sheet", sheet_command))
    app.add_handler(CommandHandler("akses", akses_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Bot Aktif (NPI Project)...")
    app.run_polling()

if __name__ == "__main__":
    main()
