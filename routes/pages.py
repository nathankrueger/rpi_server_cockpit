"""Page routes for serving HTML templates."""
from flask import Blueprint, render_template

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


@pages_bp.route('/monitor')
def monitor():
    """Serve the system monitor page."""
    return render_template('monitor.html')
