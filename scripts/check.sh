#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python_bin="${ALPHAGENIE_PYTHON:-.venv/bin/python}"
"$python_bin" -m unittest discover -s tests -v
"$python_bin" scripts/release_check.py
if command -v node >/dev/null 2>&1; then
  node --test tests/*.mjs
else
  printf '%s\n' 'Node tests not run: install Node 22+ and run npm test (no npm install needed).'
  exit 1
fi
