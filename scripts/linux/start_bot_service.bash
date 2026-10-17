#!/usr/bin/env bash
set -euo pipefail

echo "Starting discordbot.service..."
sudo systemctl restart discordbot.service
sudo systemctl status discordbot.service --no-pager
