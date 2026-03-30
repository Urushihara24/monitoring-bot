# 🚀 Инструкция по развёртыванию на сервере

## Быстрый старт

### 1. Подготовка сервера

```bash
# Обновление пакетов
sudo apt update && sudo apt upgrade -y

# Установка Python и зависимостей
sudo apt install -y python3 python3-pip python3-venv git curl

# Установка Chrome (для Selenium)
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
sudo apt update
sudo apt install -y google-chrome-stable

# Или Chromium (легковесная версия)
sudo apt install -y chromium-browser
```

### 2. Установка бота

```bash
# Клонирование репозитория
cd /opt
sudo git clone <REPO_URL> monitoring
sudo chown -R $USER:$USER monitoring
cd monitoring

# Создание виртуального окружения
python3 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Настройка .env

```bash
cp .env.example .env
nano .env
```

**Обязательные параметры:**
```env
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_IDS=your_telegram_id

# GGSEL API
GGSEL_API_KEY=eyJhbGciOiJIUzI1NiJ9...  # JWT токен из кабинета
GGSEL_SELLER_ID=1325236
GGSEL_PRODUCT_ID=your_product_id

# Конкуренты
COMPETITOR_URLS=https://ggsel.net/catalog/product/your-product
```

### 4. Настройка cookies (обход QRATOR)

#### Вариант А: Локально → копирование

```bash
# Локально (на вашем Mac):
cd /path/to/Monitoring
python3 scripts/update_competitor_cookies.py --interactive

# Копирование на сервер:
scp data/cookies_backup.json user@server:/opt/monitoring/data/
```

#### Вариант Б: Прямо на сервере

```bash
# На сервере (нужен GUI или X11):
cd /opt/monitoring
source .venv/bin/activate
python3 scripts/update_competitor_cookies.py --interactive
```

### 5. Настройка авто-обновления cookies

```bash
# Добавление в crontab
(crontab -l 2>/dev/null | grep -v "cron_update_cookies")
echo "0 */6 * * * /opt/monitoring/scripts/cron_update_cookies.sh >> /opt/monitoring/logs/cron_cookies.log 2>&1" | crontab -

# Проверка
crontab -l
```

### 6. Установка systemd

```bash
cd /opt/monitoring
sudo ./scripts/install_systemd.sh

# Проверка
sudo systemctl status monitoring-bot.service
sudo systemctl status monitoring-bot-watchdog.timer

# Логи
journalctl -u monitoring-bot.service -f
```

---

## 🔧 Управление

### Команды systemctl

```bash
# Статус
sudo systemctl status monitoring-bot.service

# Старт/стоп/рестарт
sudo systemctl start monitoring-bot.service
sudo systemctl stop monitoring-bot.service
sudo systemctl restart monitoring-bot.service

# Автозапуск при загрузке
sudo systemctl enable monitoring-bot.service
```

### Логи

```bash
# Журнал systemd
journalctl -u monitoring-bot.service -f
journalctl -u monitoring-bot.service --since "1 hour ago"

# Логи cron (обновление cookies)
grep cron_update_cookies /var/log/syslog
cat /opt/monitoring/logs/cron_cookies.log
```

### Тестирование

```bash
cd /opt/monitoring
source .venv/bin/activate

# Smoke тест API
make smoke

# Проверка API login
make check-apilogin

# Тесты
make test
```

---

## 📁 Структура на сервере

```
/opt/monitoring/
├── .env                          # Конфиг (не коммитить)
├── .venv/                        # Виртуальное окружение
├── data/
│   ├── state.db                  # SQLite state
│   └── cookies_backup.json       # Cookies (git-ignored)
├── logs/
│   ├── bot-2026-03-30.log        # Логи бота
│   └── cron_cookies.log          # Логи обновления cookies
├── scripts/
│   ├── update_competitor_cookies.py
│   ├── cron_update_cookies.sh
│   ├── install_systemd.sh
│   └── ...
└── src/
    ├── main.py
    ├── parser.py
    └── ...
```

---

## ⚠️ Важные моменты

### 1. Cookies backup

- **Первичная настройка:** один раз запустить `--interactive`
- **Обновление:** cron каждые 6 часов
- **Если протухли:** бот использует Selenium fallback
- **Проверка:** `cat data/cookies_backup.json | jq .updated_at`

### 2. GGSEL API

- **Токен:** JWT из личного кабинета (не secret key)
- **Seller ID:** должен совпадать с `sub` в JWT
- **Проверка:** `make check-apilogin`

### 3. Логирование

- **Бот:** `logs/bot-*.log` + systemd journal
- **Cookies:** `logs/cron_cookies.log`
- **Ротация:** автоматически (10MB, 5 файлов)

---

## 🆘 Troubleshooting

### Бот не запускается

```bash
# Проверка логов
journalctl -u monitoring-bot.service -n 50

# Проверка .env
cat .env | grep -v "="

# Проверка API
make smoke
```

### Cookies протухли

```bash
# Обновить вручную
cd /opt/monitoring
source .venv/bin/activate
python3 scripts/update_competitor_cookies.py --interactive

# Перезапустить бота
sudo systemctl restart monitoring-bot.service
```

### Cron не работает

```bash
# Проверка crontab
crontab -l

# Проверка логов
grep CRON /var/log/syslog | tail -20

# Перезапуск cron
sudo systemctl restart cron
```

### API возвращает 401

```bash
# Проверить токен
make check-apilogin

# Если "Не найдено" - проверить GGSEL_SELLER_ID
# Должен совпадать с sub в JWT payload
```

---

## 📞 Контакты

При проблемах:
1. Проверить логи (`journalctl`, `logs/`)
2. Запустить `make smoke` и `make check-apilogin`
3. Проверить crontab (`crontab -l`)
