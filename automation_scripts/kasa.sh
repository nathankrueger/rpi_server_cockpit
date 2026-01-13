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
PLUG_NAME=""
ACTION=""
KASA_USER=""
KASA_PASS=""

# Function to discover device IP by name substring
# Returns the IP address of the first device matching the name substring
find_device_by_name() {
    local name_substr="$1"
    local auth_flags=""

    if [[ -n "$KASA_USER" ]] && [[ -n "$KASA_PASS" ]]; then
        auth_flags="--username $KASA_USER --password $KASA_PASS"
    fi

    # Run discovery and parse output
    local discovery_output=$(kasa $auth_flags discover 2>&1)

    # Look for device name containing the substring (case-insensitive)
    local device_ip=""
    local in_device_block=false
    local current_name=""
    local current_ip=""

    while IFS= read -r line; do
        # Check for device name line (== Name ==)
        if [[ "$line" =~ ^==\ (.+)\ ==$ ]]; then
            current_name="${BASH_REMATCH[1]}"
            in_device_block=true
            current_ip=""
        fi

        # Check for IP in different formats
        if [[ "$line" =~ ^IP:\ +(.+)$ ]]; then
            current_ip="${BASH_REMATCH[1]}"
        elif [[ "$line" =~ ^Host:\ +(.+)$ ]]; then
            current_ip="${BASH_REMATCH[1]}"
        fi

        # If we have both name and IP, check for match
        if [[ -n "$current_name" ]] && [[ -n "$current_ip" ]]; then
            if [[ "$current_name" =~ $name_substr ]] || [[ "${current_name,,}" =~ ${name_substr,,} ]]; then
                echo "$current_ip"
                return 0
            fi
            current_name=""
            current_ip=""
        fi
    done <<< "$discovery_output"

    return 1
}

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
    echo "Usage: $0 [-d|--discover] | (-i|--ip_addr <IP> | -n|--name <substring>) [-r|--read_state | -t|--toggle | -o|--on | -f|--off] [-u|--username <email>] [-p|--password <password>]"
    echo ""
    echo "Options:"
    echo "  -d, --discover           Discover and list all Kasa devices on the network"
    echo "  -i, --ip_addr <IP>       IP address of the Kasa smart plug"
    echo "  -n, --name <substring>   Match plug by name substring"
    echo "  -r, --read_state         Read and display current state"
    echo "  -t, --toggle             Toggle the plug state (ON->OFF or OFF->ON)"
    echo "  -o, --on                 Turn the plug ON"
    echo "  -f, --off                Turn the plug OFF"
    echo "  -u, --username <email>   Kasa account email (for newer devices)"
    echo "  -p, --password <pass>    Kasa account password (for newer devices)"
    echo ""
    echo "Note: For device control, either -i or -n is required."
    echo "      Newer devices require authentication via KASA_USERNAME/KASA_PASSWORD env vars or -u/-p flags."
    echo ""
    echo "Example:"
    echo "  $0 -d                    # List all devices"
    echo "  $0 -i 192.168.1.24 -r"
    echo "  $0 -n \"Living Room\" --toggle"
    echo "  $0 -i 192.168.1.47 --on -u your@email.com -p yourpassword"
    echo "  KASA_USERNAME=your@email.com KASA_PASSWORD=yourpass $0 -n \"Lamp\" --on"
    exit 1
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--discover)
            ACTION="discover"
            shift
            ;;
        -i|--ip_addr)
            PLUG_IP="$2"
            shift 2
            ;;
        -n|--name)
            PLUG_NAME="$2"
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
        -o|--on)
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
if [[ -z "$ACTION" ]]; then
    echo "Error: An action is required (-d, -r, -t, -o, or -f)"
    usage
fi

# For discover mode, we don't need IP or name
if [[ "$ACTION" != "discover" ]]; then
    if [[ -z "$PLUG_IP" ]] && [[ -z "$PLUG_NAME" ]]; then
        echo "Error: Either IP address (-i) or name (-n) is required"
        usage
    fi

    if [[ -n "$PLUG_IP" ]] && [[ -n "$PLUG_NAME" ]]; then
        echo "Error: Cannot specify both -i and -n. Use one or the other."
        usage
    fi
fi

# Check if kasa is installed
if ! command -v kasa &> /dev/null; then
    echo "Error: kasa command not found. Install with: pip3 install python-kasa"
    exit 1
fi

# Handle discover mode separately
if [[ "$ACTION" == "discover" ]]; then
    echo "Discovering Kasa devices on the network..."
    if [[ -n "$KASA_USER" ]] && [[ -n "$KASA_PASS" ]]; then
        kasa --username "$KASA_USER" --password "$KASA_PASS" discover
    else
        kasa discover
    fi
    exit 0
fi

# Build kasa command with authentication if provided
if [[ -n "$PLUG_NAME" ]]; then
    # Discover device by name and get IP
    echo "Discovering device with name matching: $PLUG_NAME"
    PLUG_IP=$(find_device_by_name "$PLUG_NAME")
    if [[ -z "$PLUG_IP" ]]; then
        echo "Error: No device found matching name '$PLUG_NAME'"
        exit 1
    fi
    echo "Found device at IP: $PLUG_IP"
fi

# Build command with IP (either provided or discovered)
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