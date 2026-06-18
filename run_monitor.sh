#!/bin/bash
# Wrapper script for launching background_monitor.py
# Used by LaunchAgent — sets PYTHONPATH to venv site-packages

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Use system Python with venv packages via PYTHONPATH
PYTHON="/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python"
SITE_PACKAGES="$SCRIPT_DIR/venv/lib/python3.9/site-packages"

export PYTHONPATH="$SITE_PACKAGES"
export PYTHONDONTWRITEBYTECODE=1

exec "$PYTHON" "$SCRIPT_DIR/background_monitor.py"
