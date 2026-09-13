# P1 Contract V1 Schemas

Authoritative contract: [p1-workspace-contract.md](../../docs/spec/p1-workspace-contract.md).

Seven independent object schemas use JSON Schema Draft 2020-12, `schema_version: "1.0"`, and `urn:openguard:p1:<file-stem>:1.0` identifiers. `common.schema.json` contains shared closed value objects, not an eighth business object. Every object rejects unknown properties. Resolve URN references from these local files; never fetch schemas from the network.

Examples: [object-examples.json](../../docs/p1/object-examples.json). Synthetic examples conform to the contract but do not prove actual scan facts, authorization, working API endpoints, or available artifacts.

Validation: `PYTHONPATH=backend python -m pytest -q -p no:cacheprovider tests/unit/test_p1_contract_schema.py` using the project's existing development dependencies (`jsonschema`, `pytest`). No production dependency is added.

JSON Schema checks shape, versions, enums and local conditions such as task notes. The Markdown additionally requires reference existence, immutable snapshot resolution, hash/count consistency, correct fact-based edge derivation, and CAS updates. These need implementation-level verification in later tasks. Passing these schema tests is not P1 product acceptance.

Graph V1 is complete within its explicit filter and rejects pagination fields. Capacity excess is an API error, never a truncated success. Metadata observations reject raw payloads and state that full response replay is unavailable. Task notes never become Evidence. No P0 schema or runtime imports these files.
