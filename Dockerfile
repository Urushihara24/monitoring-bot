FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

LABEL org.opencontainers.image.source="https://github.com/Urushihara24/monitoring-bot"
LABEL org.opencontainers.image.description="Auto-pricing and marketplace monitoring bot for GGSEL and DigiSeller"

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY healthcheck.py ./
COPY .env.example ./

RUN mkdir -p /app/data /app/logs

CMD ["python3", "-m", "src"]
