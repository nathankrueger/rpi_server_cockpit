#!/bin/bash

# Default duration in seconds
TIME=30
# Default number of CPU cores
CORES=2

# Function to display usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -d, --duration SECONDS    Duration in seconds (default: 30)"
    echo "  -c, --cores NUMBER        Number of CPU cores to stress (default: 2)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --duration 60 --cores 4"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --duration|-d)
            TIME="$2"
            shift 2
            ;;
        --cores|-c)
            CORES="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo ""
            show_usage
            exit 1
            ;;
    esac
done

# Validate that TIME is a positive integer
if ! [[ "$TIME" =~ ^[0-9]+$ ]] || [ "$TIME" -le 0 ]; then
    echo "ERROR: Duration must be a positive integer"
    exit 1
fi

# Validate that CORES is a positive integer
if ! [[ "$CORES" =~ ^[0-9]+$ ]] || [ "$CORES" -le 0 ]; then
    echo "ERROR: Number of cores must be a positive integer"
    exit 1
fi

echo "Starting CPU stress test using $CORES cores for $TIME seconds..."

stress-ng --cpu $CORES --timeout ${TIME}s&

for ((i = 1; i <= $TIME; i++)) do
    echo "$i / $TIME seconds"
    sleep 1
done

echo "Stress test completed!"