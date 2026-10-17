#!/usr/bin/env bash
set -euo pipefail

if [ ! -t 0 ]; then
    echo "No interactive terminal; skipping optional bot-token configuration."
    exit 0
fi

read -r -p "Configure a bot token now? (y/N): " response
if [[ ! "$response" =~ ^[Yy]$ ]]; then
    echo "Skipping bot-token configuration."
    exit 0
fi

read -r -s -p "Discord bot token: " token
echo
if [ -z "$token" ]; then
    echo "No token entered; skipping token configuration."
    exit 0
fi

config_dir="$HOME/.config/hsbot"
mkdir -p "$config_dir"
chmod 700 "$config_dir"
umask 077
printf 'WZ_BOT_TOKEN=%s\n' "$token" > "$config_dir/config"
chmod 600 "$config_dir/config"
unset token

echo "Bot token stored with user-only permissions in $config_dir/config."
