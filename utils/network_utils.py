"""Network and internet connectivity utilities."""
from utils.subprocess_helper import run as subprocess_run

# Kernel routing table. Columns: Iface Destination Gateway Flags RefCnt Use
# Metric Mask MTU Window IRTT. Addresses are little-endian hex, so the default
# route (0.0.0.0/0) is the row whose Destination is all zeros.
_ROUTE_FILE = '/proc/net/route'


def get_primary_interface(fallback=None):
    """Return the interface carrying the default route.

    When several interfaces have a default route (e.g. onboard wifi plus a USB
    wifi dongle), the kernel sends traffic over the one with the lowest metric,
    so that's the one worth reporting on. Reads procfs directly - no
    subprocess, cheap enough to poll.

    Returns `fallback` if no default route exists (offline / link down).
    """
    try:
        best_iface, best_metric = None, None
        with open(_ROUTE_FILE, 'r') as f:
            next(f)  # header
            for line in f:
                fields = line.split()
                if len(fields) < 7:
                    continue
                iface, destination, metric = fields[0], fields[1], int(fields[6])
                if destination != '00000000' or iface == 'lo':
                    continue
                if best_metric is None or metric < best_metric:
                    best_iface, best_metric = iface, metric
        return best_iface or fallback
    except Exception as e:
        print(f"Error detecting primary network interface: {e}")
        return fallback


def check_internet_connectivity():
    """Check internet connectivity by pinging DNS servers."""
    hosts = ['8.8.8.8', '1.1.1.1']  # Google DNS and Cloudflare DNS

    for host in hosts:
        try:
            result = subprocess_run(
                ['ping', '-c', '1', '-W', '2', host],
                capture_output=True,
                timeout=3
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False
