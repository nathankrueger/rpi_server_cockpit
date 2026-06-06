"""
Raspberry Pi Dashboard - Main Entry Point

This is the top-level application file that:
1. Initializes Flask and SocketIO
2. Registers all blueprints
3. Starts background threads
4. Provides the WSGI application entry point
"""
import os
from datetime import timedelta

from flask import Flask, url_for
from flask_socketio import SocketIO

from app_state import DEBUG_MODE, set_socketio
from utils import init_server_config
from routes import register_blueprints
from socketio_handlers import register_socketio_handlers
from background import start_all_background_threads

# Monkey patch for eventlet (only in production)
# Must be done before importing anything that uses sockets
if not DEBUG_MODE:
    import eventlet
    eventlet.monkey_patch()

# Create Flask app
app = Flask(__name__)
# Generate a random secret key on startup for Flask session management
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())

# Cache static assets aggressively in the browser. Stale assets are avoided via the
# cache-busting ?v=<mtime> query appended by the versioned_static() Jinja helper below.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=30)


@app.context_processor
def inject_versioned_static():
    """Expose versioned_static() to templates.

    Appends a ?v=<file mtime> query to static URLs so browsers can cache assets for a
    long time but still re-fetch them when the file changes.
    """
    def versioned_static(filename):
        url = url_for('static', filename=filename)
        try:
            mtime = int(os.stat(os.path.join(app.static_folder, filename)).st_mtime)
            return f"{url}?v={mtime}"
        except OSError:
            return url
    return dict(versioned_static=versioned_static)

# Create SocketIO with appropriate async mode
async_mode = 'threading' if DEBUG_MODE else 'eventlet'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=async_mode)

# Store socketio instance in app_state for use by other modules
set_socketio(socketio)

# Initialize server config
init_server_config()

# Register all blueprints (routes)
register_blueprints(app)

# Register timeseries blueprint
from timeseries import timeseries_bp
app.register_blueprint(timeseries_bp)

# Register SocketIO event handlers
register_socketio_handlers(socketio)

# Start all background monitoring threads
start_all_background_threads()

# Start timeseries data collector
from timeseries import start_collector
start_collector()


def create_app():
    """WSGI application wrapper for gunicorn deployment."""
    return app


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
