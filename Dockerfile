FROM python:3.11-slim

# System dependencies install karo (FFmpeg zaroori hai)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Working directory set karo
WORKDIR /app

# Saari files copy karo
COPY . .

# Userbot folder mein jao aur dependencies install karo
WORKDIR /app/userbot-main
RUN pip install --no-cache-dir -r requirements.txt

# Bot start karo
CMD ["python", "main.py"]
