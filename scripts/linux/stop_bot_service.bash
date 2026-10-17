#!/usr/bin/env bash
set -euo pipefail

echo "Stopping discordbot.service..."
sudo systemctl stop discordbot.service
echo "discordbot.service stopped. It remains enabled for the next boot."