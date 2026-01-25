#!/bin/bash

# ============================================================
# Configuration
# ============================================================

# Path to the data_log repository for sensor integration
# Modify this if your data_log repo is in a different location
DATA_LOG_PATH="/home/nkrueger/dev/data_log"

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
  Installs the rpi_server_cockpit project with dependencies and data_log integration.
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

# Validate data_log path exists
if [ ! -d "$DATA_LOG_PATH" ]; then
    echo "Error: data_log repository not found at: $DATA_LOG_PATH"
    echo "Please update DATA_LOG_PATH in this script to point to your data_log repo."
    exit 1
fi

if [ ! -f "$DATA_LOG_PATH/pyproject.toml" ]; then
    echo "Error: $DATA_LOG_PATH does not appear to be a valid Python package."
    echo "Missing pyproject.toml. Please ensure data_log has been set up as a package."
    exit 1
fi

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

echo "Installing data_log package (editable)..."
pip install -e "$DATA_LOG_PATH"

echo ""
echo "Installation complete!"
echo "  - Virtual environment: $SCRIPT_DIR/.venv"
echo "  - data_log installed from: $DATA_LOG_PATH"
echo ""
echo "To activate the environment:"
echo "  source .venv/bin/activate"