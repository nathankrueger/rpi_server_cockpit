#!/bin/bash

# ============================================================
# Functions
# ============================================================

usage() {
    cat << EOF
Usage: ./install.sh [OPTIONS]

Options:
  -r, --reinstall    Remove existing virtual environment and reinstall from scratch
  -h, --help         Display this help message

Description:
  Installs the rpi_server_cockpit project with dependencies.
  By default, reuses an existing virtual environment if present.

EOF
}

# ============================================================
# Installation
# ============================================================

set -e  # Exit on error

REINSTALL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--reinstall)
            REINSTALL=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$REINSTALL" = true ]; then
    if [ -d ".venv" ]; then
        echo "Removing existing virtual environment..."
        rm -rf .venv
    fi
fi

if [ -d ".venv" ]; then
    echo "Activating existing virtual environment..."
    source .venv/bin/activate
else
    echo "Creating new virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate

    echo "Updating pip..."
    pip install --upgrade pip
fi

echo "Installing requirements..."
pip install -r requirements.txt

echo ""
echo "Installation complete!"
echo "  - Virtual environment: $SCRIPT_DIR/.venv"
echo ""
echo "To activate the environment:"
echo "  source .venv/bin/activate"
