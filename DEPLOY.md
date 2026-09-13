# Deploy (VPS / Docker)

## 1. Preparation

```bash
git clone <repo> monitoring-bot
cd monitoring-bot
cp .env.example .env
nano .env
```

## 2. Start the container

```bash
# Docker Compose v2
docker compose down
docker compose up -d --build
docker compose logs -f

# If the server only has legacy docker-compose:
docker-compose down
docker-compose up -d --build
docker-compose logs -f
```

## 3. Verification

```bash
# Run the healthcheck locally against state.db
python3 healthcheck.py

# Run API smoke inside the container using the runtime .env
docker compose exec -T monitoring-pricing-bot python3 scripts/smoke_profiles_api.py

# If the server only has legacy docker-compose:
docker-compose exec -T monitoring-pricing-bot python3 scripts/smoke_profiles_api.py
```

## 4. Cookie refresh

Refresh cookies externally using a browser or your own tooling, then update the profile-specific key in `.env`:
- `GGSEL_COMPETITOR_COOKIES`
- `DIGISELLER_COMPETITOR_COOKIES`
- fallback: `COMPETITOR_COOKIES`

```bash
nano .env
```

A container restart is not required: on every cycle the bot attempts to reload fresh cookies from `.env`, which is mounted read-only into the container.
If the env file is stored elsewhere, configure `ENV_FILE_PATH=/path/to/.env`.
If old cookies have already expired, the bot can clear them from runtime state automatically after a successful request without cookies. The `.env` file itself is not modified.

## 5. Watchdog

Local watchdog script:

```bash
bash scripts/systemd_watchdog.sh
```

It checks:
- heartbeat (`state.last_cycle`)
- API smoke
- and restarts `BOT_SERVICE_NAME` when a failure is detected

## 6. Profiles

Profiles can be enabled independently in `.env`:
- `GGSEL_ENABLED=true/false`
- `DIGISELLER_ENABLED=true/false`

Both profiles can run simultaneously in the same process.
