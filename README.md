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
GGSEL_API_KEY=your_api_key_here
GGSEL_PRODUCT_ID=4697439
GGSEL_LANG=ru-RU

# Конкуренты
COMPETITOR_URLS=https://ggsel.net/catalog/product/competitor-12345

# Настройки цен
MIN_PRICE=0.25
MAX_PRICE=10.0
UNDERCUT_VALUE=0.0051
MODE=FIXED
FIXED_PRICE=0.35
```

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
| `GGSEL_PRODUCT_ID` | ID товара | - |
| `GGSEL_LANG` | Локаль Seller API (`ru-RU`/`en-US`) | ru-RU |
| `COMPETITOR_URLS` | URL конкурентов | - |
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
- `alert_state` - антиспам-состояние уведомлений об ошибках

Бот валидирует runtime-настройки перед каждым циклом.
Если параметры некорректны, цикл пропускается и отправляется throttled-ошибка в Telegram.

---

## 📄 License

MIT
