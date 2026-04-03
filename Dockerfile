FROM python:3.11-slim

WORKDIR /app

# Копирование requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY healthcheck.py ./
COPY .env.example ./

# Создание директорий
RUN mkdir -p /app/data /app/logs

# Запуск бота
CMD ["python3", "-m", "src"]
