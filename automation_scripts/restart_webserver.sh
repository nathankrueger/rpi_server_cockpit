#!/bin/bash

# Function to print usage
print_usage() {
    echo "Usage: $0 [-u|--update] [-h|--help]"
    echo ""
    echo "Options:"
    echo "  -u, --update    Pull latest changes from git before restarting"
    echo "  -h, --help      Show this help message"
}

# Parse options using getopt
OPTIONS=$(getopt -o "uh" -l "update,help" -- "$@")
if [ $? -ne 0 ]; then
    print_usage
    exit 1
fi

eval set -- "$OPTIONS"

UPDATE=false

while true; do
    case "$1" in
        -u|--update)
            UPDATE=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
    esac
done

# Run git pull if --update flag is set
if [ "$UPDATE" = true ]; then
    echo "Cloning latest server ..."
    git pull
    sleep 2
fi

sudo systemctl restart pi-dashboard