#!/bin/bash

### NOTE: To use this, a sudoers entry is required: /etc/sudoers.d/pi-dashboard-media-library
#
#   # Command alias for minidlna configuration management
#   Cmnd_Alias MINIDLNA_CMDS = /usr/bin/sed -i * /etc/minidlna.conf, \
#                               /usr/bin/grep * /etc/minidlna.conf, \
#                               /usr/bin/tee -a /etc/minidlna.conf, \
#                               /usr/bin/systemctl restart minidlna, \
#                               /usr/bin/systemctl is-active minidlna
#
#   # Allow nkrueger to manage minidlna without password
#   nkrueger ALL=(root) NOPASSWD: MINIDLNA_CMDS


# Default media folder line to add/remove from minidlna.conf
DEFAULT_MEDIA_FOLDER="media_dir=V,/media/nkrueger/Elements6TB/"

# MiniDLNA configuration file
MINIDLNA_CONF="/etc/minidlna.conf"

# Function to display help message
show_help() {
    cat << EOF
Usage: $0 [OPTION]

Manage MiniDLNA media directory configuration.

Options:
  -h, --help                Show this help message and exit
  -q, --query               List all media_dir lines currently in minidlna.conf
  -e, --enable[=MEDIA_LINE] Add media directory line to minidlna.conf
                            If MEDIA_LINE is not provided, uses default:
                            $DEFAULT_MEDIA_FOLDER
  -d, --disable[=MEDIA_LINE] Remove media directory line from minidlna.conf
                            If MEDIA_LINE is not provided, uses default:
                            $DEFAULT_MEDIA_FOLDER

Examples:
  Query current media directories:
    $0 -q

  Enable default media folder:
    $0 -e

  Enable custom media folder (note: short options use space, not =):
    $0 -e 'media_dir=V,/media/other/path/'
    $0 --enable='media_dir=V,/media/other/path/'

  Disable default media folder:
    $0 -d

  Disable specific media folder:
    $0 -d 'media_dir=V,/media/other/path/'
    $0 --disable='media_dir=V,/media/other/path/'

Notes:
  - The script automatically restarts the minidlna service after changes
  - Requires sudo permissions (see sudoers configuration in script header)

EOF
    exit 0
}

# Custom argument parsing (getopt doesn't handle optional args well with short options)
ACTION=""
MEDIA_LINE=""

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            show_help
            ;;
        -q|--query)
            ACTION="query"
            shift
            ;;
        -e|--enable)
            ACTION="enable"
            shift
            # Check if next arg exists and doesn't start with -
            if [ $# -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                MEDIA_LINE="$1"
                shift
            else
                MEDIA_LINE="$DEFAULT_MEDIA_FOLDER"
            fi
            ;;
        --enable=*)
            ACTION="enable"
            MEDIA_LINE="${1#*=}"
            shift
            ;;
        -d|--disable)
            ACTION="disable"
            shift
            # Check if next arg exists and doesn't start with -
            if [ $# -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
                MEDIA_LINE="$1"
                shift
            else
                MEDIA_LINE="$DEFAULT_MEDIA_FOLDER"
            fi
            ;;
        --disable=*)
            ACTION="disable"
            MEDIA_LINE="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            ;;
    esac
done

# Validate that an action was specified
if [ -z "$ACTION" ]; then
    echo "Error: Must specify either --query, --enable, or --disable"
    exit 1
fi

# Check if minidlna.conf exists
if [ ! -f "$MINIDLNA_CONF" ]; then
    echo "Error: $MINIDLNA_CONF not found"
    exit 1
fi

# Handle query action
if [ "$ACTION" = "query" ]; then
    echo "Media directories configured in $MINIDLNA_CONF:"
    echo ""
    MEDIA_DIRS=$(sudo grep "^media_dir=" "$MINIDLNA_CONF")
    if [ -z "$MEDIA_DIRS" ]; then
        echo "  (none found)"
    else
        echo "$MEDIA_DIRS" | while IFS= read -r line; do
            echo "  $line"
        done
    fi
    exit 0
fi

# Escape special characters for sed
ESCAPED_LINE=$(echo "$MEDIA_LINE" | sed 's/[\/&]/\\&/g')

if [ "$ACTION" = "enable" ]; then
    # Check if the line already exists
    if sudo grep -qF "$MEDIA_LINE" "$MINIDLNA_CONF"; then
        echo "Media line already exists in $MINIDLNA_CONF"
        echo "Line: $MEDIA_LINE"
    else
        # Check if we need to remove the default line first (replace behavior)
        if [ "$MEDIA_LINE" != "$DEFAULT_MEDIA_FOLDER" ]; then
            # Remove default line if it exists
            ESCAPED_DEFAULT=$(echo "$DEFAULT_MEDIA_FOLDER" | sed 's/[\/&]/\\&/g')
            sudo sed -i "/^${ESCAPED_DEFAULT}/d" "$MINIDLNA_CONF"
        fi

        # Add the new line
        echo "$MEDIA_LINE" | sudo tee -a "$MINIDLNA_CONF" > /dev/null
        echo "Added media line to $MINIDLNA_CONF"
        echo "Line: $MEDIA_LINE"

        # Restart minidlna service if it's running
        if systemctl is-active --quiet minidlna; then
            echo "Restarting minidlna service..."
            sudo systemctl restart minidlna
        fi
    fi
elif [ "$ACTION" = "disable" ]; then
    # Check if the line exists
    if sudo grep -qF "$MEDIA_LINE" "$MINIDLNA_CONF"; then
        # Remove the line
        sudo sed -i "/^$(echo "$MEDIA_LINE" | sed 's/[\/&]/\\&/g')/d" "$MINIDLNA_CONF"
        echo "Removed media line from $MINIDLNA_CONF"
        echo "Line: $MEDIA_LINE"

        # Restart minidlna service if it's running
        if systemctl is-active --quiet minidlna; then
            echo "Restarting minidlna service..."
            sudo systemctl restart minidlna
        fi
    else
        echo "Media line not found in $MINIDLNA_CONF"
        echo "Line: $MEDIA_LINE"
    fi
fi

exit 0
