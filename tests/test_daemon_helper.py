"""Verify daemon_helper.sh exists at the expected path and can execute."""

import os
import pathlib
import subprocess

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DAEMON_HELPER = PROJECT_ROOT / 'scripts' / 'daemon_helper.sh'


def test_daemon_helper_exists_and_executable():
    """The script must exist and have the executable bit set."""
    assert DAEMON_HELPER.is_file(), f'{DAEMON_HELPER} not found'
    assert os.access(DAEMON_HELPER, os.X_OK), f'{DAEMON_HELPER} is not executable'


def test_daemon_helper_runs_trivial_command():
    """Running a trivial command through the helper should succeed (exit 0)."""
    result = subprocess.run(
        [str(DAEMON_HELPER), 'true'],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, f'stderr: {result.stderr}'
