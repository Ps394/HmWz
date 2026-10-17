#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: Python 3 is not installed." >&2
    echo "Install Python 3 and its venv package with your distribution's package manager." >&2
    exit 1
fi

if ! python3 -c 'import sys; print("Using Python {}.{}".format(*sys.version_info[:2])); raise SystemExit(sys.version_info < (3, 12))'; then
    echo "Error: Python 3.12 or newer is required." >&2
    exit 1
fi

if [ -d venv ]; then
    echo "Virtual environment already exists; skipping creation."
else
    python3 -m venv venv
fi

if [ ! -x venv/bin/python ]; then
    echo "Error: venv/bin/python was not created successfully." >&2
    exit 1
fi

echo "Virtual environment is ready at $PROJECT_DIR/venv."
