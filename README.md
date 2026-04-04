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

Поведение cookies:
- бот синхронизирует cookies из `.env` на каждом цикле без рестарта
- если cookies протухли и парсинг без cookies успешен,
  runtime cookies очищаются автоматически (чтобы не повторять битый запрос)
- если retry без cookies тоже неуспешен, stale runtime cookies сбрасываются,
  чтобы в следующем цикле не застревать на `401/403` с тем же значением
- путь к env-файлу можно переопределить через `ENV_FILE_PATH`

## Быстрый старт (локально)

```bash
python3 -m venv .venv
source .venv/bin/activate
# runtime deps
pip install -r requirements.txt
# для запуска тестов/линтеров
pip install -r requirements-dev.txt
cp .env.example .env
```

Минимум в `.env`:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_IDS`
- для включённого профиля: `*_API_KEY`/`*_ACCESS_TOKEN`, `*_SELLER_ID`, `*_PRODUCT_ID`
- если `*_API_KEY` это JWT access token, задайте `*_API_SECRET` для `ApiLogin`
  (автообновление токена)
- `COMPETITOR_URLS` (или профильный список для DigiSeller)
- cookies конкурента: `GGSEL_COMPETITOR_COOKIES` / `DIGISELLER_COMPETITOR_COOKIES`
  (если не заданы, используется общий `COMPETITOR_COOKIES`)
- при нестандартном запуске можно явно задать `ENV_FILE_PATH`

Если у включённого профиля не задан `*_PRODUCT_ID`, такой профиль не
запускается (fail-safe защита от шумных циклов и пустых API-обновлений).

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
- `DIGISELLER_API_SECRET` (если `DIGISELLER_API_KEY` хранится как JWT)
- `DIGISELLER_SELLER_ID`
- `DIGISELLER_PRODUCT_ID`

Рекомендуемо сразу указать:
- `DIGISELLER_COMPETITOR_URLS` (если нужен авто-режим мониторинга)
- `DIGISELLER_REQUIRE_API_ON_START=true` (чтобы процесс не стартовал с битым API)

Опционально для авто-инструкций в переписке заказа (DigiSeller):
- `DIGISELLER_CHAT_AUTOREPLY_ENABLED=true`
- `DIGISELLER_CHAT_AUTOREPLY_PRODUCT_IDS=5077639,5104800`
- `DIGISELLER_CHAT_AUTOREPLY_INTERVAL_SECONDS=30`
- `DIGISELLER_CHAT_AUTOREPLY_DEDUPE_BY_MESSAGES=true`
- `DIGISELLER_CHAT_AUTOREPLY_LOOKBACK_MESSAGES=30`
- `DIGISELLER_CHAT_AUTOREPLY_SENT_TTL_DAYS=30`
- `DIGISELLER_CHAT_AUTOREPLY_CLEANUP_EVERY_HOURS=24`
- `DIGISELLER_CHAT_TEMPLATE_RU_ALREADY`, `DIGISELLER_CHAT_TEMPLATE_RU_ADD`
- `DIGISELLER_CHAT_TEMPLATE_EN_ALREADY`, `DIGISELLER_CHAT_TEMPLATE_EN_ADD`

Если шаблоны не заданы, бот берёт текст из полей товара:
- для RU: `info_ru`/`instruction_ru`/`add_info_ru` с fallback на `info`/`instruction`/`add_info`
- для EN: `info_en`/`instruction_en`/`add_info_en` с fallback на `info`/`instruction`/`add_info`

Для режима `добавит` приоритет у `add_info*`, иначе у `info*`.
Инструкция в чат заказа отправляется один раз (с dedupe по сообщениям).
Перед отправкой бот проверяет права chat API; при нехватке прав
отправка не выполняется, причина пишется в `/diag` (`Chat perms`).

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
- `/status` — статус активного профиля
- `/status <profile>` — статус выбранного профиля
- `/diag` — диагностика активного профиля
- `/diag <profile>` — диагностика выбранного профиля
- `/smoke` — безопасный API smoke для активного профиля (read + noop write + verify)
  для DigiSeller дополнительно показывает `token/perms`.
  Можно указать профиль аргументом: `/smoke ggsel` или `/smoke digiseller`.

Алиасы профилей в аргументах команд:
- GGSEL: `gg`, `ggsel`
- DigiSeller: `digi`, `dg`, `digiseller`, `plati`

Главное меню:
- `📊 Статус`
- `🔔 Авто: ВКЛ/ВЫКЛ`
- `🧩 Профиль`
- `⚙ Настройки`

При смене профиля незавершённый ввод (pending действие в настройках)
сбрасывается автоматически, чтобы исключить применение значения в другой профиль.

Настройки:
- `⬆ +0.01₽` / `⬇ -0.01₽` (ручная корректировка)
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

Проверка GGSEL `apilogin` (использует `GGSEL_API_SECRET` или fallback на
`GGSEL_API_KEY`):

```bash
python3 scripts/check_apilogin.py
```

Если `GGSEL_API_KEY` у вас JWT access token, обязательно задайте
`GGSEL_API_SECRET`, иначе `apilogin` недоступен.

Выпуск access token через `apilogin`:

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

Если профиль запрошен явно (`--profile ggsel|digiseller`) и выключен в `.env`,
скрипт завершится с ошибкой (код `1`).

С реальным тестовым изменением и rollback:

```bash
python3 scripts/smoke_profiles_api.py --profile digiseller --mutate --delta 0.0001 --verify-read
```

Smoke прав чатов/переписки (без отправки сообщений):

```bash
python3 scripts/smoke_chat_api.py --profile all
```

С безопасной POST-пробой `chat.send` (id_i=0):

```bash
python3 scripts/smoke_chat_api.py --profile digiseller --send-probe
```

Smoke доступности текстов инструкций (без отправки сообщений):

```bash
python3 scripts/smoke_instruction_data.py --profile all
```

## Тесты и проверки

```bash
pytest -q
python3 -m compileall src scripts healthcheck.py
```

Если у вас Python 3.14+, используйте версии из `requirements-dev.txt`
(`pytest==8.4.2`, `pytest-asyncio==1.2.0`), чтобы избежать deprecated warning
от старого `pytest-asyncio`.

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
