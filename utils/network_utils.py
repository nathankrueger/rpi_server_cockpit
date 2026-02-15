"""Network and internet connectivity utilities."""
from utils.subprocess_helper import run as subprocess_run


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
