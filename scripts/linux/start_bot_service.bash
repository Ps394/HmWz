#!/bin/bash
# Start HsBot service

echo "Starting HsBot service..."

sudo systemctl daemon-reload || { echo "daemon-reload failed"; exit 1;}
sudo systemctl enable discordbot.service || { echo "enable discordbot.service failed"; exit 1; }
sudo systemctl restart discordbot.service || { echo "restart discordbot.service failed"; exit 1; } 

if [ $? -eq 0 ]; then
    echo "HsBot service started successfully"
    sudo systemctl status discordbot.service --no-pager
else
    echo "Failed to start HsBot service"
    exit 1
fi

