FROM python:3.11-slim AS base

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

STOPSIGNAL SIGTERM
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python3", "healthcheck.py"]
CMD ["python3", "-m", "src"]

# Optional hardened target for deployments that do not depend on host bind-mount
# ownership. Use named volumes (see docker-compose.secure.yml) so the app user
# owns the writable runtime directories.
FROM base AS runtime-nonroot

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app/data /app/logs

USER app

# Backward-compatible default target. Existing bind-mount deployments keep the
# historical root runtime until they intentionally migrate to runtime-nonroot.
FROM base AS runtime
