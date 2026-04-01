# 🤖 Auto-Pricing Bot для GGSEL Marketplace

Полноценный auto-pricing engine с чёткой бизнес-логикой, Telegram-управлением и обходом anti-bot защиты.

**Основные возможности:**
- Автоматический мониторинг цен конкурентов (RSC Parser + Playwright fallback)
- Distill.io интеграция как резервный парсер
- Гибкая бизнес-логика ценообразования (FIXED/STEP_UP режимы)
- Telegram-бот с Reply Keyboard для управления настройками
- Runtime-конфигурация без перезапуска бота
- Обход QRATOR/anti-bot защиты через cookies + Playwright
- SQLite для хранения состояния и истории цен
- Docker + systemd для продакшн-деплоя

---

## 🚀 Развёртывание на сервере

### Быстрый старт (Docker)

```bash
# 1. Клонирование
cd /opt
git clone <REPO_URL> monitoring
cd monitoring

# 2. Настройка
cp .env.example .env
nano .env  # Заполните TELEGRAM_BOT_TOKEN, GGSEL_API_KEY, COMPETITOR_URLS

# 3. Cookies (обход anti-bot)
# На локальном компьютере:
python3 scripts/update_competitor_cookies.py --interactive
# Копирование на сервер:
scp data/cookies_backup.json user@server:/opt/monitoring/data/

# 4. Запуск
docker-compose up -d --build
docker-compose logs -f  # Проверка логов
```

**Полная инструкция:** см. [DEPLOY_SERVER.md](DEPLOY_SERVER.md)

**Скрипт автоматической настройки:**

```bash
bash scripts/setup_server.sh
```

---

## 🚀 Быстрый старт (локально)

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
GGSEL_SELLER_ID=8175
GGSEL_PRODUCT_ID=4697439
GGSEL_LANG=ru-RU
GGSEL_REQUIRE_API_ON_START=false

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
DESIRED_PRICE=0.35
MODE=FIXED
FIXED_PRICE=0.35
```

**Авторизация GGSEL:**
- `GGSEL_API_KEY` — секретный API key из личного кабинета (используется для `/apilogin`)
- `GGSEL_ACCESS_TOKEN` — опционально готовый access token (если не задан, получается автоматически)
- `GGSEL_SELLER_ID` — ID продавца (должен совпадать с `sub` в JWT payload)
- **Важно:** если `GGSEL_API_KEY` выглядит как JWT (`xxx.yyy.zzz`), это access token — укажите его в `GGSEL_ACCESS_TOKEN`, а в `GGSEL_API_KEY` вставьте секретный ключ

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

### Основные переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота | - |
| `TELEGRAM_ADMIN_IDS` | ID админов (через запятую) | - |
| `GGSEL_API_KEY` | Секретный API ключ GGSEL (для `/apilogin`) | - |
| `GGSEL_ACCESS_TOKEN` | Готовый access token (опционально) | - |
| `GGSEL_SELLER_ID` | ID продавца | `8175` |
| `GGSEL_PRODUCT_ID` | ID товара для мониторинга | - |
| `GGSEL_BASE_URL` | Базовый URL Seller API | `https://seller.ggsel.com/api_sellers/api` |
| `GGSEL_LANG` | Локаль API (`ru-RU`/`en-US`) | `ru-RU` |
| `GGSEL_REQUIRE_API_ON_START` | Fail-fast на старте, если API недоступен | `false` |

### Конкуренты и парсинг

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `COMPETITOR_URLS` | URL конкурентов (через запятую) | - |
| `COMPETITOR_COOKIES` | Cookies для обхода anti-bot (`name=value; ...`) | - |
| `SELENIUM_USE_REAL_PROFILE` | Использовать реальный профиль Chrome | `false` |
| `SELENIUM_CHROME_USER_DATA_DIR` | Путь к user-data-dir Chrome | - |
| `SELENIUM_CHROME_PROFILE_DIR` | Имя профиля Chrome | `Default` |
| `SELENIUM_HEADLESS` | Запуск в headless режиме | `true` |

### Настройки цен

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `MIN_PRICE` | Минимальная цена | `0.25` |
| `MAX_PRICE` | Максимальная цена | `10.0` |
| `DESIRED_PRICE` | Желаемая цена (для слабого конкурента) | `0.35` |
| `UNDERCUT_VALUE` | Насколько быть ниже конкурента | `0.0051` |
| `MODE` | Режим при `MIN_PRICE`: `FIXED` или `STEP_UP` | `FIXED` |
| `FIXED_PRICE` | Фиксированная цена (MODE=FIXED) | `0.35` |
| `STEP_UP_VALUE` | Шаг повышения (MODE=STEP_UP) | `0.05` |

### Фильтры конкурентов

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `LOW_PRICE_THRESHOLD` | Порог «слабого» конкурента по цене | `0` |
| `WEAK_PRICE_CEIL_LIMIT` | Граница ceil-логики для слабого конкурента | `0.3` |
| `POSITION_FILTER_ENABLED` | Включить фильтр по позиции в категории | `false` |
| `WEAK_POSITION_THRESHOLD` | Позиция, выше которой конкурент «слабый» | `20` |

