# P1 isolated integration fixture

`backend/app/dev_integration.py` seeds its synthetic P1 instances from the
public repository fixture `examples/sample-scan-result.json`.  It changes only
stable synthetic identities, revision and a component version to create two
comparable completed snapshots, then creates one partial snapshot with an
explicit coverage gap.

This directory documents that fixture boundary for tests.  Runtime seed code
does not import pytest or test helpers, and it never reads an ignored output
directory, a production database, or a real repository scan.
