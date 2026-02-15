"""Central subprocess runner.

All modules should use run() from here instead of subprocess.run() directly.
This provides a single place to swap between tpool (eventlet-safe) and direct execution.
"""
import subprocess

# Use eventlet.tpool when monkey-patched, so subprocess calls run in real OS
# threads and never block the event loop. Falls back to plain subprocess.run
# when eventlet is not active (e.g. DEBUG_MODE) or not installed.
try:
    import eventlet.patcher
    if eventlet.patcher.is_monkey_patched('os'):
        from eventlet.tpool import execute as _tpool
        def run(*args, **kwargs):
            return _tpool(subprocess.run, *args, **kwargs)
    else:
        run = subprocess.run
except ImportError:
    run = subprocess.run
