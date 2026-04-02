# Auto-Pricing Bot (GGSEL + DigiSeller)

Бот мониторит цену конкурента по ссылкам, рассчитывает целевую цену и обновляет цену товара через API площадки.

Поддерживается 2 независимых профиля:
- `ggsel`
- `digiseller`

У каждого профиля отдельные:
- API-ключи/токен
- товар
- список конкурентов
- авто-режим
- runtime-настройки
- история и алерты

## Что реализовано
- Reply-клавиатура Telegram (без inline-кнопок).
- Профильный режим в Telegram (`🧩 Профиль`).
- Быстрый runtime-интервал (`CHECK_INTERVAL`) через кнопку `⏱ Интервал`.
- Парсер конкурента на `stealth_requests + BeautifulSoup` с fallback на публичный `api4.ggsel.com/goods/<id>`.
- Обновление цены только при фактическом изменении цены конкурента.
- Автоподхват новых cookies из `.env` без перезапуска процесса.
- Авторизация GGSEL/DigiSeller через `/apilogin` (sign = `sha256(api_key + timestamp)`).
- Защита от убытков:
  - hard floor
  - ограничение резких снижений (`MAX_DOWN_STEP`)
  - быстрый откат вверх (`FAST_REBOUND_DELTA` + bypass cooldown)
- Профильный `SQLite` state/runtime/alerts.
- CI (GitHub Actions) + тесты `pytest`.

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполни `.env` минимум:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_IDS`
- для включённого профиля: `*_API_KEY`/`*_ACCESS_TOKEN`, `*_SELLER_ID`, `*_PRODUCT_ID`, `*_COMPETITOR_URLS`

Запуск:

```bash
python3 -m src
```

## Профили

### GGSEL
- включение: `GGSEL_ENABLED=true`
- API: `https://seller.ggsel.com/api_sellers/api`

### DigiSeller
- включение: `DIGISELLER_ENABLED=true`
- API: `https://api.digiseller.com/api`

## Telegram управление

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

## Тесты

```bash
pytest
python -m compileall src healthcheck.py
```

## Docker

```bash
docker compose up -d --build
docker compose logs -f
```

## Важные файлы
- `/Users/vsevolod/Documents/Monitoring/src/main.py`
- `/Users/vsevolod/Documents/Monitoring/src/scheduler.py`
- `/Users/vsevolod/Documents/Monitoring/src/rsc_parser.py`
- `/Users/vsevolod/Documents/Monitoring/src/storage.py`
- `/Users/vsevolod/Documents/Monitoring/src/telegram_bot.py`
- `/Users/vsevolod/Documents/Monitoring/src/api_client.py`
- `/Users/vsevolod/Documents/Monitoring/src/digiseller_client.py`

## API источники
- GGSEL Seller API: `https://seller.ggsel.com/docs/seller-api-v-1`
- DigiSeller API: `https://my.digiseller.com/inside/api.asp`
  - Products/categories: `https://my.digiseller.com/inside/api_catgoods.asp`
  - Product edit: `https://my.digiseller.com/inside/api_goods.asp`
