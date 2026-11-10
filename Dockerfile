FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .

# ntgcalls force-upgrade taaki stale wheel ka InputMode issue kabhi na aaye
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -U ntgcalls

COPY . .

CMD ["python", "main.py"]
