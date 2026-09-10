#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${ALPHAGENIE_PYTHON:-python3.11}"
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3, 11), "Use Python 3.11"'
if [[ -L .venv ]]; then
  printf '%s\n' 'Refusing symlinked .venv; use a dedicated virtual environment in this checkout.' >&2
  exit 1
fi
if [[ -e .venv && ! -x .venv/bin/python ]]; then
  printf '%s\n' 'Existing .venv is not usable; move it aside yourself before retrying.' >&2
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  "$python_bin" -m venv .venv
fi
.venv/bin/python -E scripts/install_dependencies.py
printf '%s\n' 'Ready: source .venv/bin/activate' 'Then: python -m alphagenie serve'
