#!/bin/bash

# Parse options using getopt
OPTIONS=$(getopt -o "" -l "update" -- "$@")
if [ $? -ne 0 ]; then
    echo "Usage: $0 [--update]"
    exit 1
fi

eval set -- "$OPTIONS"

UPDATE=false

while true; do
    case "$1" in
        --update)
            UPDATE=true
            shift
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
fi

sudo systemctl restart pi-dashboard