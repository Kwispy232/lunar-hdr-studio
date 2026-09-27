#!/bin/sh
# Works from any working directory, including a checkout path containing spaces.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for python in .venv/bin/python python3.11 python3.12 python3.13 python3.14 python3 python; do
  if "$python" -c 'import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] < (3, 15)))' 2>/dev/null; then
    exec "$python" launcher.py "$@"
  fi
done
printf '%s\n' 'Lunar HDR needs Python 3.11–3.14. Install it from https://www.python.org/downloads/ and try again.' >&2
exit 1
