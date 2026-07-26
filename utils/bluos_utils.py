"""BluOS / Bluesound player client (stdlib only).

BluOS devices expose a REST API on port 11000: plain HTTP GET requests with
URL-encoded params and XML responses, no auth. This module is a thin client
over that API, using only the standard library (`urllib` + `xml.etree`), the
same approach as routes/external_api.py.

Under eventlet, `monkey_patch()` patches `socket`, so these blocking `urllib`
calls cooperatively yield and don't freeze the event loop.

See plans/bluos-api-notes.md for endpoint details.
"""
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_PORT = 11000
DEFAULT_TIMEOUT = 5


def _base_url(host, port=DEFAULT_PORT):
    return f"http://{host}:{port}"


def _get(host, port, path, params=None, timeout=DEFAULT_TIMEOUT):
    """GET a BluOS endpoint and return the parsed XML root element."""
    url = f"{_base_url(host, port)}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'rpi-dashboard'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return ET.fromstring(data)


def _text(root, tag, default=None):
    el = root.find(tag)
    return el.text if el is not None and el.text is not None else default


def _int(root, tag, default=None):
    val = _text(root, tag)
    if val is None:
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _normalize_image(image, host, port):
    """Turn a BluOS <image> value into an absolute, fetchable URL.

    Absolute URLs (service-hosted artwork) are returned as-is. Relative paths
    (often /Artwork...) are prefixed with the player address and given
    followRedirects=1 so a GET returns image bytes rather than a 302.
    """
    if not image:
        return None
    if image.startswith('http://') or image.startswith('https://'):
        return image
    sep = '&' if '?' in image else '?'
    return f"{_base_url(host, port)}{image}{sep}followRedirects=1"


def get_status(host, port=DEFAULT_PORT):
    """Return current player status as a plain dict.

    Keys: state, playing, title, artist, album, volume, secs, totlen, image,
    can_seek. `title` falls back through title1/title2/title3 (line 1 is usually
    the song). `can_seek` reflects whether the current source/track supports
    seeking (some streaming tracks report canSeek=0).
    """
    root = _get(host, port, '/Status')
    state = _text(root, 'state', 'stop')
    image = _normalize_image(_text(root, 'image'), host, port)
    # BluOS reports 'stream' (not 'play') for streaming sources like TidalConnect
    # / internet radio — both mean audio is playing.
    playing = state in ('play', 'stream')
    return {
        'state': state,
        'playing': playing,
        'title': _text(root, 'title1') or _text(root, 'name'),
        'artist': _text(root, 'title2') or _text(root, 'artist'),
        'album': _text(root, 'title3') or _text(root, 'album'),
        'volume': _int(root, 'volume', 0),
        'secs': _int(root, 'secs', 0),
        'totlen': _int(root, 'totlen', 0),
        'can_seek': bool(_int(root, 'canSeek', 0)),
        'image': image,
    }


def set_volume(host, port, level):
    """Set absolute volume 0-100. Callers clamp to volume_max before this."""
    _get(host, port, '/Volume', {'level': int(level)})


def play(host, port):
    _get(host, port, '/Play')


def pause(host, port):
    _get(host, port, '/Pause')


def toggle(host, port):
    """Toggle play/pause based on current state."""
    if get_status(host, port)['playing']:
        pause(host, port)
    else:
        play(host, port)


def stop(host, port):
    _get(host, port, '/Stop')


def skip(host, port):
    """Next track."""
    _get(host, port, '/Skip')


def back(host, port):
    """Previous track."""
    _get(host, port, '/Back')


def seek(host, port, secs):
    """Seek to an absolute position in seconds within the current track."""
    _get(host, port, '/Play', {'seek': int(secs)})


def fetch_artwork(image_url, timeout=DEFAULT_TIMEOUT):
    """Fetch artwork bytes for the art proxy. Returns (data, content_type)."""
    req = urllib.request.Request(image_url, headers={'User-Agent': 'rpi-dashboard'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
    return data, content_type
