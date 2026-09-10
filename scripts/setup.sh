#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${ALPHAGENIE_PYTHON:-python3.11}"
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Use Python 3.11"'
if [[ ! -x .venv/bin/python ]]; then
  "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
printf '%s\n' 'Ready: source .venv/bin/activate' 'Then: python -m alphagenie serve'
