#!/bin/bash
cd "$(dirname "$0")" || exit 1
./run.sh "$@"
status=$?
if [ "$status" -ne 0 ] && [ -t 0 ]; then
  printf '\nPress Return to close this window… '
  read -r _
fi
exit "$status"
