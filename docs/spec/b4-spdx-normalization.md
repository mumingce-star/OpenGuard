# B4 SPDX normalization

`app.licenses.normalize_license(text, evidence)` is an offline, deterministic bridge from explicit scanner aliases to a P0 `LicenseExpression`.

- Only the repository-owned alias table is recognized; every compound term must match.
- It requires source `Evidence`; unknown text remains `pending` with no normalized ID.
- A verified result requires all supplied evidence to be `verified`.
- It does not identify a license from prose, retrieve SPDX data, or make a legal conclusion.

The current supported set is deliberately the B5 rule coverage. Future SPDX-list ingestion needs a versioned data ledger and an ADR before expanding this table.
