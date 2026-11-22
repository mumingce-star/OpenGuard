# Report V2 1.0 historical golden fixtures

These are two frozen TEST_ONLY archives named in the TASK45 P1.1 final gates.
`legacy-v1.zip` has SHA-256
`99636c699a0034f9050c4dcf9fc9248786d8bbda08bfaca6f144ddbdbdf63527`.
The zip is only a storage container. No part of the embedded HTML is executed.
Each subdirectory contains the frozen canonical preimage, the request body,
and byte-for-byte copies of the snapshot and two attachment BLOBs. No source
database, sessions, credentials, or other application state is included.

| Vector | Origin relative to the AIC project directory | Source SQLite SHA-256 |
| --- | --- | --- |
| `a` | `output/competition/demo-is-number-real-scan-20261115-01/TEST_ONLY/backend/report_v2.db` | `f1b813292f0b712bc8330c972c10868650b61d533e5f4390fe077ac279845c0a` |
| `b` | `output/competition/task38-unified-baseline-b58/tmp-data/pytest-baseline/test_task_report_replay_bytes_0/repository/output/manual-fixes/p1-dev-fixture/report_v2.db` | `1207dbf712dbe8986828e6850f166f445424559f0512f2008eaf7c1dce4a682e` |

Extraction was read-only with SQLite `mode=ro&immutable=1`. Neither source
database had WAL, SHM, or rollback journal sidecars. The source SHA-256s before
and after extraction were identical. The stored BLOBs matched their historical
digest columns and the preimages matched the historical request fingerprints.

Vector A comes from an `is-number@7.0.0` loopback archive. Its request bytes
were recovered with the original sender's serialization and verified against
`evidence/http-chain/API_EXCHANGES.json` in that run. Both attachment BLOBs
also matched its raw HTTP exports. Vector B comes from the historical TASK38
ASGI test for task-bound report replay and restart persistence. Its request
body is the frozen semantic reconstruction from that test and the stored
binding. Its original HTTP request bytes were unavailable.

The tests pin all byte lengths and SHA-256s independently of the current
writer. They load the stored rows into a fresh disposable tenant store.
Keep the fixtures and expected values fixed for future writer changes.
