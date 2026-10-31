#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/service_config.bash"
service_name="$(hmwz_resolve_service_name "${1:-}")"

echo "Starting $service_name..."
sudo systemctl restart "$service_name"
sudo systemctl status "$service_name" --no-pager
