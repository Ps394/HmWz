#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${HMWZ_SERVICE_NAME:-discordbot-test}"

echo "Starting $SERVICE_NAME.service..."
sudo systemctl restart $SERVICE_NAME.service
sudo systemctl status $SERVICE_NAME.service --no-pager
