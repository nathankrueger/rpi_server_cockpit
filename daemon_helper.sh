#!/bin/bash
# Helper script to properly daemonize a process
# Usage: daemon_helper.sh <command>

if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>"
    exit 1
fi

# Double fork to create proper daemon
(
    # First fork - creates child in background
    if [ "$(uname)" = "Linux" ]; then
        # Use nohup and disown for maximum detachment
        nohup setsid "$@" </dev/null >/dev/null 2>&1 &
        disown
    else
        nohup "$@" </dev/null >/dev/null 2>&1 &
    fi
) &

# Parent exits immediately
exit 0
