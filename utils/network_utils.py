"""Network and internet connectivity utilities."""
import subprocess


def check_internet_connectivity():
    """Check internet connectivity by pinging DNS servers."""
    hosts = ['8.8.8.8', '1.1.1.1']  # Google DNS and Cloudflare DNS

    for host in hosts:
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', host],
                capture_output=True,
                timeout=3
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False
