# 🤖 Auto-Pricing Bot для GGSEL Marketplace

Полноценный auto-pricing engine с чёткой бизнес-логикой.

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
pip3 install -r requirements.txt --break-system-packages
```

### 2. Настройка

Отредактируйте `.env`:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_ADMIN_IDS=1481790360

# GGSEL API
GGSEL_API_KEY=your_api_secret_here
GGSEL_ACCESS_TOKEN=
GGSEL_PRODUCT_ID=4697439
GGSEL_LANG=ru-RU

# Конкуренты
COMPETITOR_URLS=https://ggsel.net/catalog/product/competitor-12345
COMPETITOR_COOKIES=
SELENIUM_USE_REAL_PROFILE=false
SELENIUM_CHROME_USER_DATA_DIR=
SELENIUM_CHROME_PROFILE_DIR=Default
SELENIUM_HEADLESS=true

# Настройки цен
MIN_PRICE=0.25
MAX_PRICE=10.0
UNDERCUT_VALUE=0.0051
MODE=FIXED
FIXED_PRICE=0.35
```

Авторизация GGSEL:
- `GGSEL_API_KEY` — секретный key, используется для `/apilogin`
- `GGSEL_ACCESS_TOKEN` — опционально готовый access token
- если `GGSEL_ACCESS_TOKEN` не задан, бот получает token автоматически через `/apilogin`
- если `GGSEL_API_KEY` выглядит как JWT (`xxx.yyy.zzz`), это, скорее всего, access token, а не secret key

### 3. Запуск

```bash
python3 -m src.main
```

Или через Makefile:

```bash
make run
```

### 4. Запуск в Docker

```bash
docker compose up -d --build
```

Healthcheck контейнера использует heartbeat планировщика (`state.last_cycle`).

### 5. Backup state.db

```bash
python3 scripts/backup_state.py
```

Или:

```bash
make backup
```

После запуска ключевые параметры можно менять прямо в Telegram через Reply Keyboard:
- `🎯 Цена` (`DESIRED_PRICE`)
- `➖ Шаг` (`UNDERCUT_VALUE`)
- `📉 Мин` (`MIN_PRICE`)
- `📈 Макс` (`MAX_PRICE`)
- `🩺 Диагностика` (проверка API, heartbeat, runtime-конфига, DB)
- `🔀 Режим` (`FIXED/STEP_UP`)
- `📍 Позиция` (вкл/выкл фильтра позиции)
- `🔗 Добавить URL` / `🗑 Удалить URL`
- `📤 Экспорт` / `📥 Импорт` runtime-настроек
- `🧾 История` изменений настроек

---

## 📋 Бизнес-логика

### 1. Базовая формула

```python
my_price = competitor_price - UNDERCUT_VALUE
```

- НЕ округляется
- Точность до 4 знаков (пример: 0.30 -> 0.2949 при UNDERCUT_VALUE=0.0051)

### 2. Нижний порог

Если `new_price < MIN_PRICE`:

- **MODE=FIXED**: `price = FIXED_PRICE`
- **MODE=STEP_UP**: `price = current_price + STEP_UP_VALUE`

### 3. Множество конкурентов

```python
target_price = min(competitor_prices)
```

### 4. Фильтр слабого конкурента

Если конкурент "слабый" по цене ИЛИ по позиции в категории:

- По цене: `competitor_price < LOW_PRICE_THRESHOLD`
- По позиции: `POSITION_FILTER_ENABLED=true` и `rank > WEAK_POSITION_THRESHOLD`

- Если `< WEAK_PRICE_CEIL_LIMIT`: `ceil(price * 10) / 10 - UNDERCUT_VALUE`
- Если `>= WEAK_PRICE_CEIL_LIMIT`: `DESIRED_PRICE`

### 5. Cooldown

Не менять цену чаще `COOLDOWN_SECONDS`

### 6. Ignore Delta

Если `|new_price - current_price| < 0.001` → пропуск

---

