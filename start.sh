#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
if [ -x runtime/venv/bin/python ]; then
  exec runtime/venv/bin/python -B openguard.py start "$@"
fi
if command -v python3.12 >/dev/null 2>&1; then
  exec python3.12 -B openguard.py start "$@"
fi
printf '%s\n' '需要CPython3.12。先按README.md准备环境，再执行 python3.12 openguard.py setup。' >&2
exit 2
