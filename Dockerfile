# استخدام صورة Python رسمية
FROM python:3.11-slim

# تثبيت ffmpeg وأدوات النظام اللازمة
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# إنشاء مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات أولاً (للاستفادة من الـ caching)
COPY requirements.txt .

# تثبيت متطلبات Python
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# تعيين متغير البيئة (سيتم تمريره من Railway)
ENV BOT_TOKEN=${BOT_TOKEN}

# أمر التشغيل
CMD ["python", "main.py"]
