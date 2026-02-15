#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Use venv python directly to avoid activate/sourcing issues
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    echo "Error: venv not found at $SCRIPT_DIR/.venv" >&2
    exit 1
fi

"$PYTHON" -m pytest tests/ "$@"
