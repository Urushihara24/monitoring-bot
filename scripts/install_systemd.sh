#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${1:-monitoring-bot}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${APP_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${APP_DIR}/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 not found"
  exit 1
fi

WATCHDOG_NAME="${SERVICE_NAME}-watchdog"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_FILE="${SYSTEMD_DIR}/${SERVICE_NAME}.service"
WATCHDOG_SERVICE_FILE="${SYSTEMD_DIR}/${WATCHDOG_NAME}.service"
WATCHDOG_TIMER_FILE="${SYSTEMD_DIR}/${WATCHDOG_NAME}.timer"

echo "Installing systemd units:"
echo "  service: ${SERVICE_FILE}"
echo "  watchdog service: ${WATCHDOG_SERVICE_FILE}"
echo "  watchdog timer: ${WATCHDOG_TIMER_FILE}"
echo "  app dir: ${APP_DIR}"
echo "  python: ${PYTHON_BIN}"

sudo tee "${SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=GGSEL Monitoring Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYTHON_BIN} -m src.main
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

sudo tee "${WATCHDOG_SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=Watchdog for ${SERVICE_NAME}
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${APP_DIR}
Environment=APP_DIR=${APP_DIR}
Environment=BOT_SERVICE_NAME=${SERVICE_NAME}.service
Environment=HEALTHCHECK_MAX_AGE_SECONDS=300
Environment=WATCHDOG_RUN_SMOKE=1
ExecStart=/usr/bin/env bash ${APP_DIR}/scripts/systemd_watchdog.sh
EOF

sudo tee "${WATCHDOG_TIMER_FILE}" > /dev/null <<EOF
[Unit]
Description=Run watchdog for ${SERVICE_NAME} every 2 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
Unit=${WATCHDOG_NAME}.service
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"
sudo systemctl enable --now "${WATCHDOG_NAME}.timer"

echo
echo "Installed successfully."
echo "Check status:"
echo "  sudo systemctl status ${SERVICE_NAME}.service"
echo "  sudo systemctl status ${WATCHDOG_NAME}.timer"
echo
echo "Logs:"
echo "  journalctl -u ${SERVICE_NAME}.service -f"
