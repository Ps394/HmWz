#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "=== HmWz installation ==="
bash "$SCRIPT_DIR/create_venv.bash"
bash "$SCRIPT_DIR/install_dependencies.bash"
bash "$SCRIPT_DIR/configure_token.bash"
bash "$SCRIPT_DIR/install_service.bash"

echo
echo "Installation complete. The configured systemd service is enabled and running."
