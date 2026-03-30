#!/usr/bin/env bash
# Cron-скрипт для периодического обновления cookies конкурента
# Запускать каждые 6-12 часов через cron

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_BIN="${APP_DIR}/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

cd "${APP_DIR}"

echo "[$(date -Iseconds)] Запуск обновления cookies..."

# Запускаем обновление в headless режиме (использует существующие cookies)
"${PYTHON_BIN}" "${APP_DIR}/scripts/update_competitor_cookies.py" --url "${COMPETITOR_URL:-https://ggsel.net/catalog/product/fortnite-predmety-skiny-emocii-bez-vxoda-102124601}"

if [[ $? -eq 0 ]]; then
  echo "[$(date -Iseconds)] Cookies обновлены успешно"
else
  echo "[$(date -Iseconds)] Ошибка обновления cookies" >&2
fi
