#!/bin/bash

# Kasa Smart Plug Control
# Requires: python3-kasa package (install with: pip3 install python-kasa)

# Get the script directory and workspace root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"

# Source .env file if it exists
if [[ -f "$WORKSPACE_ROOT/.env" ]]; then
    source "$WORKSPACE_ROOT/.env"
fi

# Default values
PLUG_IP=""
ACTION=""
KASA_USER=""
KASA_PASS=""

# Function to get current plug state
# Returns 0 if ON, 1 if OFF
get_plug_state() {
    local cmd="$1"
    if $cmd state 2>/dev/null | grep "State (state):" | grep -q "True"; then
        return 0  # ON
    else
        return 1  # OFF
    fi
}

# Function to toggle the plug
toggle_plug() {
    local cmd="$1"
    if get_plug_state "$cmd"; then
        echo "Plug is ON, turning OFF..."
        $cmd off
        echo "Plug turned OFF"
    else
        echo "Plug is OFF, turning ON..."
        $cmd on
        echo "Plug turned ON"
    fi
}

# Function to display usage
usage() {
    echo "Usage: $0 -i|--ip_addr <IP> [-r|--read_state | -t|--toggle | -n|--on | -f|--off] [-u|--username <email>] [-p|--password <password>]"
    echo ""
    echo "Options:"
    echo "  -i, --ip_addr <IP>       IP address of the Kasa smart plug (required)"
    echo "  -r, --read_state         Read and display current state"
    echo "  -t, --toggle             Toggle the plug state (ON->OFF or OFF->ON)"
    echo "  -n, --on                 Turn the plug ON"
    echo "  -f, --off                Turn the plug OFF"
    echo "  -u, --username <email>   Kasa account email (for newer devices)"
    echo "  -p, --password <pass>    Kasa account password (for newer devices)"
    echo ""
    echo "Note: Newer Kasa devices require authentication. Set KASA_USERNAME and"
    echo "      KASA_PASSWORD environment variables or use -u/-p flags."
    echo ""
    echo "Example:"
    echo "  $0 -i 192.168.1.24 -r"
    echo "  $0 -i 192.168.1.47 --toggle"
    echo "  $0 -i 192.168.1.47 --on -u your@email.com -p yourpassword"
    echo "  KASA_USERNAME=your@email.com KASA_PASSWORD=yourpass $0 -i 192.168.1.47 --on"
    exit 1
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--ip_addr)
            PLUG_IP="$2"
            shift 2
            ;;
        -r|--read_state)
            ACTION="read"
            shift
            ;;
        -t|--toggle)
            ACTION="toggle"
            shift
            ;;
        -n|--on)
            ACTION="on"
            shift
            ;;
        -f|--off)
            ACTION="off"
            shift
            ;;
        -u|--username)
            KASA_USER="$2"
            shift 2
            ;;
        -p|--password)
            KASA_PASS="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Error: Unknown option $1"
            usage
            ;;
    esac
done

# Check for credentials in environment variables if not provided via flags
if [[ -z "$KASA_USER" ]] && [[ -n "$KASA_USERNAME" ]]; then
    KASA_USER="$KASA_USERNAME"
fi

if [[ -z "$KASA_PASS" ]] && [[ -n "$KASA_PASSWORD" ]]; then
    KASA_PASS="$KASA_PASSWORD"
fi

# Validate inputs
if [[ -z "$PLUG_IP" ]]; then
    echo "Error: IP address is required"
    usage
fi

if [[ -z "$ACTION" ]]; then
    echo "Error: An action is required (-r, -t, -n, or -f)"
    usage
fi

# Check if kasa is installed
if ! command -v kasa &> /dev/null; then
    echo "Error: kasa command not found. Install with: pip3 install python-kasa"
    exit 1
fi

# Build kasa command with authentication if provided
KASA_CMD="kasa --host $PLUG_IP"
if [[ -n "$KASA_USER" ]] && [[ -n "$KASA_PASS" ]]; then
    KASA_CMD="kasa --host $PLUG_IP --username $KASA_USER --password $KASA_PASS"
fi

# Execute the requested action
case $ACTION in
    read)
        $KASA_CMD state
        ;;
    toggle)
        toggle_plug "$KASA_CMD"
        ;;
    on)
        $KASA_CMD on
        echo "Plug turned ON"
        ;;
    off)
        $KASA_CMD off
        echo "Plug turned OFF"
        ;;
esac