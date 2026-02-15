"""
Dynamic syntax check for all Python files in the project.

Discovers every .py file (excluding .venv) and verifies it compiles
without SyntaxError or IndentationError.
"""

import py_compile
import pathlib
import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {'.venv', '__pycache__', '.git', 'node_modules'}


def _collect_python_files():
    """Walk the project tree and yield all .py files, skipping excluded dirs."""
    for path in PROJECT_ROOT.rglob('*.py'):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        yield path


def _python_file_ids():
    """Generate readable test IDs from file paths."""
    for path in _collect_python_files():
        yield pytest.param(path, id=str(path.relative_to(PROJECT_ROOT)))


@pytest.mark.parametrize("filepath", _python_file_ids())
def test_python_syntax(filepath):
    """Each .py file in the project must compile without syntax errors."""
    py_compile.compile(str(filepath), doraise=True)
