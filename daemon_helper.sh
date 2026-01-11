#!/bin/bash
# Simple daemon launcher - double fork to detach completely
# Usage: daemon_helper.sh <command>

if [ $# -eq 0 ]; then
    echo "Usage: $0 <command>"
    exit 1
fi

# Simple double-fork: creates an orphan process that gets adopted by init
# No special permissions, no cgroup manipulation, just pure Unix process management
(
    (
        exec "$@" </dev/null >/dev/null 2>&1 &
    ) &
)

exit 0
