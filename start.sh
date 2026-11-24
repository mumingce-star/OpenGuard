#!/bin/sh
set -eu
case $0 in
  /*) launcher=$0 ;;
  *) launcher=./$0 ;;
esac
CDPATH= cd -P "$(dirname "$launcher")"

is_python312() {
  "$1" -c 'import sys; raise SystemExit(sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12))' >/dev/null 2>&1
}

if [ -x runtime/venv/bin/python ]; then
  exec runtime/venv/bin/python -B openguard.py start "$@"
fi
if [ "${OPENGUARD_PYTHON+x}" = x ]; then
  case $OPENGUARD_PYTHON in
    /*)
      if [ -f "$OPENGUARD_PYTHON" ] && [ -x "$OPENGUARD_PYTHON" ] && is_python312 "$OPENGUARD_PYTHON"; then
        exec "$OPENGUARD_PYTHON" -B openguard.py start "$@"
      fi
      ;;
  esac
  printf '%s\n' 'OPENGUARD_PYTHON 必须指向可执行的 CPython 3.12 绝对路径。' >&2
  exit 2
fi
if command -v python3.12 >/dev/null 2>&1 && is_python312 python3.12; then
  exec python3.12 -B openguard.py start "$@"
fi
if command -v python3 >/dev/null 2>&1 && is_python312 python3; then
  exec python3 -B openguard.py start "$@"
fi
printf '%s\n' '需要CPython3.12。先按README.md准备环境，再执行 python3.12 openguard.py setup。' >&2
exit 2
