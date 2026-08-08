"""Claude Code usage-limit endpoint."""
from flask import Blueprint, jsonify, request

from config_loader import get_claude_usage_config
from utils import get_claude_usage

claude_bp = Blueprint('claude', __name__)


@claude_bp.route('/api/claude/usage', methods=['GET'])
def claude_usage():
    """Get Claude usage limits (session / weekly windows).

    Returns {'enabled': False} when the meter is not configured, so the monitor page
    can leave the tile hidden. Never returns credentials - only percentages, reset
    timestamps, and an error code when the lookup fails.

    Query params:
        force: '1' to bypass the server-side cache
    """
    force = request.args.get('force') == '1'
    return jsonify(get_claude_usage(get_claude_usage_config(), force=force))
