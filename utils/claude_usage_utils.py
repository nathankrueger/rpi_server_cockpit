"""Claude Code usage-limit lookup.

Reads the OAuth access token Claude Code stores for the logged-in account and asks
Anthropic for the current rate-limit utilization (session window, weekly window, and
any model-scoped weekly windows). Only the resulting percentages are returned - the
token never leaves this module.

The token is deliberately *not* refreshed here. Refreshing rotates the refresh token,
which would invalidate the copy Claude Code holds; instead an expired token surfaces
as an 'expired' error and clears itself the next time Claude Code runs.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

# Claude Code authenticates to this endpoint with an OAuth bearer token, which the API
# only accepts alongside this beta opt-in header.
_OAUTH_BETA = 'oauth-2025-04-20'
_ANTHROPIC_VERSION = '2023-06-01'

_DEFAULT_CACHE_SECONDS = 60
_DEFAULT_TIMEOUT = 10

# The usage endpoint is itself rate limited (429 with a Retry-After of several minutes),
# so a forced refresh may skip the cache at most this often. Without this floor, holding
# down the refresh button trips the limit for everyone using the dashboard.
_DEFAULT_FORCE_MIN_INTERVAL = 15

# Fallback backoff when a 429 arrives without a usable Retry-After header.
_DEFAULT_RATE_LIMIT_BACKOFF = 120

# Bounds how often the upstream API is hit no matter how many browser tabs are polling.
_cache_lock = threading.Lock()
_cached_result = None
_cached_at = 0.0

# Last successful lookup, kept so a transient failure can keep showing real numbers
# (flagged stale) instead of blanking the tile.
_last_success = None
_last_success_at = 0.0

# Timestamps guarding the upstream call itself.
_last_upstream_call = 0.0
_retry_after_until = 0.0

# Human-readable names for the limit windows the API reports.
_KIND_LABELS = {
    'session': 'SESSION',
    'weekly_all': 'WEEKLY',
    'weekly_scoped': 'WEEKLY',
    'weekly_opus': 'WEEKLY (OPUS)',
}


def _read_access_token(credentials_path):
    """Return (token, error). Exactly one of the two is None."""
    path = os.path.expanduser(credentials_path)

    if not os.path.exists(path):
        return None, 'no_credentials'

    try:
        with open(path, 'r') as f:
            creds = json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"Claude usage: cannot read {path}: {e}")
        return None, 'bad_credentials'

    oauth = creds.get('claudeAiOauth') or {}
    token = oauth.get('accessToken')
    if not token:
        return None, 'bad_credentials'

    # expiresAt is epoch milliseconds. A doomed request would just 401, so skip it.
    expires_at = oauth.get('expiresAt')
    if isinstance(expires_at, (int, float)) and expires_at / 1000.0 <= time.time():
        return None, 'expired'

    return token, None


def _limit_label(entry):
    """Build a display label for one limit window."""
    label = _KIND_LABELS.get(entry.get('kind'), str(entry.get('kind', 'LIMIT')).upper())

    # Model-scoped weekly windows (e.g. the separate Opus/Fable weekly pool) share the
    # 'weekly_scoped' kind and are only distinguishable by their scope.
    scope = entry.get('scope') or {}
    model_name = (scope.get('model') or {}).get('display_name')
    if model_name:
        label = f"{label} ({model_name.upper()})"

    return label


def _normalize(payload):
    """Reduce the API payload to the limit rows the tile renders."""
    limits = []

    for entry in payload.get('limits') or []:
        percent = entry.get('percent')
        if percent is None:
            continue
        limits.append({
            'id': f"{entry.get('kind')}:{_limit_label(entry)}",
            'label': _limit_label(entry),
            'percent_used': float(percent),
            'percent_remaining': max(0.0, 100.0 - float(percent)),
            'resets_at': entry.get('resets_at'),
            'severity': entry.get('severity', 'normal'),
        })

    # Older payloads may only carry the two top-level windows.
    if not limits:
        for key, label in (('five_hour', 'SESSION'), ('seven_day', 'WEEKLY')):
            window = payload.get(key) or {}
            utilization = window.get('utilization')
            if utilization is None:
                continue
            limits.append({
                'id': key,
                'label': label,
                'percent_used': float(utilization),
                'percent_remaining': max(0.0, 100.0 - float(utilization)),
                'resets_at': window.get('resets_at'),
                'severity': 'normal',
            })

    return limits


def _fetch(token, timeout):
    """Call the usage endpoint. Returns the normalized result dict."""
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            'Authorization': f'Bearer {token}',
            'anthropic-beta': _OAUTH_BETA,
            'anthropic-version': _ANTHROPIC_VERSION,
            'Accept': 'application/json',
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {'available': False, 'error': 'unauthorized'}
        if e.code == 429:
            # The endpoint hands back a Retry-After in seconds (observed: ~220).
            retry_after = _parse_retry_after(e.headers.get('Retry-After'))
            print(f"Claude usage: rate limited, retrying in {retry_after}s")
            return {'available': False, 'error': 'rate_limited', 'retry_after': retry_after}
        print(f"Claude usage: HTTP {e.code} from usage endpoint")
        return {'available': False, 'error': 'unreachable'}
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        print(f"Claude usage: request failed: {e}")
        return {'available': False, 'error': 'unreachable'}

    return {'available': True, 'limits': _normalize(payload)}


def _parse_retry_after(header_value):
    """Seconds to wait per a Retry-After header, falling back to a fixed backoff."""
    try:
        seconds = int(float(header_value))
    except (TypeError, ValueError):
        return _DEFAULT_RATE_LIMIT_BACKOFF
    # Clamp: a missing/zero value must still back off, and an absurd one shouldn't
    # wedge the tile for hours.
    return max(1, min(seconds, 3600))


def _with_last_good(result):
    """Fall back to the last successful reading when a lookup fails.

    Real percentages that are a few minutes old beat blanking the tile - especially
    for a rate-limit blip, where the numbers almost certainly haven't moved. The
    'stale' flag lets the UI say so.
    """
    if result.get('available') or _last_success is None:
        return result

    return dict(
        _last_success,
        stale=True,
        error=result.get('error'),
        retry_after=result.get('retry_after'),
        fetched_at=_last_success_at,
    )


def get_claude_usage(config, force=False):
    """Get current Claude usage limits, honoring the configured cache window.

    Args:
        config: settings dict from config_loader.get_claude_usage_config()
        force: skip the cache window (used by the refresh button). Still subject to
            'force_min_interval' and to any active rate-limit backoff - the upstream
            endpoint is rate limited, so force is not an unconditional bypass.

    Returns:
        dict with 'enabled', and when enabled either 'available': True plus a
        'limits' list (possibly flagged 'stale'), or 'available': False plus an
        'error' code and, when rate limited, a 'retry_after' in seconds.
    """
    global _cached_result, _cached_at, _last_success, _last_success_at
    global _last_upstream_call, _retry_after_until

    if not config.get('enabled'):
        return {'enabled': False}

    cache_seconds = float(config.get('cache_seconds', _DEFAULT_CACHE_SECONDS))
    timeout = float(config.get('request_timeout', _DEFAULT_TIMEOUT))
    credentials_path = config.get('credentials_path', '~/.claude/.credentials.json')
    force_min_interval = float(config.get('force_min_interval', _DEFAULT_FORCE_MIN_INTERVAL))

    with _cache_lock:
        now = time.time()

        # An active 429 backoff outranks everything, including force: calling again
        # before Retry-After elapses just extends the lockout.
        if now < _retry_after_until:
            throttled = {
                'available': False,
                'error': 'rate_limited',
                'retry_after': int(_retry_after_until - now),
            }
            return dict(_with_last_good(throttled), enabled=True, cached=True)

        # Rapid repeat presses of the refresh button serve the cache instead.
        if force and (now - _last_upstream_call) < force_min_interval:
            force = False

        if not force and _cached_result is not None and (now - _cached_at) < cache_seconds:
            return dict(_cached_result, enabled=True, cached=True)

        token, error = _read_access_token(credentials_path)
        if error:
            result = {'available': False, 'error': error}
        else:
            _last_upstream_call = time.time()
            result = _fetch(token, timeout)

        if result.get('error') == 'rate_limited':
            _retry_after_until = time.time() + result.get('retry_after', _DEFAULT_RATE_LIMIT_BACKOFF)

        result['fetched_at'] = time.time()

        if result.get('available'):
            _last_success = result
            _last_success_at = result['fetched_at']
        else:
            result = _with_last_good(result)

        _cached_result = result
        _cached_at = time.time()

    return dict(result, enabled=True, cached=False)