## ⚙️ Конфигурация

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота | - |
| `TELEGRAM_ADMIN_IDS` | ID админов | - |
| `GGSEL_API_KEY` | API ключ GGSEL | - |
| `GGSEL_ACCESS_TOKEN` | Готовый access token (опционально) | - |
| `GGSEL_PRODUCT_ID` | ID товара | - |
| `GGSEL_LANG` | Локаль Seller API (`ru-RU`/`en-US`) | ru-RU |
| `GGSEL_REQUIRE_API_ON_START` | Fail-fast на старте, если API недоступен | false |
| `COMPETITOR_URLS` | URL конкурентов | - |
| `COMPETITOR_COOKIES` | Cookies для антибот-защиты конкурентов (`name=value; ...`) | - |
| `SELENIUM_USE_REAL_PROFILE` | Использовать реальный профиль Chrome в Selenium | false |
| `SELENIUM_CHROME_USER_DATA_DIR` | Путь к user-data-dir Chrome | - |
| `SELENIUM_CHROME_PROFILE_DIR` | Имя профиля Chrome (например `Default`) | Default |
| `SELENIUM_HEADLESS` | Запуск Selenium в headless режиме | true |
| `MIN_PRICE` | Минимальная цена | 0.25 |
| `MAX_PRICE` | Максимальная цена | 10.0 |
| `UNDERCUT_VALUE` | Насколько быть ниже конкурента | 0.0051 |
| `DESIRED_PRICE` | Желаемая цена | 0.35 |
| `MODE` | Режим: FIXED/STEP_UP | FIXED |
| `FIXED_PRICE` | Фикс цена | 0.35 |
| `STEP_UP_VALUE` | Шаг повышения | 0.05 |
| `LOW_PRICE_THRESHOLD` | Порог слабого конкурента | 0 |
| `WEAK_PRICE_CEIL_LIMIT` | Граница ceil-логики (п.4) | 0.3 |
| `POSITION_FILTER_ENABLED` | Включить фильтр по позиции конкурента | false |
| `WEAK_POSITION_THRESHOLD` | Позиция, ниже которой конкурент считается слабым | 20 |
| `COOLDOWN_SECONDS` | Пауза между обновлениями | 30 |
| `IGNORE_DELTA` | Мин. разница для обновления | 0.001 |
| `CHECK_INTERVAL` | Интервал проверки | 30 |
| `NOTIFY_SKIP` | Отправлять уведомления о skip-циклах | false |
| `NOTIFY_SKIP_COOLDOWN_SECONDS` | Антиспам для skip-уведомлений | 300 |
| `NOTIFY_COMPETITOR_CHANGE` | Уведомлять об изменении min-цены конкурента | true |
| `COMPETITOR_CHANGE_DELTA` | Минимальная дельта для алерта конкурента | 0.0001 |
| `COMPETITOR_CHANGE_COOLDOWN_SECONDS` | Антиспам для алерта конкурента | 60 |
| `LOG_MAX_BYTES` | Размер файла лога до ротации | 10485760 |
| `LOG_BACKUP_COUNT` | Количество ротаций лога | 5 |

---

## 📁 Структура проекта

```
project/
├── src/
│   ├── __init__.py
│   ├── config.py       # Конфигурация
│   ├── storage.py      # SQLite хранилище
│   ├── parser.py       # Парсинг конкурентов
│   ├── api_client.py   # GGSEL API
│   ├── logic.py        # Бизнес-логика
│   ├── scheduler.py    # Планировщик
│   ├── telegram_bot.py # Управление и уведомления через Reply Keyboard
│   └── main.py         # Точка входа
├── data/
│   └── state.db        # SQLite база
├── logs/
│   └── bot-YYYY-MM-DD.log
├── .env
├── .env.example
└── requirements.txt
```

---

## 🔧 Требования

- Python 3.8+
- Telegram Bot Token
- GGSEL API Key

---

## 🧰 Операционные команды

```bash
make test      # pytest
make compile   # compileall
make up        # docker compose up -d --build
make down      # docker compose down
make logs      # docker compose logs -f
make health    # локальный healthcheck
make smoke     # live smoke Seller API (без изменения цены)
make check-apilogin  # проверка связки GGSEL_API_KEY + GGSEL_SELLER_ID
make issue-token  # выпуск access token через /apilogin
make systemd-install  # установка systemd service + watchdog timer (Linux)
```

Если `make check-apilogin` показывает `retdesc=Не найдено`:
1. В `GGSEL_API_KEY` указан не тот ключ (обычно туда попал JWT/access token).
2. Неверный `GGSEL_SELLER_ID` для этого key.

Для конкурентов с anti-bot защитой (например QRATOR) можно задать
`COMPETITOR_COOKIES` из браузера (DevTools -> Application -> Cookies),
чтобы парсер смог получить HTML карточки товара.

Также доступен Selenium-режим с реальным Chrome-профилем:
1. На сервере подготовьте user-data-dir Chrome.
2. Укажите `SELENIUM_USE_REAL_PROFILE=true`.
3. Задайте `SELENIUM_CHROME_USER_DATA_DIR` и при необходимости `SELENIUM_CHROME_PROFILE_DIR`.
4. Если сервер без GUI, используйте `SELENIUM_HEADLESS=true` или запуск через `xvfb-run`.

## 🔁 Автоперезапуск на сервере (systemd)

Бот можно установить как systemd-сервис с автоматическим рестартом и watchdog-таймером:

```bash
make systemd-install
```

Что будет создано:
- `<service>.service` — основной бот (`Restart=always`, `RestartSec=5`)
- `<service>-watchdog.service` — проверка heartbeat и smoke Seller API
- `<service>-watchdog.timer` — запуск watchdog каждые 2 минуты

По умолчанию имя сервиса: `monitoring-bot`.
Можно задать своё:

```bash
./scripts/install_systemd.sh my-bot
```

Проверка статуса:

```bash
sudo systemctl status monitoring-bot.service
sudo systemctl status monitoring-bot-watchdog.timer
journalctl -u monitoring-bot.service -f
```

---

## 📊 Метрики

Бот сохраняет в SQLite:

- `last_price` - последняя цена
- `last_update` - время обновления
- `last_cycle` - heartbeat цикла планировщика
- `update_count` - количество обновлений
- `skip_count` - количество пропусков
- `auto_mode` - состояние авто-режима (сохраняется между перезапусками)
- `price_history` - история изменений
- `runtime_settings` - runtime overrides из Telegram
- `settings_history` - журнал изменений runtime-настроек (кто/что/когда)
- `alert_state` - антиспам-состояние уведомлений (ошибки/skip/изменение конкурента)

Бот валидирует runtime-настройки перед каждым циклом.
Если параметры некорректны, цикл пропускается и отправляется throttled-ошибка в Telegram.

---

## 📄 License

MIT
