# Deploy (VPS / Docker)

## 1. Подготовка

```bash
git clone <repo> monitoring-bot
cd monitoring-bot
cp .env.example .env
nano .env
```

## 2. Запуск контейнера

```bash
docker compose down
docker compose up -d --build
docker compose logs -f
```

## 3. Проверка

```bash
python3 healthcheck.py
python3 scripts/smoke_profiles_api.py
pytest
```

## 4. Cookies refresh

Первичная выдача cookies:

```bash
python3 scripts/update_competitor_cookies.py --interactive
```

Фоновое обновление:

```bash
bash scripts/cron_update_cookies.sh
```

## 5. Watchdog

Локальный watchdog-скрипт:

```bash
bash scripts/systemd_watchdog.sh
```

Он проверяет:
- heartbeat (`state.last_cycle`)
- smoke API
- при проблеме перезапускает `BOT_SERVICE_NAME`

## 6. Профили

В `.env` можно включать профили отдельно:
- `GGSEL_ENABLED=true/false`
- `DIGISELLER_ENABLED=true/false`

Оба профиля могут работать одновременно в одном процессе.
