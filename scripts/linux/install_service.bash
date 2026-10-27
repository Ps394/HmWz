#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

if [ "$(id -u)" -eq 0 ]; then
    echo "Error: Run this script as the bot user, not as root. It uses sudo for systemd setup." >&2
    exit 1
fi
if ! command -v systemctl >/dev/null 2>&1; then
    echo "Error: systemctl is not available; this system cannot install a systemd service." >&2
    exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
    echo "Error: sudo is required to install and enable the systemd service." >&2
    exit 1
fi
if [ ! -x "$PROJECT_DIR/venv/bin/python" ]; then
    echo "Error: Virtual environment not found. Run create_venv.bash first." >&2
    exit 1
fi

service_user="$(id -un)"
service_group="$(id -gn)"
service_home="$HOME"
python_path="$PROJECT_DIR/venv/bin/python"
entry_path="$PROJECT_DIR/src/bot.py"

systemd_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//%/%%}"
    printf '"%s"' "$value"
}

unit_file="$(mktemp)"
trap 'rm -f "$unit_file"' EXIT

cat > "$unit_file" <<EOF
[Unit]
Description=HmWz Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$service_user
Group=$service_group
Environment=HOME=$(systemd_quote "$service_home")
WorkingDirectory=$(systemd_quote "$PROJECT_DIR")
ExecStart=$(systemd_quote "$python_path") $(systemd_quote "$entry_path")
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$unit_file" /etc/systemd/system/discordbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now discordbot.service
echo "Installed and started discordbot.service for user $service_user."
