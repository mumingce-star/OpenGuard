# Report V2: fixed NoticeDraft inclusion

ReportV2Service accepts an optional `notice_reader=ReportNoticeReader(notice_store)`.
The adapter only invokes scoped `NoticeDraftStore.get(scan_id, assessment_id, draft_id)`;
it never initializes storage, generates drafts, or reads NOTICE facts. Production
factory/configuration is unchanged: the production Notice reader is not configured.

Each selected persisted draft becomes one `observation` section with the complete
NoticeDraft as content, its draft ID as the sole source ID, and its original schema
version. Its content hash and complete scan/assessment references must match the
report. Report Task/Graph references are independent and may coexist. Existing
resource/evidence references must resolve in the captured Scan Facts; empty refs,
missing values and coverage gaps are copied, not guessed or promoted to findings.

Validation distinguishes strict Graph and Notice objects. Missing, duplicate,
unreferenced or mismatched sections are rejected even if outer hashes are rebuilt.
The existing generation item/byte and store artifact/database budgets include the
Notice records and entries. Failure aborts report creation without partial records.

Empty notice_refs preserve the prior flow. A new nonempty request without a reader
returns the existing 409 not_ready reason notice_snapshot_reader_not_available.
Malformed/duplicate references are 400, scoped missing drafts 404, valid draft/hash
or binding mismatches 409, and corrupt saved content/storage failures 503. There is
no cross-scope lookup. Stable reference sorting feeds existing request identity and
fingerprint logic; a saved idempotent replay precedes all upstream reads.

JSON and HTML contain the fixed full draft. HTML visibly labels it
“NOTICE 草稿／待人工核验”, preserves missing/gaps and escapes all source text.
An excerpt is not complete original text; a draft is not proof that obligations
were fulfilled. No external content is loaded. The full document remains in the
escaped appendix. Generator/renderer versions are 1.2; public schema stays 1.0.
Historical reports are not migrated, regenerated or rewritten. GET/download and
replay read saved ReportV2Store bytes without consulting the Notice source.

Acceptance uses local fixture-backed real Notice/Report services, SQLite and
FastAPI TestClient. It is not live NOTICE scanning or production deployment.
