#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(pwd)}"
BOT_SERVICE_NAME="${BOT_SERVICE_NAME:-monitoring-bot.service}"
HEALTHCHECK_MAX_AGE_SECONDS="${HEALTHCHECK_MAX_AGE_SECONDS:-300}"
WATCHDOG_RUN_SMOKE="${WATCHDOG_RUN_SMOKE:-1}"

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${APP_DIR}/.venv/bin/python"
fi

echo "[watchdog] app_dir=${APP_DIR}"
echo "[watchdog] service=${BOT_SERVICE_NAME}"
echo "[watchdog] python=${PYTHON_BIN}"

restart_reason=""

if ! HEALTHCHECK_DB_PATH="${APP_DIR}/data/state.db" \
    HEALTHCHECK_MAX_AGE_SECONDS="${HEALTHCHECK_MAX_AGE_SECONDS}" \
    "${PYTHON_BIN}" "${APP_DIR}/healthcheck.py" >/dev/null 2>&1; then
  restart_reason="stale_or_missing_heartbeat"
fi

if [[ -z "${restart_reason}" && "${WATCHDOG_RUN_SMOKE}" == "1" ]]; then
  if ! (cd "${APP_DIR}" && PYTHONPATH=. "${PYTHON_BIN}" scripts/smoke_seller_api.py >/dev/null 2>&1); then
    restart_reason="seller_api_smoke_failed"
  fi
fi

if [[ -n "${restart_reason}" ]]; then
  echo "[watchdog] restart service: ${BOT_SERVICE_NAME} reason=${restart_reason}"
  systemctl restart "${BOT_SERVICE_NAME}"
else
  echo "[watchdog] ok"
fi
