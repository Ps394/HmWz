#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/service_config.bash"

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

if [[ -z "$PROJECT_DIR" || -z "${HOME:-}" ]]; then
    echo "Error: Project and home paths must not be empty." >&2
    exit 1
fi

systemd_quote() {
    local value="$1"
    if [[ -z "$value" ]]; then
        echo "Error: Refusing to write an empty systemd path." >&2
        return 1
    fi
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//%/%%}"
    printf '"%s"' "$value"
}

systemd_path() {
    local value="$1"
    if [[ "$value" != /* || "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
        echo "Error: systemd paths must be absolute and must not contain line breaks." >&2
        return 1
    fi
    # Path directives retain quotes literally, unlike ExecStart arguments.
    printf '%s' "${value//%/%%}"
}

current_service_name="$(hmwz_resolve_service_name)"
service_name_input="${HMWZ_SERVICE_NAME:-}"
if [[ -z "$service_name_input" && -t 0 ]]; then
    read -r -p "systemd service name [${current_service_name%.service}]: " service_name_input || true
fi
if [[ -z "$service_name_input" ]]; then
    service_name="$current_service_name"
else
    service_name="$(hmwz_normalize_service_name "$service_name_input")"
fi

service_user="$(id -un)"
service_group="$(id -gn)"
service_home="$HOME"
python_path="$PROJECT_DIR/venv/bin/python"
entry_path="$PROJECT_DIR/src/bot.py"
token_file_directive=

if [[ -n "${HMWZ_TOKEN_FILE:-}" ]]; then
    if [[ "$HMWZ_TOKEN_FILE" != /* || ! -f "$HMWZ_TOKEN_FILE" || ! -r "$HMWZ_TOKEN_FILE" ]]; then
        echo "Error: HMWZ_TOKEN_FILE must be an absolute path to a readable file: $HMWZ_TOKEN_FILE" >&2
        exit 1
    fi
    token_file_directive="EnvironmentFile=$(systemd_path "$HMWZ_TOKEN_FILE")"
fi

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
EOF

if [[ -n "$token_file_directive" ]]; then
    printf '%s\n' "$token_file_directive" >> "$unit_file"
fi

cat >> "$unit_file" <<EOF
WorkingDirectory=$(systemd_path "$PROJECT_DIR")
ExecStart=$(systemd_quote "$python_path") $(systemd_quote "$entry_path")
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$unit_file" "/etc/systemd/system/$service_name"
sudo systemctl daemon-reload
sudo systemctl enable --now "$service_name"
hmwz_save_service_name "$service_name"
echo "Installed and started $service_name for user $service_user."
