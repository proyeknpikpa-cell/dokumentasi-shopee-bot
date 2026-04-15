import os
import re
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import cloudinary
import cloudinary.uploader
import google.generativeai as genai

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PANDUAN_URL = "https://proyeknpikpa-cell.github.io/panduan-bot-npi/"

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

# ======================
# ⚙️ GLOBAL STATE & AI CONFIG
# ======================
RESPONSE_MODE = "full"
ITEMS_PER_PAGE = 10

# Inisialisasi AI dengan pengecekan aman
model_ai = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model_ai = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"⚠️ Gagal konfigurasi Gemini: {e}")

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

private_key = GOOGLE_PRIVATE_KEY.replace("\\n", "\n") if GOOGLE_PRIVATE_KEY else ""

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

# ======================
# 🛠️ HELPER & AI LOGIC
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

async def ai_extract_caption(raw_caption):
    """
    Menggunakan AI untuk mengekstraksi Kegiatan dan Lokasi saja.
    Dilengkapi dengan retry logic agar bot tidak crash jika API error.
    """
    if not model_ai or not raw_caption:
        return raw_caption
    
    prompt = f"""
    Ekstrak informasi penting dari teks laporan proyek berikut.
    Ambil HANYA bagian 'Kegiatan' dan 'Lokasi' saja.
    Format jawaban harus strictly: "Kegiatan: [isi] | Lokasi: [isi]"
    Jika informasi tidak ditemukan, tulis "-".
    Jangan berikan kalimat pengantar atau penjelasan apa pun.

    Teks:
    {raw_caption}
    """
    
    # Retry logic (Exponential Backoff)
    delays = [1, 2, 4]
    for delay in delays:
        try:
            # Menggunakan loop event-driven agar tidak memblokir bot
            response = await asyncio.to_thread(model_ai.generate_content, prompt)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"🤖 AI Retry log: {e}")
            await asyncio.sleep(delay)
            
    # Jika semua percobaan gagal, kembalikan teks asli (fallback aman)
    return raw_caption

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
        
        # PROSES AI: Ekstraksi hanya Kegiatan & Lokasi
        if caption_raw.strip():
            # Kita panggil AI di sini
            caption_final = await ai_extract_caption(caption_raw)
            clean = clean_text(caption_raw[:30])
            base_name = f"{clean}_{timestamp}"
        else:
            base_name = f"foto_{timestamp}"
            caption_final = "-"
            
        photo = message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_path = f"/tmp/{base_name}.jpg"
        await file.download_to_drive(file_path)
        
        # Upload ke Cloudinary
        result = cloudinary.uploader.upload(file_path, folder=folder_name, public_id=base_name, overwrite=True)
        url = result["secure_url"]
        
        # Simpan ke Google Sheet
        save_photo_to_sheet(date, time, month, sender, caption_final, url)
        
        # Kirim Respon
        if RESPONSE_MODE == "simple":
            await message.reply_text("✅ Foto berhasil diupload")
        else:
            await message.reply_text(
                f"✅ **FOTO BERHASIL**\n"
                f"👤 {sender}\n"
                f"📝 {caption_final}\n"
                f"🔗 [Lihat Foto]({url})",
                parse_mode="Markdown"
            )
            
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        print(f"Error Photo: {e}")
        await message.reply_text(f"❌ TERJADI KENDALA: Pastikan format caption benar atau coba lagi nanti.")

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
        temp_path = f"/tmp/{timestamp}_{original_name}"
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
        print(f"Error Doc: {e}")
        await message.reply_text(f"❌ Gagal mengupload dokumen.")

# ======================
# 📋 COMMANDS
# ======================
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📄 Cek Dokumen", callback_data=f"menu_doc|{user_id}")],
        [InlineKeyboardButton("📊 Statistik Foto", callback_data=f"jumlah|{user_id}")],
        [InlineKeyboardButton("📖 Panduan Bot", url=PANDUAN_URL)],
        [InlineKeyboardButton("👨‍💻 Developer", callback_data=f"dev|{user_id}")],
        [InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{user_id}")]
    ]
    await update.message.reply_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))
    await delete_user_command(update, context)

async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **Link Dokumentasi**\n"
        f"🔗 [Klik untuk Membuka Sheet]({SHEET_URL})",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await delete_user_command(update, context)

