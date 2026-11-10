#!/usr/bin/env bash
set -euo pipefail

# Run from the script's own directory so .env and relative paths resolve.
cd "$(dirname "$0")"

# Print accented names/paths correctly.
export PYTHONUTF8=1

# Prefer the local virtual environment when it exists.
# No geckodriver PATH tweak is needed: Selenium 4 manages the driver itself.
if [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

exec "$PYTHON" igrp-script.py "$@"
