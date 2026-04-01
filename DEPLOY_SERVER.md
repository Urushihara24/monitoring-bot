# 🚀 Инструкция по развёртыванию на сервере 5.230.125.77

## 1. Подключение к серверу

```bash
ssh root@5.230.125.77
# Пароль: qZwmgL6ddJ1dSFX0
```

## 2. Отправка файлов на сервер

В локальном терминале (не в SSH):

```bash
cd /Users/vsevolod/Documents/Monitoring
scp /tmp/monitoring-deploy.tar.gz root@5.230.125.77:/root/
```

## 3. На сервере (после подключения)

```bash
# Перейдите в директорию
cd /root

# Распакуйте архив
tar -xzf monitoring-deploy.tar.gz

# Установите зависимости
pip3 install -r requirements.txt --break-system-packages

# Установите stealth-requests
pip3 install stealth-requests --break-system-packages

# Проверьте .env
cat .env | grep -E "TELEGRAM|GGSEL"

# Запустите бота
python3 -m src.main
```

## 4. Проверка Telegram

```bash
# Проверка доступа к Telegram API
curl -s https://api.telegram.org/bot8653474276:AAGyVkehvnQBT2-sv8_X4bBmSrZppN86AGo/getMe | python3 -m json.tool
```

Если видите ответ с информацией о боте — **Telegram работает!** ✅

## 5. Запуск в фоне (опционально)

```bash
# Через nohup
nohup python3 -m src.main > bot.log 2>&1 &

# Или через screen
screen -S monitoring-bot
python3 -m src.main
# Ctrl+A, D для открепления
```

## 6. Проверка логов

```bash
tail -f logs/bot-*.log
```

---

## 🔧 Если Telegram не работает на сервере

Добавьте прокси в `.env`:

```bash
nano .env
# Добавьте строку:
TELEGRAM_PROXY_URL=http://proxy:port
```

Или используйте SOCKS5:
```bash
TELEGRAM_PROXY_URL=socks5://user:pass@proxy:port
```

---

## ✅ Ожидаемый результат

```
🚀 Запуск Auto-Pricing Bot...
✅ Товар найден: Fortnite Скины / Предметы / Эмоции Подарком
   Текущая цена: 0.37 RUB
Telegram бот запущен
Планировщик запущен (интервал: 60s)
🔄 Запуск цикла pricing...
Мин. цена: 70.0₽ за 200 V-Bucks = 0.35₽/V-Buck
```
