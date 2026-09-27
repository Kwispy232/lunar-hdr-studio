#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -c 'import sys; assert sys.version_info >= (3, 11), "Install Python 3.11 or newer from python.org"'
  python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet -r requirements.txt
exec .venv/bin/python main.py
