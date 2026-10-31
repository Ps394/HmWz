#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/service_config.bash"
service_name="$(hmwz_resolve_service_name "${1:-}")"

echo "Stopping $service_name..."
sudo systemctl stop "$service_name"
echo "$service_name stopped. It remains enabled for the next boot."