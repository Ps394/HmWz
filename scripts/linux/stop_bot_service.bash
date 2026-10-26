#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${HMWZ_SERVICE_NAME:-discordbot-test}"

echo "Stopping $SERVICE_NAME.service..."
sudo systemctl stop $SERVICE_NAME.service
echo "$SERVICE_NAME.service stopped. It remains enabled for the next boot."