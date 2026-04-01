# 🍪 Cookies для парсинга конкурентов

## ⚠️ Проблема

Сайт ggsel.net использует защиту QRATOR (anti-bot), которая требует:
1. Прохождения капчи при первом посещении
2. Наличия валидных session cookies для доступа к товарам

**Без cookies парсер получает HTTP 403 Forbidden.**

---

## 🔧 Как получить cookies

### Вариант 1: Интерактивный режим (рекомендуется)

```bash
cd /Users/vsevolod/Documents/Monitoring
python3 scripts/update_competitor_cookies.py --interactive
```

**Что произойдёт:**
1. Откроется браузер Chrome
2. Загрузится страница ggsel.net
3. Пройдите капчу если появится
4. Через 30 секунд браузер закроется
5. Cookies сохранятся в `data/cookies_backup.json`

### Вариант 2: Ручное копирование cookies

1. Откройте https://ggsel.net в браузере
2. Откройте DevTools (F12) → Application → Cookies → https://ggsel.net
3. Скопируйте значения cookies:
   - `_ga`
   - `_gid`
   - `session` (если есть)
   - `qrator_jsr`
4. Вставьте в `.env`:
   ```bash
   COMPETITOR_COOKIES=_ga=xxx; _gid=yyy; session=zzz
   ```

### Вариант 3: Автоматическое обновление (cron)

После первичной настройки:

```bash
# Добавь в crontab
crontab -e

# Обновление каждые 6 часов
0 */6 * * * /Users/vsevolod/Documents/Monitoring/scripts/cron_update_cookies.sh
```

---

## ✅ Проверка cookies

```bash
python3 scripts/update_competitor_cookies.py --url https://ggsel.net/catalog/product/fortnite-predmety-skiny-emocii-bez-vxoda-102124601
```

Если видите:
- `✅ Cookies работают (200 OK)` — всё хорошо
- `❌ Cookies не работают (401)` — cookies протухли, нужно обновить

---

## 📁 Структура

```
data/
├── cookies_backup.json       # Актуальные cookies (git-ignored)
├── cookies_backup_new.json   # Свежеполученные cookies
└── COOKIES_README.md         # Эта инструкция
```

---

## 🔄 Когда обновлять

- При запуске бота на новом сервере
- Если в логах появились ошибки `401 Forbidden`
- Раз в 6-12 часов (автоматически через cron)
- После очистки cookies в браузере

---

## 🐛 Troubleshooting

### Playwright не запускается

```bash
# Переустановить браузер Playwright
playwright install chromium
```

### Selenium не работает

```bash
# Установить Chrome/Chromium
# macOS:
brew install --cask google-chrome

# Linux:
sudo apt install chromium-browser
```

### Cookies не помогают

1. Проверьте срок действия:
   ```bash
   cat data/cookies_backup.json | jq .updated_at
   ```
2. Обновите cookies:
   ```bash
   python3 scripts/update_competitor_cookies.py --interactive
   ```
3. Перезапустите бота:
   ```bash
   sudo systemctl restart monitoring-bot.service
   ```
