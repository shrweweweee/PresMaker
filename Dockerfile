FROM python:3.11-slim

# LibreOffice + Poppler для QA (рендер слайдов в PNG)
RUN apt-get update && apt-get install -y \
    libreoffice \
    poppler-utils \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
