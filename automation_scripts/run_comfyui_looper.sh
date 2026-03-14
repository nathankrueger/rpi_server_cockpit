#!/bin/bash
set -e

# ComfyUI Looper Wrapper
#
# Boots the desktop PC (optional), starts run_interactive.sh on the PC via SSH
# (fire-and-forget), then runs run_interactive.sh locally on the Pi pointing
# at the PC's ComfyUI instance.
#
# The local process is the foreground process whose stdout the automation
# panel streams. Cancelling the automation kills this process.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KASA_SCRIPT="$SCRIPT_DIR/kasa.sh"
LOOPER_SCRIPT="$HOME/dev/comfyui_looper/run_interactive.sh"

# Defaults (match remote_machine_config.json values)
SSH_USER="${REMOTE_SSH_USER:-natek}"
PLUG_IP="${REMOTE_PLUG_IP:-192.168.1.59}"
BOOT_TIMEOUT=120
START_PC=false
LOOPER_PORT=5020

usage() {
    cat <<EOF
Usage: $0 [options] [-- extra args for run_interactive.sh]

Options:
  -S            Start (power cycle) the desktop PC if it's not reachable
  -L <port>     Looper web UI port (default: $LOOPER_PORT)
  -h            Show this help

Environment:
  DESKTOP_PC_IP       PC's IP address (auto-injected by announced IPs system)
  REMOTE_SSH_USER     SSH user on the PC (default: natek)
  REMOTE_PLUG_IP      Kasa smart plug IP (default: 192.168.1.59)
EOF
    exit 1
}

# --- Parse args ---
PASSTHROUGH=()
while [ $# -gt 0 ]; do
    case "$1" in
        -S) START_PC=true; shift ;;
        -L) LOOPER_PORT="$2"; shift 2 ;;
        -h) usage ;;
        --) shift; PASSTHROUGH+=("$@"); break ;;
        *)  PASSTHROUGH+=("$1"); shift ;;
    esac
done

# --- Require DESKTOP_PC_IP ---
PC_IP="${DESKTOP_PC_IP:-}"
if [ -z "$PC_IP" ]; then
    echo "ERROR: DESKTOP_PC_IP not set (PC has not announced its IP)"
    echo "The PC must have announced its IP at least once via POST /api/announce"
    exit 1
fi

# --- SSH reachability check ---
check_ssh() {
    timeout 2 bash -c "echo >/dev/tcp/$PC_IP/22" 2>/dev/null
}

# --- Boot PC if needed ---
if ! check_ssh; then
    if [ "$START_PC" = true ]; then
        echo "PC not reachable at $PC_IP:22, power cycling plug..."
        # Power cycle: off → wait → on (handles plug already being on)
        bash "$KASA_SCRIPT" -i "$PLUG_IP" --off 2>&1 || true
        sleep 3
        bash "$KASA_SCRIPT" -i "$PLUG_IP" --on 2>&1
        echo "Plug ON — waiting up to ${BOOT_TIMEOUT}s for SSH..."

        elapsed=0
        while [ $elapsed -lt $BOOT_TIMEOUT ]; do
            if check_ssh; then
                echo "SSH ready after ${elapsed}s"
                break
            fi
            sleep 2
            elapsed=$((elapsed + 2))
            echo "  waiting... ${elapsed}s / ${BOOT_TIMEOUT}s"
        done

        if ! check_ssh; then
            echo "ERROR: PC did not come online within ${BOOT_TIMEOUT}s"
            exit 1
        fi
    else
        echo "ERROR: PC not reachable at $PC_IP:22 (use -S to auto-boot)"
        exit 1
    fi
else
    echo "PC is online at $PC_IP:22"
fi

# --- Fire-and-forget: start run_interactive.sh on the PC via SSH ---
# The PC's OpenSSH default shell is wsl.exe which doesn't support -c,
# so we pipe commands via stdin with -T (no PTY).
# nohup + background + redirects ensure the remote process survives SSH disconnect.
echo "Starting run_interactive.sh on PC (fire-and-forget)..."
ssh -T -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 \
    -o BatchMode=yes "${SSH_USER}@${PC_IP}" <<'REMOTE'
nohup ~/dev/comfyui_looper/run_interactive.sh -z </dev/null &>/dev/null &
exit
REMOTE
echo "Remote run_interactive.sh launched on PC"

# --- Run locally on Pi (foreground) ---
# This is the automation's visible output. exec replaces the shell so
# kill_proc_tree on cancel will properly terminate the looper.
echo "Starting local looper with ComfyUI at http://${PC_IP}:8188..."
echo ""
exec bash "$LOOPER_SCRIPT" \
    -u "http://${PC_IP}:8188" \
    -z \
    -L "$LOOPER_PORT" \
    "${PASSTHROUGH[@]}"
