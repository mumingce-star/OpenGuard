#!/usr/bin/env python3
"""Explicit package CLI; imports no product module until a command needs it."""
import sys

if __name__ == '__main__' and sys.argv[1:2] == ['scan']:
    sys.dont_write_bytecode = True

from deployment.launcher import main

if __name__ == '__main__':
    raise SystemExit(main())
