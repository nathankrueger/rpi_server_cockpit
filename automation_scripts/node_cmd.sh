#!/bin/bash

# Node Command Script
# Sends commands to nodes via the gateway API

# Get the script directory and workspace root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"

# Source .env file if it exists
if [[ -f "$WORKSPACE_ROOT/.env" ]]; then
    source "$WORKSPACE_ROOT/.env"
fi

# Default values
NODE_ID=""
BROADCAST=false
COMMAND=""
CMD_ARGS=""
CLI_GATEWAY_HOST=""
CLI_GATEWAY_PORT=""

# Function to display usage
usage() {
    echo "Usage: $0 (-n <node_id> | -b) -c <command> [-a <args>] [-g <host>] [-p <port>]"
    echo ""
    echo "Options:"
    echo "  -n <node_id>    Target node ID (e.g., pz2w2-shop)"
    echo "  -b              Broadcast command to all nodes"
    echo "  -c <command>    Command to send (e.g., ping, status)"
    echo "  -a <args>       Optional command arguments (comma-separated)"
    echo "  -g <host>       Gateway hostname (overrides GATEWAY_HOST env var)"
    echo "  -p <port>       Gateway port (overrides GATEWAY_PORT env var)"
    echo ""
    echo "Note: -n and -b are mutually exclusive."
    echo ""
    echo "Environment variables (used if -g/-p not specified):"
    echo "  GATEWAY_HOST    Gateway hostname (default: localhost)"
    echo "  GATEWAY_PORT    Gateway port (default: 5001)"
    echo ""
    echo "Examples:"
    echo "  $0 -n pz2w2-shop -c ping -a hello"
    echo "  $0 -b -c ping"
    echo "  $0 -g 192.168.1.100 -p 5001 -b -c status"
    exit 1
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--node)
            NODE_ID="$2"
            shift 2
            ;;
        -b|--broadcast)
            BROADCAST=true
            shift
            ;;
        -c|--command)
            COMMAND="$2"
            shift 2
            ;;
        -a|--args)
            CMD_ARGS="$2"
            shift 2
            ;;
        -g|--gateway)
            CLI_GATEWAY_HOST="$2"
            shift 2
            ;;
        -p|--port)
            CLI_GATEWAY_PORT="$2"
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

# Validate inputs
if [[ -z "$COMMAND" ]]; then
    echo "Error: Command (-c) is required"
    usage
fi

if [[ -z "$NODE_ID" ]] && [[ "$BROADCAST" == false ]]; then
    echo "Error: Either node ID (-n) or broadcast (-b) is required"
    usage
fi

if [[ -n "$NODE_ID" ]] && [[ "$BROADCAST" == true ]]; then
    echo "Error: Cannot specify both -n and -b. Use one or the other."
    usage
fi

# Set gateway connection (CLI args take precedence over env vars)
if [[ -n "$CLI_GATEWAY_HOST" ]]; then
    GATEWAY_HOST="$CLI_GATEWAY_HOST"
else
    GATEWAY_HOST="${GATEWAY_HOST:-localhost}"
fi

if [[ -n "$CLI_GATEWAY_PORT" ]]; then
    GATEWAY_PORT="$CLI_GATEWAY_PORT"
else
    GATEWAY_PORT="${GATEWAY_PORT:-5001}"
fi

# Build the args array for JSON
if [[ -n "$CMD_ARGS" ]]; then
    # Convert comma-separated args to JSON array
    IFS=',' read -ra ARG_ARRAY <<< "$CMD_ARGS"
    ARGS_JSON=$(printf '%s\n' "${ARG_ARRAY[@]}" | jq -R . | jq -s .)
else
    ARGS_JSON="[]"
fi

# Set node_id based on broadcast or specific node
if [[ "$BROADCAST" == true ]]; then
    TARGET_NODE=""
    echo "Broadcasting command '$COMMAND' to all nodes..."
else
    TARGET_NODE="$NODE_ID"
    echo "Sending command '$COMMAND' to node '$NODE_ID'..."
fi

# Build JSON payload
JSON_PAYLOAD=$(jq -n \
    --arg cmd "$COMMAND" \
    --argjson args "$ARGS_JSON" \
    --arg node_id "$TARGET_NODE" \
    '{cmd: $cmd, args: $args, node_id: $node_id}')

echo "Gateway: http://$GATEWAY_HOST:$GATEWAY_PORT/command"
echo "Payload: $JSON_PAYLOAD"
echo ""

# Send the request
RESPONSE=$(curl -s -X POST "http://$GATEWAY_HOST:$GATEWAY_PORT/command" \
    -H "Content-Type: application/json" \
    -d "$JSON_PAYLOAD")

echo "Response:"
echo "$RESPONSE" | jq . 2>/dev/null || echo "$RESPONSE"
