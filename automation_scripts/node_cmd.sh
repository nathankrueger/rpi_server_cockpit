#!/bin/bash

# Node Command Script
# Sends commands to nodes via the gateway API
#
# Exit codes:
#   0 - Success
#   1 - HTTP error (4xx/5xx)
#   2 - Gateway unreachable
#   3 - Timeout waiting for node response

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
DISCOVER=false
COMMAND=""
CMD_ARGS=""
CLI_GATEWAY_HOST=""
CLI_GATEWAY_PORT=""
WAIT_RESPONSE=false
TIMEOUT=5

# Function to display usage
usage() {
    echo "Usage: $0 (-n <node_id> | -b) -c <command> [-a <args>] [-g <host>] [-p <port>] [-w] [-t <timeout>]"
    echo "       $0 -d [-a <retries>] [-g <host>] [-p <port>] [-t <timeout>]"
    echo ""
    echo "Options:"
    echo "  -n <node_id>    Target node ID (e.g., ab01)"
    echo "  -b              Broadcast command to all nodes"
    echo "  -c <command>    Command to send (e.g., ping, params)"
    echo "  -d              Discover all reachable nodes"
    echo "  -a <args>       Optional command arguments (comma-separated; for -d: retry count)"
    echo "  -g <host>       Gateway hostname (overrides GATEWAY_HOST env var)"
    echo "  -p <port>       Gateway port (overrides GATEWAY_PORT env var)"
    echo "  -w              Wait for response (uses GET endpoint)"
    echo "  -t <timeout>    Connection timeout in seconds (default: 5)"
    echo ""
    echo "Note: -n and -b are mutually exclusive. -w requires -n (no broadcast)."
    echo "      -d is a standalone operation (no -c, -n, -b, or -w needed)."
    echo ""
    echo "Environment variables (used if -g/-p not specified):"
    echo "  GATEWAY_HOST    Gateway hostname (default: localhost)"
    echo "  GATEWAY_PORT    Gateway port (default: 5001)"
    echo ""
    echo "Examples:"
    echo "  $0 -n ab01 -c ping                  # Fire-and-forget ping"
    echo "  $0 -n ab01 -c params -w             # Read node parameters"
    echo "  $0 -n ab01 -c txpwr -a 22           # Set TX power to 22 dBm"
    echo "  $0 -b -c ping                       # Broadcast ping"
    echo "  $0 -d                               # Discover all reachable nodes"
    echo "  $0 -d -a 5                          # Discover with 5 retries"
    exit 1
}

# Build query string from comma-separated args for GET requests
build_query_string() {
    local args="$1"
    if [[ -z "$args" ]]; then
        echo ""
        return
    fi
    local query=""
    IFS=',' read -ra ARG_ARRAY <<< "$args"
    for arg in "${ARG_ARRAY[@]}"; do
        query+="&a=$(printf '%s' "$arg" | jq -sRr @uri)"
    done
    echo "?${query:1}"  # Remove leading &
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
        -d|--discover)
            DISCOVER=true
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
        -w|--wait)
            WAIT_RESPONSE=true
            shift
            ;;
        -t|--timeout)
            TIMEOUT="$2"
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
if [[ "$DISCOVER" == true ]]; then
    # Discovery mode: -c, -n, -b, -w are not used
    if [[ -n "$COMMAND" ]] || [[ -n "$NODE_ID" ]] || [[ "$BROADCAST" == true ]] || [[ "$WAIT_RESPONSE" == true ]]; then
        echo "Error: -d is standalone (do not combine with -c, -n, -b, or -w)"
        usage
    fi
else
    if [[ -z "$COMMAND" ]]; then
        echo "Error: Command (-c) or discover (-d) is required"
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

    if [[ "$WAIT_RESPONSE" == true ]] && [[ -z "$NODE_ID" ]]; then
        echo "Error: -w requires a node ID (-n), broadcast not supported for response wait"
        usage
    fi
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

# Determine request type
if [[ "$DISCOVER" == true ]]; then
    # GET /discover[?retries=N]
    URL="http://$GATEWAY_HOST:$GATEWAY_PORT/discover"
    if [[ -n "$CMD_ARGS" ]]; then
        URL="$URL?retries=$CMD_ARGS"
    fi
    echo "Discovering reachable nodes..."
    echo "Gateway: $URL"
    echo ""

    RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout "$TIMEOUT" --max-time 30 "$URL" 2>&1)
    CURL_EXIT=$?
elif [[ "$WAIT_RESPONSE" == true ]]; then
    # GET request - wait for response
    QUERY=$(build_query_string "$CMD_ARGS")
    URL="http://$GATEWAY_HOST:$GATEWAY_PORT/$COMMAND/$NODE_ID$QUERY"
    echo "Sending '$COMMAND' to node '$NODE_ID' (waiting for response)..."
    echo "Gateway: $URL"
    echo ""

    RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout "$TIMEOUT" "$URL" 2>&1)
    CURL_EXIT=$?
else
    # POST request - fire and forget
    if [[ -n "$CMD_ARGS" ]]; then
        IFS=',' read -ra ARG_ARRAY <<< "$CMD_ARGS"
        ARGS_JSON=$(printf '%s\n' "${ARG_ARRAY[@]}" | jq -R . | jq -s .)
    else
        ARGS_JSON="[]"
    fi

    if [[ "$BROADCAST" == true ]]; then
        TARGET_NODE=""
        echo "Broadcasting command '$COMMAND' to all nodes..."
    else
        TARGET_NODE="$NODE_ID"
        echo "Sending command '$COMMAND' to node '$NODE_ID'..."
    fi

    JSON_PAYLOAD=$(jq -n \
        --arg cmd "$COMMAND" \
        --argjson args "$ARGS_JSON" \
        --arg node_id "$TARGET_NODE" \
        '{cmd: $cmd, args: $args, node_id: $node_id}')

    echo "Gateway: http://$GATEWAY_HOST:$GATEWAY_PORT/command"
    echo "Payload: $JSON_PAYLOAD"
    echo ""

    RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout "$TIMEOUT" \
        -X POST "http://$GATEWAY_HOST:$GATEWAY_PORT/command" \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD" 2>&1)
    CURL_EXIT=$?
fi

# Check for connection errors
if [[ $CURL_EXIT -ne 0 ]]; then
    echo "Error: Gateway unreachable at $GATEWAY_HOST:$GATEWAY_PORT"
    echo "       Check that the gateway server is running."
    exit 2
fi

# Parse response
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "Response:"
echo "$BODY" | jq . 2>/dev/null || echo "$BODY"

# Exit with appropriate code
case "$HTTP_CODE" in
    200)
        exit 0
        ;;
    504)
        echo ""
        echo "Error: Timeout waiting for node response"
        exit 3
        ;;
    *)
        exit 1
        ;;
esac
