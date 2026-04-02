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
