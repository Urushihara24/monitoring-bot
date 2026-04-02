FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей системы
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Установка Chromium для Playwright (обход anti-bot)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-kacst \
    fonts-freefont-ttf \
    libxss1 \
    libgtk2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/share/fonts \
    && fc-cache -f

# Selenium + Chrome (для обновления cookies)
# Добавляем репозиторий Google и устанавливаем Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y --fix-missing --no-install-recommends \
        google-chrome-stable \
        chromium-chromedriver && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/google-chrome \
    CHROMEDRIVER=/usr/bin/chromedriver

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir stealth-requests

# Установка Playwright браузеров
RUN playwright install chromium
RUN playwright install-deps chromium 2>/dev/null || true

# Копирование кода
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY healthcheck.py ./
COPY .env .env.example ./

# Создание директорий
RUN mkdir -p /app/data /app/logs

# Запуск бота
CMD ["python3", "-m", "src"]
