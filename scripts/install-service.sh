#!/usr/bin/env bash
# Usage: ./scripts/install-service.sh /absolute/install/path
set -euo pipefail

INSTALL_DIR="${1:?Usage: $0 /path/to/install}"
PYTHON_BIN="$(which python3)"
SERVICE_FILE="/etc/systemd/system/flow.service"

sed -e "s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
    -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    "${INSTALL_DIR}/arsenal-personal-x.service.template" \
  | sudo tee "${SERVICE_FILE}"

sudo systemctl daemon-reload
sudo systemctl enable flow
echo "Installed service to ${SERVICE_FILE}"
echo "Start with: sudo systemctl start flow"
