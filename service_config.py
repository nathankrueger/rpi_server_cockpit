"""
Service configuration for the Raspberry Pi Dashboard.

Each service should have:
- id: Unique identifier (used in URLs and state management)
- display_name: Name shown to users in the UI
- check_type: How to check if service is running ('systemd' or 'process')
- check_name: Service name for systemctl or process name for pgrep
- control_type: How to control the service ('systemd' or 'custom')
- control_name: Name used for control commands
- button_type: Type of button to display ('details' or 'link')
- link_url: (Optional) URL for link buttons, {hostname} will be replaced dynamically
"""

SERVICES = [
    {
        'id': 'tailscaled',
        'display_name': 'TAILSCALE',
        'check_type': 'systemd',
        'check_name': 'tailscaled',
        'control_type': 'systemd',
        'control_name': 'tailscaled',
        'button_type': 'details'
    },
    {
        'id': 'minidlnad',
        'display_name': 'MINIDLNA',
        'check_type': 'systemd',
        'check_name': 'minidlna',
        'control_type': 'systemd',
        'control_name': 'minidlna',
        'button_type': 'details'
    },
    {
        'id': 'smbd',
        'display_name': 'SAMBA',
        'check_type': 'systemd',
        'check_name': 'smbd',
        'control_type': 'systemd',
        'control_name': 'smbd',
        'button_type': 'details'
    },
    {
        'id': 'qbittorrent',
        'display_name': 'QBITTORRENT',
        'check_type': 'process',
        'check_name': 'qbittorrent-nox',
        'control_type': 'custom',
        'control_name': 'qbittorrent',
        'button_type': 'link',
        'link_url': 'http://{hostname}:8080'
    }
]

# Create a dictionary for quick lookups
SERVICE_MAP = {service['id']: service for service in SERVICES}

def get_service_config(service_id):
    return SERVICE_MAP.get(service_id)

def get_all_services():
    return SERVICES
