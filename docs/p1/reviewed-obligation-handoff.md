# P1 reviewed Obligation handoff (task-scoped)

Status: **pending human confirmation; no real apply has run**. This is an internal
Backend A operator path for one fixed sample, not a public approval API, a new
rule, or an assertion that the project is compliant. It does not alter an old
ScanRun, Assessment, or Report. NOTICE production input is independent.

The sample is OpenGuard's tracked source at
`f63a5818b3ef59997ca6d365b75b12099a475079`, exported as a ZIP and
actually scanned in a private data root. The terminal source scan is
`scn_f0bbdd55-3125-49cc-8753-304918ca3d3c` (`completed`); it has zero
Obligations. Its unique `pydantic==2.13.4` component is
`cmp_0c32e291-83e7-5bc9-b474-1e5921b668b2`, supported by manifest Evidence
`evd_99c84e41-a588-5c8e-ac02-104ad689f7c4`. The source ZIP SHA-256 is
`6927e8bac8e2c9e13b84aa988ef7f0125f3283ac4d3712cb9937219f6100ea04`;
the exact-version PyPI source distribution SHA-256 is
`c40756b57adaa8b1efeeced5c196f3f3b7c435f90e84ea7f443901bec8099ef6`.
The latter contains `PKG-INFO` for pydantic 2.13.4, an MIT project declaration,
and `pydantic-2.13.4/LICENSE` (SHA-256
`a9e186f3ca16b5eef84318e7a701721351a00cb7b8ae3a4394b67b49e3529ef3`).
The full license text and remaining scope questions are in the single pending
card at `output/manual-fixes/p1-reviewed-obligation-20260923T064250Z/pydantic-review-card.json`.

`prepare` validates the existing terminal scan, exact source ZIP, unique
resource/version and manifest Evidence, and exact official artifact. It uses a
non-creating, query-only registry read and writes only the pending card at an
operator-chosen private path. It does **not** assert a HUMAN/VERIFIED fact.
The fixed inputs are deliberately hard-bound in the internal tool; other
resources need a separately reviewed task, not an argument change.

The operator must inspect the full card and artifact, then independently write
a confirmation JSON. Required fields are `schema` =
`openguard.reviewed-obligation-confirmation/1`, the exact `card_sha256`,
`source_scan_id`, `resource_id`, `resource_version`, `artifact_sha256`,
`license_sha256`, and `scope` = `runtime_dependency`; also a real
`reviewer_self_reported` name, UTC `confirmed_at`, specific
`applicability_basis` and `scope_basis`, and explicit true statements for
`license_text_reviewed_in_full`, `license_applies_to_exact_artifact`,
`scope_confirmed`, and `limits_acknowledged`. None of those approvals are
pre-filled. A self-reported name is **not** external identity verification or
a digital signature. The review covers only this exact version, artifact,
LICENSE and declared runtime-dependency scope, not installed wheels,
transitive dependencies, fulfillment, or the project as a whole.

After the operator has created the confirmation file, the read-only
`hash-confirmation --confirmation <path>` CLI action prints its canonical
SHA-256. The operator must provide that digest explicitly to `apply` via
`--confirmation-sha256`, together with `--data-dir`, `--source-archive`,
`--artifact`, `--card`, `--confirmation`, and `--result`. Run the CLI as
`python -m app.p1.reviewed_obligation_cli` with `PYTHONPATH=backend`, in the
same isolated runtime used for scanning, while no API/scanner is active on the
private root. The card and confirmation files must be owner-owned regular
single-link files with no group/world permissions (mode `0600`) and no symlink
ancestor. No client-provided path is accepted by a public API.

`apply` revalidates every binding before reserving a new scan; it saves the
canonical confirmation and pending attempt immutably. It then reruns the
original ZIP pipeline against a private, fixed-Hash copy of the exact checked
source bytes, with only a NORMALIZE-stage adapter for the one reviewed
resource; unchanged B5 rules create any Obligation. The existing formal
Assessment, Remediation derive, and Report V2 services create their own durable
records. The CLI requires `--result` to name a new file in an existing private
owner-owned directory. It reserves that path with `state=pending` before calling
`apply`; an existing or unsafe result path stops before admission. It atomically
publishes `state=success` with the result, or `state=failure` with the error.
If publication fails after `apply` returns, the CLI reports
`apply_completed_result_unavailable` and forbids retrying the whole admission;
the pending file and durable records must be inspected. Any mismatch or replay
fails closed; an interrupted attempt remains for review and is never silently
retried. A successful result gives actual new IDs,
facts Hash, rule/version, Evidence references, Task version, snapshot ID and
JSON/HTML download hrefs and Hashes. Old facts and historical snapshots remain
untouched; Task status does not mark obligation fulfillment.

The permanent automated test uses a **test-only simulated confirmation**. Its
nonempty chain is not this sample's real handoff. Until the operator supplies
the specific record and a real `apply` succeeds, `new_scan_id`, nonempty formal
`obligation_id`, Task and Report IDs are intentionally absent.
