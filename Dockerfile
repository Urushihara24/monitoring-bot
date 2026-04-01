FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей системы
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir stealth-requests

# Копирование кода
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY .env .env.example ./

# Создание директорий
RUN mkdir -p /app/data /app/logs

# Запуск бота
CMD ["python3", "-m", "src.main"]
