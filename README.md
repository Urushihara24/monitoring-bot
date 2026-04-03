# Auto-Pricing Bot (GGSEL + DigiSeller)

Telegram-бот для мониторинга цен конкурентов и автообновления цены товара через API продавца.

Поддерживаются независимые профили:
- `ggsel`
- `digiseller`

Для каждого профиля хранятся отдельно:
- API-ключи/токен
- ID товара
- список конкурентов
- runtime-настройки
- state/история/алерты

## Ключевая логика

Базовое правило цены:
- `my_price = competitor_min - UNDERCUT_VALUE`
- по умолчанию `UNDERCUT_VALUE=0.0051`
- пример: конкурент `0.3400` -> мы `0.3349`

Ограничения и защита:
- `MIN_PRICE`, `MAX_PRICE`
- `MODE=FIXED|STEP_UP` при упоре в нижнюю границу
- `MAX_DOWN_STEP` для ограничения резкого падения
- `FAST_REBOUND_DELTA` + bypass cooldown для быстрого отката вверх

Идемпотентность апдейтов:
- при неизменной цене конкурента повторный API update не выполняется
- если целевая цена уже была применена, бот делает `skip` (без лишнего шума)
- если у профиля пустой список конкурентов, цикл делает безопасный `skip`
  без отправки error-алертов
- профиль может работать и без `COMPETITOR_URLS` (ручные операции и API smoke)

Точность цен:
- расчёт/сохранение/отображение в боте: `4` знака после запятой
- в GGSEL update payload цена отправляется в формате `0.0000`
- API чтение у площадки может возвращать округлённое значение, это учитывается

## Как парсится конкурент

Pipeline:
1. `stealth_requests` + HTML (`BeautifulSoup`)
2. извлечение unit-price (`unitsToPay / unitsToGet`) если доступно
3. fallback по CSS-селекторам цены
4. fallback на публичный endpoint: `https://api4.ggsel.com/goods/<id>`
   (используется только для доменов `ggsel.*`)

Что пишется в state:
- `last_competitor_min`
- `last_competitor_url`
- `last_competitor_method`
- `last_competitor_parse_at`
- ошибки/причины блокировок парсера

## Быстрый старт (локально)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Минимум в `.env`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_IDS`
- для включённого профиля: `*_API_KEY`/`*_ACCESS_TOKEN`, `*_SELLER_ID`, `*_PRODUCT_ID`
- `COMPETITOR_URLS` (или профильный список для DigiSeller)
- cookies конкурента: `GGSEL_COMPETITOR_COOKIES` / `DIGISELLER_COMPETITOR_COOKIES`
  (если не заданы, используется общий `COMPETITOR_COOKIES`)

Профильные дефолты DigiSeller (опционально):
- `DIGISELLER_MIN_PRICE`
- `DIGISELLER_MAX_PRICE`
- `DIGISELLER_DESIRED_PRICE`
- `DIGISELLER_UNDERCUT_VALUE`
- `DIGISELLER_MODE`
- `DIGISELLER_FIXED_PRICE`
- `DIGISELLER_STEP_UP_VALUE`
- `DIGISELLER_WEAK_PRICE_CEIL_LIMIT`
- `DIGISELLER_POSITION_FILTER_ENABLED`
- `DIGISELLER_WEAK_POSITION_THRESHOLD`
- `DIGISELLER_CHECK_INTERVAL`
- `DIGISELLER_FAST_CHECK_INTERVAL_MIN`
- `DIGISELLER_FAST_CHECK_INTERVAL_MAX`
- `DIGISELLER_COOLDOWN_SECONDS`
- `DIGISELLER_IGNORE_DELTA`
- `DIGISELLER_NOTIFY_SKIP`
- `DIGISELLER_NOTIFY_SKIP_COOLDOWN_SECONDS`
- `DIGISELLER_NOTIFY_COMPETITOR_CHANGE`
- `DIGISELLER_COMPETITOR_CHANGE_DELTA`
- `DIGISELLER_COMPETITOR_CHANGE_COOLDOWN_SECONDS`
- `DIGISELLER_UPDATE_ONLY_ON_COMPETITOR_CHANGE`
- `DIGISELLER_NOTIFY_PARSER_ISSUES`
- `DIGISELLER_PARSER_ISSUE_COOLDOWN_SECONDS`
- `DIGISELLER_HARD_FLOOR_ENABLED`
- `DIGISELLER_MAX_DOWN_STEP`
- `DIGISELLER_FAST_REBOUND_DELTA`
- `DIGISELLER_FAST_REBOUND_BYPASS_COOLDOWN`

Эти значения применяются только если соответствующий runtime-ключ ещё не был
задан ранее в БД (`runtime_settings`).

### Включение DigiSeller профиля

Минимальный набор переменных:
- `DIGISELLER_ENABLED=true`
- `DIGISELLER_API_KEY` (или `DIGISELLER_ACCESS_TOKEN`)
- `DIGISELLER_SELLER_ID`
- `DIGISELLER_PRODUCT_ID`

Рекомендуемо сразу указать:
- `DIGISELLER_COMPETITOR_URLS` (если нужен авто-режим мониторинга)
- `DIGISELLER_REQUIRE_API_ON_START=true` (чтобы процесс не стартовал с битым API)

Быстрая проверка только DigiSeller:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --verify-read
```

Запуск:

```bash
python3 -m src
```

## Запуск в Docker

```bash
docker compose up -d --build
docker compose logs -f
```

## Telegram управление (reply-клавиатура)

Команды:
- `/start`
- `/status`
- `/smoke` — безопасный API smoke для активного профиля (read + noop write + verify)
  для DigiSeller дополнительно показывает `token/perms`.

Главное меню:
- `📊 Статус`
- `⬆ +0.01₽` / `⬇ -0.01₽`
- `🔔 Авто: ВКЛ/ВЫКЛ`
- `🧩 Профиль`
- `⚙ Настройки`
- `🩺 Диагностика`

Настройки:
- `🎯 Цена` (`DESIRED_PRICE`)
- `➖ Шаг` (`UNDERCUT_VALUE`)
- `📉 Мин` (`MIN_PRICE`)
- `📈 Макс` (`MAX_PRICE`)
- `⏱ Интервал` (`CHECK_INTERVAL`)
- `🔀 Режим` (`FIXED`/`STEP_UP`)
- `📍 Позиция`
- `🔗 Добавить URL` / `🗑 Удалить URL`
- `🧾 История`

## Полезные скрипты

Проверка GGSEL apilogin:

```bash
python3 scripts/check_apilogin.py
```

Выпуск access token через API key:

```bash
python3 scripts/issue_access_token.py
```

Smoke API активных профилей:

```bash
python3 scripts/smoke_profiles_api.py
```

Проверить только DigiSeller:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller
```

С реальным тестовым изменением и rollback:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --mutate --delta 0.0001 --verify-read
```

## Тесты и проверки

```bash
pytest -q
python3 -m compileall src healthcheck.py
```

## Структура кода

- `src/main.py` — запуск профилей и orchestration
- `src/scheduler.py` — цикл парсинг -> расчёт -> update/skip
- `src/logic.py` — бизнес-формулы цены
- `src/rsc_parser.py` — парсер конкурента
- `src/api_client.py` — GGSEL API клиент
- `src/digiseller_client.py` — DigiSeller API клиент
- `src/telegram_bot.py` — Telegram reply UI + handlers
- `src/storage.py` — SQLite state/runtime/history/alerts

## Источники API

- GGSEL Seller API: `https://seller.ggsel.com/docs/seller-api-v-1`
- DigiSeller API: `https://my.digiseller.com/inside/api.asp`