### Тайминги и уведомления

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `COOLDOWN_SECONDS` | Мин. пауза между обновлениями цены | `30` |
| `IGNORE_DELTA` | Мин. разница цен для обновления | `0.001` |
| `CHECK_INTERVAL` | Интервал проверки конкурентов | `30` |
| `NOTIFY_SKIP` | Уведомлять о пропусках (skip) | `false` |
| `NOTIFY_SKIP_COOLDOWN_SECONDS` | Антиспам для skip-уведомлений | `300` |
| `NOTIFY_COMPETITOR_CHANGE` | Уведомлять об изменении цены конкурента | `true` |
| `COMPETITOR_CHANGE_DELTA` | Мин. дельта для алерта конкурента | `0.0001` |
| `COMPETITOR_CHANGE_COOLDOWN_SECONDS` | Антиспам для алерта конкурента | `60` |

### Логирование

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `LOG_MAX_BYTES` | Размер файла лога до ротации | `10485760` (10MB) |
| `LOG_BACKUP_COUNT` | Количество файлов лога | `5` |

---

## 🤖 Telegram-бот

Бот управляется через **Reply Keyboard** (кнопки внизу экрана).

### Главное меню

| Кнопка | Описание |
|--------|----------|
| `📊 Статус` | Показать текущее состояние: цена, конкуренты, статистика |
| `⬆ +0.01₽` | Увеличить цену на 0.01₽ |
| `⬇ -0.01₽` | Уменьшить цену на 0.01₽ |
| `🔔 Авто: ВКЛ/ВЫКЛ` | Включить/выключить авто-режим |
| `⚙ Настройки` | Открыть меню настроек |
| `🩺 Диагностика` | Проверка API, heartbeat, конфигурации |

### Меню настроек

| Кнопка | Описание |
|--------|----------|
| `🎯 Цена` | Установить `DESIRED_PRICE` |
| `➖ Шаг` | Установить `UNDERCUT_VALUE` |
| `📉 Мин` | Установить `MIN_PRICE` |
| `📈 Макс` | Установить `MAX_PRICE` |
| `🔀 Режим` | Переключить `MODE` (FIXED ↔ STEP_UP) |
| `📍 Позиция` | Включить/выключить фильтр по позиции |
| `🔗 Добавить URL` | Добавить URL конкурента |
| `🗑 Удалить URL` | Удалить URL из списка |
| `📤 Экспорт` | Экспорт текущих runtime-настроек |
| `📥 Импорт` | Импорт настроек в формате `key=value` |
| `🧾 История` | История изменений настроек |

### Уведомления

Бот отправляет уведомления о:
- ✅ Обновлении цены (старая → новая, причина)
- ⏭️ Пропуске обновления (причина: cooldown, ignore_delta, и т.д.)
- 📡 Изменении цены конкурента (если `NOTIFY_COMPETITOR_CHANGE=true`)
- ❌ Ошибках API и парсинга (с throttling)

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

**Важно:** Перед запуском очистите переменные окружения:
```bash
unset GGSEL_SELLER_ID GGSEL_ACCESS_TOKEN GGSEL_API_KEY
python3 -m src.main
```

Если `make check-apilogin` показывает `retdesc=Не найдено`:
1. В `GGSEL_API_KEY` указан не тот ключ (обычно туда попал JWT/access token).
2. Неверный `GGSEL_SELLER_ID` для этого key.
3. **Решение:** Используйте JWT токен как `GGSEL_API_KEY` и правильный `GGSEL_SELLER_ID` из личного кабинета.

---

## 🍪 Обход QRATOR (anti-bot защита конкурента)

Для парсинга цен конкурента с защитой QRATOR используется **трёхуровневая стратегия**:

1. **Cookies backup** (основной метод) — загрузка сохранённых cookies
2. **Playwright** (fallback 1) — headless Chromium с эмуляцией браузера
3. **Selenium** (fallback 2) — резервный метод для сложных случаев

### Метод 1: Cookies backup (рекомендуется)

1. **Первичная настройка (интерактивно):**
   ```bash
   # На локальной машине с браузером
   python3 scripts/update_competitor_cookies.py --interactive
   ```
   - Откроется браузер, пройдите капчу если нужно
   - Cookies сохранятся в `data/cookies_backup.json`

2. **Копирование на сервер:**
   ```bash
   # Скопируйте файл на сервер
   scp data/cookies_backup.json user@server:/path/to/Monitoring/data/
   ```

3. **Автоматическое обновление (cron):**
   ```bash
   # Добавь в crontab (обновление каждые 6 часов)
   0 */6 * * * /path/to/Monitoring/scripts/cron_update_cookies.sh
   ```

### Метод 2: Playwright (автоматический fallback)

Если cookies протухли, бот автоматически использует Playwright:
- Открывает страницу в headless Chromium
- Ждёт загрузки контента (2.5 сек)
- Извлекает HTML для парсинга

**Ничего настраивать не требуется** — работает из коробки.

### Метод 3: Selenium с реальным профилем

Для сложных случаев можно использовать реальный профиль Chrome:

1. **Подготовка профиля на сервере:**
   ```bash
   # Создать профиль (первый раз с GUI или xvfb)
   google-chrome --user-data-dir=/opt/chrome-profile --remote-debugging-port=9222
   ```

2. **Настройка .env:**
   ```bash
   SELENIUM_USE_REAL_PROFILE=true
   SELENIUM_CHROME_USER_DATA_DIR=/opt/chrome-profile
   SELENIUM_CHROME_PROFILE_DIR=Default
   SELENIUM_HEADLESS=false  # или true если профиль работает
   ```

### Метод 4: Ручные cookies

1. Открыть https://ggsel.net в браузере
2. DevTools → Application → Cookies → ggsel.net
3. Скопировать значения ключевых cookies
4. В `.env`:
   ```bash
   COMPETITOR_COOKIES=_ga=GA1.2.xxx; _gid=xxx; session=xxx
   ```

---

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
