#!/bin/sh
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)" || exit 2
exec sh ./start.sh
