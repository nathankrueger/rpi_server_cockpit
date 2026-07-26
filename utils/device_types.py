"""Device-type dispatch registry.

Maps a device's `type` to (a) a status poller and (b) a set of command
handlers. The broadcaster uses `get_status`; the command route uses `commands`.
Adding a new device kind (e.g. an IP camera) means registering one new entry
here plus a frontend renderer — no other wiring.

Each command handler takes `(device_config, value)` where `value` is the
optional numeric payload from the request (used by volume/seek).
"""
from utils import bluos_utils


def _port(device):
    return device.get('port', bluos_utils.DEFAULT_PORT)


def _clamp_volume(device, value):
    """Clamp a requested volume into [0, volume_max] — hard safety cap so no
    client can drive the player past the configured limit."""
    vmax = int(device.get('volume_max', 60))
    return max(0, min(vmax, int(value)))


DEVICE_TYPES = {
    'bluos': {
        'get_status': lambda dev: bluos_utils.get_status(dev['host'], _port(dev)),
        'commands': {
            'play': lambda dev, value: bluos_utils.play(dev['host'], _port(dev)),
            'pause': lambda dev, value: bluos_utils.pause(dev['host'], _port(dev)),
            'toggle': lambda dev, value: bluos_utils.toggle(dev['host'], _port(dev)),
            'next': lambda dev, value: bluos_utils.skip(dev['host'], _port(dev)),
            'prev': lambda dev, value: bluos_utils.back(dev['host'], _port(dev)),
            'seek': lambda dev, value: bluos_utils.seek(dev['host'], _port(dev), int(value)),
            'volume': lambda dev, value: bluos_utils.set_volume(
                dev['host'], _port(dev), _clamp_volume(dev, value)
            ),
        },
    },
}


def get_status_for(device):
    """Poll a device's status via its type handler. Raises on unknown type."""
    handler = DEVICE_TYPES.get(device.get('type'))
    if not handler:
        raise ValueError(f"Unknown device type: {device.get('type')}")
    return handler['get_status'](device)


def run_command(device, action, value=None):
    """Dispatch a command to a device by type. Returns False for unknown
    type/action, True on success."""
    handler = DEVICE_TYPES.get(device.get('type'))
    if not handler:
        return False
    command = handler['commands'].get(action)
    if not command:
        return False
    command(device, value)
    return True