async def cekdokumen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("⚠️ Gunakan format: `/cekdokumen @username` atau `/cekdokumen Nama Pengirim`", parse_mode="Markdown")
        return

    target_sender = " ".join(context.args).strip()
    await show_list_by_sender(update, context, target_sender, 0, user_id, is_callback=False)
    await delete_user_command(update, context)

async def akses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user):
        await update.message.reply_text("❌ Akses ditolak.")
        await delete_user_command(update, context)
        return

    if not context.args:
        await update.message.reply_text("⚠️ Gunakan format: `/akses email@gmail.com`", parse_mode="Markdown")
        await delete_user_command(update, context)
        return

    email = context.args[0]
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❌ Format email tidak valid.")
        await delete_user_command(update, context)
        return

    status_msg = await update.message.reply_text(f"⏳ Memproses akses untuk `{email}`...", parse_mode="Markdown")
    try:
        sheet_instance.share(email, perm_type='user', role='writer', notify=True)
        await status_msg.edit_text(f"✅ Berhasil! `{email}` sekarang telah menjadi **Editor**.", parse_mode="Markdown")
    except Exception as e:
        await status_msg.edit_text(f"❌ Gagal: {str(e)}")
    
    await delete_user_command(update, context)

# ======================
# 🎯 CALLBACK & VIEW HELPERS
# ======================
async def show_list_by_sender(update_or_query, context, sender_name, offset, owner_id, is_callback=True):
    all_rows = sheet_doc.get_all_values()[1:]
    filtered = [r for r in all_rows if len(r) > 3 and r[3].lower() == sender_name.lower()]
    filtered.reverse()

    total = len(filtered)
    start = offset
    end = offset + ITEMS_PER_PAGE
    current_list = filtered[start:end]

    msg_obj = update_or_query.callback_query if is_callback else update_or_query.message

    if not current_list:
        text = f"📭 Pengirim `{sender_name}` belum pernah mengunggah dokumen."
        kb = [[InlineKeyboardButton("❌ Tutup", callback_data=f"close|{owner_id}")]]
        if is_callback:
            await msg_obj.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            await msg_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        return

    text = f"👤 **DOKUMEN DARI: {sender_name}**\n"
    text += f"_(Menampilkan {start+1}-{min(end, total)} dari {total} file)_\n\n"

    for i, row in enumerate(current_list, start=1):
        name = row[4]
        cat = row[5]
        link = row[6]
        text += f"{i}. **{name}** ({cat})\n🔗 [Buka Dokumen]({link})\n\n"

    buttons = []
    nav_row = []
    if end < total:
        nav_row.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"lsender_{sender_name}_{end}|{owner_id}"))
    if offset > 0:
        nav_row.append(InlineKeyboardButton("➡️ Terbaru", callback_data=f"lsender_{sender_name}_{max(0, offset-ITEMS_PER_PAGE)}|{owner_id}"))
    
    if nav_row: buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("🔙 Kembali ke Menu", callback_data=f"back_main|{owner_id}")])
    buttons.append([InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{owner_id}")])

    if is_callback:
        await msg_obj.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
    else:
        await msg_obj.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw_data = query.data
    parts = raw_data.split("|")
    
    action_data = parts[0]
    owner_id = int(parts[1]) if len(parts) > 1 else None
    current_user_id = query.from_user.id

    if owner_id and current_user_id != owner_id:
        await query.answer("⚠️ Menu ini hanya untuk pengguna yang memanggilnya!", show_alert=True)
        return

    if action_data == "close":
        await query.answer("Menu ditutup")
        await query.delete_message()
        return

    await query.answer()

    if action_data == "menu_doc":
        kb = [
            [InlineKeyboardButton("📕 PDF", callback_data=f"list_PDF_0|{owner_id}")],
            [InlineKeyboardButton("📘 WORD", callback_data=f"list_WORD_0|{owner_id}")],
            [InlineKeyboardButton("📗 EXCEL", callback_data=f"list_EXCEL_0|{owner_id}")],
            [InlineKeyboardButton("📙 PPT", callback_data=f"list_PPT_0|{owner_id}")],
            [InlineKeyboardButton("👤 Cari Pengirim", callback_data=f"search_sender|{owner_id}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data=f"back_main|{owner_id}")],
            [InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{owner_id}")]
        ]
        await query.edit_message_text("Pilih metode pencarian dokumen:", reply_markup=InlineKeyboardMarkup(kb))

    elif action_data == "search_sender":
        all_rows = sheet_doc.get_all_values()[1:]
        senders = sorted(list(set(row[3] for row in all_rows if len(row) > 3 and row[3])))
        
        if not senders:
            await query.edit_message_text("📭 Belum ada data pengirim.", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_doc|{owner_id}")]]))
            return

        text = "👥 **Pilih Pengirim:**"
        kb = []
        for s in senders:
            kb.append([InlineKeyboardButton(f"👤 {s}", callback_data=f"lsender_{s}_0|{owner_id}")])
        kb.append([InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_doc|{owner_id}")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif action_data.startswith("lsender_"):
        _, rest = action_data.split("_", 1)
        parts_val = rest.rsplit("_", 1)
        s_name = parts_val[0]
        offset = int(parts_val[1])
        await show_list_by_sender(update, context, s_name, offset, owner_id, is_callback=True)

    elif action_data.startswith("list_"):
        _, category, offset = action_data.split("_")
        offset = int(offset)
        all_rows = sheet_doc.get_all_values()[1:] 
        filtered = [r for r in all_rows if len(r) > 5 and r[5] == category]
        filtered.reverse() 
        total = len(filtered)
        start = offset
        end = offset + ITEMS_PER_PAGE
        current_list = filtered[start:end]

        if not current_list:
            await query.edit_message_text(f"📭 Belum ada dokumen {category}", 
                                         reply_markup=InlineKeyboardMarkup([
                                             [InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_doc|{owner_id}")],
                                             [InlineKeyboardButton("❌ Tutup", callback_data=f"close|{owner_id}")]
                                         ]))
            return

        text = f"📂 **DAFTAR DOKUMEN {category}**\n"
        text += f"_(Menampilkan {start+1}-{min(end, total)} dari {total} file)_\n\n"
        for i, row in enumerate(current_list, start=1):
            name = row[4] 
            link = row[6] 
            text += f"{i}. **{name}**\n🔗 [Buka Dokumen]({link})\n\n"

        buttons = []
        nav_row = []
        if end < total:
            nav_row.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"list_{category}_{end}|{owner_id}"))
        if offset > 0:
            nav_row.append(InlineKeyboardButton("➡️ Terbaru", callback_data=f"list_{category}_{max(0, offset-ITEMS_PER_PAGE)}|{owner_id}"))
        if nav_row: buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("🔙 Pilih Jenis Lain", callback_data=f"menu_doc|{owner_id}")])
        buttons.append([InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{owner_id}")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    elif action_data == "back_main":
        keyboard = [
            [InlineKeyboardButton("📄 Cek Dokumen", callback_data=f"menu_doc|{owner_id}")],
            [InlineKeyboardButton("📊 Statistik Foto", callback_data=f"jumlah|{owner_id}")],
            [InlineKeyboardButton("📖 Panduan Bot", url=PANDUAN_URL)],
            [InlineKeyboardButton("👨‍💻 Developer", callback_data=f"dev|{owner_id}")],
            [InlineKeyboardButton("❌ Tutup Menu", callback_data=f"close|{owner_id}")]
        ]
        await query.edit_message_text("📋 Menu Bot:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif action_data == "jumlah":
        today = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d-%m-%Y")
        rows = sheet_photo.get_all_values()
        count = sum(1 for r in rows if r and r[0] == today)
        await query.edit_message_text(f"📊 Hari ini ada {count} foto diupload.",
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"back_main|{owner_id}")]]))

    elif action_data == "dev":
        await query.edit_message_text(f"👨‍💻 Developer: {OWNER_USERNAME}",
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"back_main|{owner_id}")]]))

# ======================
# 💬 SARAN & MODE
# ======================
async def saran_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("❗ Tulis saran setelah /saran")
        return
    await update.message.reply_text("✅ Saran terkirim!")
    await delete_user_command(update, context)

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
    app.add_handler(CommandHandler("cekdokumen", cekdokumen_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Bot Aktif (NPI Project)...")
    app.run_polling()

if __name__ == "__main__":
    main()
