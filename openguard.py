#!/usr/bin/env python3
"""Explicit package CLI; imports no product module until a command needs it."""
from deployment.launcher import main
if __name__ == '__main__':
    raise SystemExit(main())
