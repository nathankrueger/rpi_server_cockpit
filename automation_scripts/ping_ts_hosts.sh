#!/bin/bash

# Get the list of Tailscale peers and extract their info
# Using mapfile to properly handle the JSON array
mapfile -t PEERS < <(tailscale status --json | jq -c '.Peer[]')

if [ ${#PEERS[@]} -eq 0 ]; then
    echo "No Tailscale peers found."
    exit 0
fi

echo "Found ${#PEERS[@]} Tailscale peer(s)"
echo ""

# Loop through each peer
for i in "${!PEERS[@]}"; do
    if [ $i -ne 0 ]; then
        echo ""
        echo "----------------------------------------"
        echo ""
    fi

    PEER="${PEERS[$i]}"

    # Extract hostname and IP address from the peer JSON
    HOSTNAME=$(echo "$PEER" | jq -r '.HostName')
    IPADDR=$(echo "$PEER" | jq -r '.TailscaleIPs[0]')
    DNS_NAME=$(echo "$PEER" | jq -r '.DNSName' | sed 's/\.$//')  # Remove trailing dot

    echo "Peer $((i+1)) of ${#PEERS[@]}"
    echo "Hostname: $HOSTNAME"
    echo "DNS Name: $DNS_NAME"
    echo "IP Address: $IPADDR"
    echo ""

    # Ping the peer
    echo "Pinging $HOSTNAME ($IPADDR)..."
    if ping -c 4 -W 5 "$IPADDR" > /dev/null 2>&1; then
        echo "✓ Ping successful"
    else
        echo "✗ Ping failed"
    fi
done

echo ""
echo "----------------------------------------"
echo "Ping scan complete."
