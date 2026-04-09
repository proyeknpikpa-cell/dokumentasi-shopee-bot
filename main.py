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

TOKEN = os.getenv("BOT_TOKEN")

# ===== START COMMAND =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot dokumentasi aktif!")

# ===== AMBIL KEGIATAN DARI CAPTION =====
def extract_kegiatan(text):
    if not text:
        return None

    match = re.search(r'Kegiatan\s*:\s*(.*)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

# ===== AMBIL TANGGAL =====
def extract_date(text):
    try:
        match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', text)
        if match:
            date_obj = datetime.strptime(match.group(1), "%d %B %Y")
            return date_obj.strftime("%Y-%m-%d")
    except:
        pass

    return datetime.now().strftime("%Y-%m-%d")

# ===== HANDLE FOTO =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    caption = message.caption or ""

    kegiatan = extract_kegiatan(caption)
    tanggal = extract_date(caption)

    if kegiatan:
        filename = f"{tanggal}_{kegiatan}.jpg"
    else:
        filename = f"{tanggal}.jpg"

    filename = filename.replace(" ", "_")

    photo = message.photo[-1]
    file = await photo.get_file()

    os.makedirs("downloads", exist_ok=True)
    path = f"downloads/{filename}"

    await file.download_to_drive(path)

    await message.reply_text(f"📁 Foto disimpan sebagai:\n{filename}")

# ===== RUN BOT =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

print("Bot running...")
app.run_polling()
