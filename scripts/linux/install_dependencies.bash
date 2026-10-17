#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -x venv/bin/python ]; then
    echo "Error: Virtual environment not found. Run create_venv.bash first." >&2
    exit 1
fi

venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
echo "Dependencies installed successfully."
