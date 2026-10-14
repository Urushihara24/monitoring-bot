# Deploy (VPS / Docker)

## 1. Preparation

```bash
git clone <repo> monitoring-bot
cd monitoring-bot
cp .env.example .env
nano .env
```

New example configurations start with `DRY_RUN=true`. Keep it enabled until seller IDs, products, competitors and pricing limits have been verified.

## 2. Choose a runtime profile

### Backward-compatible runtime

Use the default Compose file for an existing installation that already relies on host bind mounts:

```bash
docker compose -f docker-compose.yml up -d --build
```

This target intentionally keeps the historical root runtime so existing `./data` and `./logs` ownership does not break during an upgrade.

### Non-root runtime for new / migrated deployments

`docker-compose.secure.yml` builds the `runtime-nonroot` target and runs the application as UID/GID `10001` with Docker named volumes:

```bash
docker compose -f docker-compose.secure.yml up -d --build
```

Use this profile for a new deployment or after intentionally migrating runtime data. Do **not** switch an existing bind-mount deployment blindly: back up `data/` first and copy the required SQLite/runtime files into the named volume using your normal migration/backup procedure.

Verify the effective user:

```bash
docker compose -f docker-compose.secure.yml exec -T monitoring-bot id
```

Expected UID/GID: `10001` (`app`).

## 3. Container lifecycle and health

The image itself defines:

- `STOPSIGNAL SIGTERM`;
- an image-level healthcheck using `python3 healthcheck.py`;
- 60s health interval, 10s timeout, 30s start period, 3 retries.

Both Compose profiles also enable Docker's init process and allow 20 seconds for graceful shutdown before forced termination.

Check health:

```bash
docker ps --filter name=monitoring-pricing-bot

docker inspect \
  --format '{{json .State.Health}}' \
  monitoring-pricing-bot
```

The healthcheck validates active-profile heartbeat and seller API access. An intentionally unconfigured image can therefore report `unhealthy`; this is expected until an active profile and credentials are configured.

## 4. Start / update

Backward-compatible runtime:

```bash
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml logs -f
```

Non-root runtime:

```bash
docker compose -f docker-compose.secure.yml down
docker compose -f docker-compose.secure.yml up -d --build
docker compose -f docker-compose.secure.yml logs -f
```

## 5. Verification

Run the healthcheck inside the container:

```bash
docker compose -f docker-compose.yml exec -T monitoring-bot python3 healthcheck.py
```

Read-only API smoke is safe while `DRY_RUN=true`:

```bash
docker compose -f docker-compose.yml exec -T monitoring-bot \
  python3 scripts/smoke_profiles_api.py --profile all --verify-read
```

Write-capable smoke probes remain blocked while `DRY_RUN=true`.

## 6. Resource sizing

The repository does not impose CPU or memory limits by default because parser load, product count and enabled profiles vary significantly between installations. For a small deployment, **1 vCPU and 512 MiB RAM** is a reasonable starting observation point; use more memory when running multiple profiles/products or when anti-bot/parser fallbacks are active.

Before enforcing container limits, observe real peak RSS/CPU during several pricing cycles and during parser retries. Leave headroom for Python, `curl_cffi`, SQLite and Telegram/network bursts. An OOM-killed pricing process is worse than an unconstrained process on a correctly sized host.

## 7. Cookie refresh

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

## 8. Watchdog

Local watchdog script:

```bash
bash scripts/systemd_watchdog.sh
```

It checks:

- heartbeat (`state.last_cycle`);
- API smoke;
- and restarts `BOT_SERVICE_NAME` when a failure is detected.

## 9. Profiles

Profiles can be enabled independently in `.env`:

- `GGSEL_ENABLED=true/false`
- `DIGISELLER_ENABLED=true/false`

Both profiles can run simultaneously in the same process.
