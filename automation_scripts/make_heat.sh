#!/bin/bash

# Default duration in seconds
TIME=30

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --duration)
            TIME="$2"
            shift 2
            ;;
        -d)
            TIME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--duration|-d SECONDS]"
            echo "  --duration, -d    Duration in seconds (default: 30)"
            exit 1
            ;;
    esac
done

# Validate that TIME is a positive integer
if ! [[ "$TIME" =~ ^[0-9]+$ ]] || [ "$TIME" -le 0 ]; then
    echo "ERROR: Duration must be a positive integer"
    exit 1
fi

echo "Starting CPU stress test for $TIME seconds..."

stress-ng --cpu 2 --timeout ${TIME}s&

for ((i = 1; i <= $TIME; i++)) do
    echo "$i / $TIME seconds"
    sleep 1
done

echo "Stress test completed!"