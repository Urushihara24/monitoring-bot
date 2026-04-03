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
# Docker Compose v2
docker compose down
docker compose up -d --build
docker compose logs -f

# Если на сервере только legacy docker-compose:
docker-compose down
docker-compose up -d --build
docker-compose logs -f
```

## 3. Проверка

```bash
# Проверка healthcheck локально (по state.db)
python3 healthcheck.py

# Проверка API smoke внутри контейнера (использует runtime .env)
docker compose exec -T monitoring-pricing-bot python3 scripts/smoke_profiles_api.py

# Если на сервере только legacy docker-compose:
docker-compose exec -T monitoring-pricing-bot python3 scripts/smoke_profiles_api.py
```

## 4. Cookies refresh

Обновление cookies выполняется внешним способом (браузер/ваш инструмент),
после чего обновите профильный ключ в `.env`:
- `GGSEL_COMPETITOR_COOKIES`
- `DIGISELLER_COMPETITOR_COOKIES`
- (fallback) `COMPETITOR_COOKIES`

```bash
nano .env
```

Рестарт контейнера не требуется: бот на каждом цикле пытается подтянуть свежие
cookies из `.env` (файл примонтирован в контейнер как read-only).

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
