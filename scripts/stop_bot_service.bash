#!/bin/bash
# Stop HsBot service

echo "Stopping HsBot service..."

sudo systemctl stop discordbot.service || { echo "stop discordbot.service failed"; exit 1; }
sudo systemctl disable discordbot.service || { echo "disable discordbot.service failed"; exit 1; }

if [ $? -eq 0 ]; then
    echo "HsBot service stopped successfully"
else
    echo "Failed to stop HsBot service"
    exit 1
fi