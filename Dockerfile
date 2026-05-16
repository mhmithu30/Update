FROM python:3.11-slim

# Chrome install
RUN apt-get update && apt-get install -y \
    wget curl gnupg unzip \
    chromium chromium-driver \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "combined_bot.py"]
