import os
import asyncio
import subprocess
import tempfile
import shutil
from pathlib import Path
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import yt_dlp

# إعداد logging
logging.basicConfig(level=logging.INFO)

# التوكن (غيّر هنا أو استخدم متغير بيئة)
TOKEN = os.environ.get("BOT_TOKEN", "8385940501:AAHAcJycypwDe97RAX6cF73lo_ZDXURXQlI")

# حقوق المطور
DEVELOPER = "@Bondokkaa0"

# مسار ffmpeg (نفترض أنه في مجلد bin بجانب main.py)
BASE_DIR = Path(__file__).parent
FFMPEG_PATH = BASE_DIR / "bin" / "ffmpeg"
if FFMPEG_PATH.exists():
    os.environ["PATH"] += os.pathsep + str(FFMPEG_PATH.parent)
    logging.info(f"تم العثور على ffmpeg في {FFMPEG_PATH}")
else:
    logging.warning("ffmpeg غير موجود، قد لا تعمل بعض الوظائف")

# دالة بدء
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_msg = (
        f"أهلاً بك {user.first_name}!\n"
        f"يمكنك التحميل من الصفحات التالية:\n"
        f"🎬 يوتيوب\n"
        f"🎵 تيك توك\n"
        f"📘 فيسبوك\n"
        f"📸 انستغرام\n"
        f"🐦 تويتر\n"
        f"وغيرها الكثير...\n\n"
        f"أرسل الرابط وسأعرض لك خيارات التحميل.\n"
        f"يمكنك إرسال عدة روابط في رسائل منفصلة.\n\n"
        f"البوت من تطوير {DEVELOPER}"
    )
    await update.message.reply_text(welcome_msg)

# دالة معالجة الرسائل (الروابط)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text("الرجاء إرسال رابط صحيح يبدأ بـ http:// أو https://")
        return

    # إرسال رسالة انتظار
    msg = await update.message.reply_text("🔍 جاري تحليل الرابط...")

    try:
        # خيارات تحليل الرابط
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(text, download=False)
            # إذا كانت قائمة تشغيل، نأخذ أول فيديو
            if 'entries' in info:
                info = info['entries'][0]

        title = info.get('title', 'بدون عنوان')
        duration = info.get('duration', 0)
        minutes = duration // 60
        seconds = duration % 60

        # تخزين المعلومات في user_data
        context.user_data['info'] = info
        context.user_data['url'] = text

        # أزرار الاختيار
        keyboard = [
            [InlineKeyboardButton("🎥 فيديو (جودة عالية)", callback_data="video_high")],
            [InlineKeyboardButton("🎥 فيديو (جودة منخفضة 480p)", callback_data="video_low")],
            [InlineKeyboardButton("🎵 صوت فقط (MP3)", callback_data="audio")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await msg.edit_text(
            f"✅ تم التحليل:\n"
            f"العنوان: {title}\n"
            f"المدة: {minutes}:{seconds:02d}\n\n"
            f"اختر ما تريد تحميله:",
            reply_markup=reply_markup
        )

    except Exception as e:
        await msg.edit_text(f"❌ حدث خطأ أثناء التحليل:\n{str(e)}")

# دالة معالجة الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    choice = query.data
    user_data = context.user_data
    info = user_data.get('info')
    url = user_data.get('url')

    if not info or not url:
        await query.edit_message_text("⚠️ انتهت صلاحية الجلسة، أرسل الرابط مجدداً.")
        return

    if choice == "cancel":
        await query.edit_message_text("تم إلغاء العملية.")
        return

    await query.edit_message_text("⏳ جاري التحميل والمعالجة... قد يستغرق هذا دقيقة.")

    # إنشاء مجلد مؤقت للتحميل
    download_dir = BASE_DIR / "downloads"
    download_dir.mkdir(exist_ok=True)

    try:
        # تحديد خيارات التحميل حسب الاختيار
        ydl_opts = {
            'outtmpl': str(download_dir / '%(title)s.%(ext)s'),
            'quiet': True,
            'ffmpeg_location': str(FFMPEG_PATH) if FFMPEG_PATH.exists() else None,
        }

        if choice == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif choice == "video_high":
            ydl_opts.update({
                'format': 'best[ext=mp4]/best',
            })
        else:  # video_low
            ydl_opts.update({
                'format': 'best[height<=480][ext=mp4]/best[height<=480]',
            })

        # التحميل
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # البحث عن أحدث ملف في مجلد downloads
        files = list(download_dir.glob("*"))
        if not files:
            raise Exception("لم يتم العثور على الملف المحمل")

        # اختيار أحدث ملف
        latest_file = max(files, key=lambda f: f.stat().st_ctime)

        # التحقق من الحجم
        file_size = latest_file.stat().st_size
        max_size = 50 * 1024 * 1024  # 50 ميجابايت

        if file_size > max_size:
            # محاولة ضغط الفيديو إذا كان الحجم كبيراً (للفيديو فقط)
            if choice != "audio":
                # إعلام المستخدم
                await query.message.reply_text("📦 الملف كبير جداً (>50MB). جاري محاولة ضغطه...")
                # ضغط الفيديو باستخدام ffmpeg
                compressed_file = download_dir / f"compressed_{latest_file.name}"
                # خفض الجودة إلى 480p مع معدل بت معتدل
                cmd = [
                    str(FFMPEG_PATH) if FFMPEG_PATH.exists() else "ffmpeg",
                    "-i", str(latest_file),
                    "-vf", "scale=854:480",
                    "-c:v", "libx264",
                    "-crf", "28",
                    "-preset", "fast",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    str(compressed_file)
                ]
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode == 0 and compressed_file.exists():
                    # حذف الملف الأصلي
                    latest_file.unlink()
                    latest_file = compressed_file
                    file_size = latest_file.stat().st_size
                else:
                    await query.message.reply_text("❌ فشل الضغط. جرب خيار الصوت فقط.")
                    latest_file.unlink()
                    return

            # إذا ما زال الحجم كبيراً بعد الضغط، نقترح الصوت فقط
            if file_size > max_size:
                await query.message.reply_text("❌ حتى بعد الضغط الملف أكبر من 50MB. جرب تحميل الصوت فقط.")
                latest_file.unlink()
                return

        # إرسال الملف
        with open(latest_file, 'rb') as f:
            if choice == "audio":
                await query.message.reply_audio(
                    audio=f,
                    caption=f"تم التحميل بواسطة {DEVELOPER}",
                    title=latest_file.stem
                )
            else:
                await query.message.reply_video(
                    video=f,
                    caption=f"تم التحميل بواسطة {DEVELOPER}",
                    supports_streaming=True
                )

        # حذف الملف بعد الإرسال
        latest_file.unlink()
        await query.message.reply_text("✅ تم التحميل بنجاح!")

    except Exception as e:
        await query.message.reply_text(f"❌ حدث خطأ أثناء التحميل:\n{str(e)}")

def main():
    # إنشاء التطبيق
    app = Application.builder().token(TOKEN).build()

    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    # بدء البوت
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()