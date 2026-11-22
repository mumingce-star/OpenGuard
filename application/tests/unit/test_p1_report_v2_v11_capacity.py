"""Exact limits and transactional rollback on private TEST_ONLY stores."""

from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import html
import json
import sqlite3

import pytest

from app.assessment.engine import build_assessment
from app.assessment.store import AssessmentStore
from app.domain.usage import UsageDeclaration
from app.persistence import SQLiteScanRunRegistry
from app.p1 import report_v2
from app.p1.remediation_store import RemediationTaskStore
from app.p1.report_v2_integrity import binding_identity
from app.p1.report_v2_store import ReportV2Store, ReportV2StoreError
from test_task45_dependency_evidence_contract import _Harness, _NOW, _component, _evidence, _identifier


MIB = 1024 * 1024
OBSERVATION_SCHEMA = "openguard-report-v2-dependency-evidence/1"
TABLES = ("report_snapshots", "report_artifacts", "report_requests")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _table_counts(db):
    return tuple(db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in TABLES)


def _counts(store):
    with closing(sqlite3.connect(store.path.as_uri() + "?mode=ro", uri=True)) as db:
        return _table_counts(db)


@pytest.fixture
def capacity_environment(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(report_v2, "_utc_now", lambda: "2026-01-02T00:00:00Z")
    assessment_store = AssessmentStore(tmp_path / "assessment.db", min_free_bytes=0)
    remediation = RemediationTaskStore(tmp_path / "remediation.db", min_free_bytes=0)
    remediation.initialize()
    # Confirms hard 1.1 upper bounds even if a trusted builder sets higher local values.
    store = ReportV2Store(tmp_path / "report_v2.db", max_snapshot_bytes=32 * MIB,
                          max_artifact_bytes=64 * MIB, min_free_bytes=0)
    store.initialize()
    scan_db = tmp_path / "scans.db"
    with closing(SQLiteScanRunRegistry(scan_db)) as registry:
        seed = _Harness(client=None, registry=registry, database=scan_db)
        service = report_v2.ReportV2Service(
            registry, assessment_store, remediation, store, enable_v11_writes=True,
            max_included_items=21_000, max_document_bytes=32 * MIB,
        )

        def sources(number, excerpts=()):
            # Include one linked and hash-bound dependency. Additional evidence
            # is deliberately unbound, preserving count and byte isolation.
            manifest = _evidence(1, "manifest")
            padding_source = _evidence(2, "sbom")
            padding = [padding_source.model_copy(update={
                "id": _identifier("evd", index), "excerpt": excerpt,
            }) for index, excerpt in enumerate(excerpts, 2)]
            run = seed.save(
                number, components=[_component(1, manifest)], evidence=[manifest, *padding],
            ).run
            assessment = build_assessment(
                run, UsageDeclaration(declared_at=_NOW), generated_at=_NOW,
            )
            formal = assessment_store.create(assessment, idempotency_key=f"fixed-{number}")
            assert formal.formal and formal.scan_id == run.id
            return run, formal

        yield service, store, sources


def _create(service, record, key):
    run, assessment = record
    return service.create(run.id, assessment.id, schema_version="1.1", idempotency_key=key)


def _assert_capacity_error(error, reason):
    assert error.value.code == "upstream_unavailable"
    assert error.value.reason == reason


def _structural_size(record):
    run, assessment = record
    assert len(run.components) == 1 and len(run.components[0].evidence_ids) == 1
    assert not any((run.ai_assets, run.findings, run.licenses, run.obligations,
                    run.remediations, run.errors, run.report_links, assessment.obligations))
    # One component, evidence records, Assessment rows, and one dependency row
    # with one ref. With no explicit source refs, graphs or NOTICE, no other rows apply.
    return (
        1 + len(run.evidence) + len(assessment.dimensions)
        + len(assessment.resource_evaluations) + len(assessment.coverage_issues) + 2
    )


@pytest.mark.parametrize("limit", [19_999, 20_000, 20_001])
def test_real_bound_records_meet_exact_structural_archive_boundary(capacity_environment, limit):
    service, store, sources = capacity_environment
    baseline_size = _structural_size(sources(1))
    record = sources(2, [None] * (limit - baseline_size))
    assert _structural_size(record) == limit
    if limit <= 20_000:
        snapshot = _create(service, record, "structural-boundary")
        assert snapshot.schema_version == "1.1"
        artifact = service.artifact(record[0].id, record[1].id, snapshot.snapshot_id, "json")
        (observation,) = [
            row["content"] for row in json.loads(artifact)["sections"]
            if row["schema_version"] == OBSERVATION_SCHEMA
        ]
        assert observation["returned"] == observation["total"] == 1 and not observation["incomplete"]
        assert len(observation["items"][0]["evidence"]) == 1 and not observation["items"][0]["gaps"]
        assert _counts(store) == (1, 2, 1)
    else:
        with pytest.raises(report_v2.ReportV2ServiceError) as error:
            _create(service, record, "structural-boundary")
        _assert_capacity_error(error, "report_generation_capacity_exceeded")
        assert _counts(store) == (0, 0, 0)
    print(f"P1_1_STRUCTURAL_BOUNDARY counted_items={limit} expected_write={limit <= 20_000}")


def _unicode_excerpts(extra_bytes, rows):
    # Start with the same one-byte placeholder as the probe. The extra bytes
    # are split over valid 1,000-character evidence excerpts.
    for _ in range(rows):
        additional = min(extra_bytes, 2997)
        repeats, remainder = divmod(additional, 3)
        yield "x" + "界" * repeats + "x" * remainder
        extra_bytes -= additional
    assert extra_bytes == 0


def test_canonical_json_exact_16_mib_and_one_byte_over(capacity_environment):
    service, store, sources = capacity_environment
    rows = 6500
    probe = _create(service, sources(1, ["x"] * rows), "probe")
    probe_size = next(meta.size_bytes for meta in probe.artifacts if meta.format == "json")
    extra = 16 * MIB - probe_size
    assert 0 < extra < rows * 2997
    exact = _create(service, sources(2, _unicode_excerpts(extra, rows)), "exact-document")
    assert next(meta.size_bytes for meta in exact.artifacts if meta.format == "json") == 16 * MIB
    assert next(meta.size_bytes for meta in exact.artifacts if meta.format == "html") < 32 * MIB
    rejected = sources(3, _unicode_excerpts(extra + 1, rows))
    with pytest.raises(report_v2.ReportV2ServiceError) as error:
        _create(service, rejected, "over-document")
    _assert_capacity_error(error, "report_generation_capacity_exceeded")
    assert store.request_fingerprint(rejected[0].id, rejected[1].id, "over-document") is None
    assert _counts(store) == (2, 4, 2)
    print("P1_1_CANONICAL_JSON exact=16777216 over=16777217 utf8=true")


def test_html_escape_growth_exceeds_32_mib_with_canonical_json_under_16_mib(
    capacity_environment, monkeypatch,
):
    service, store, sources = capacity_environment
    rows = 8000
    excerpt = "&" * 900
    # No truncation is allowed in the complete text appendix. Just these
    # escaped excerpts alone cross the attachment limit before markup.
    escaped_lower_bound = rows * len(html.escape(excerpt).encode("utf-8"))
    assert escaped_lower_bound > 32 * MIB
    actual_json_sizes = []
    render_json = report_v2._render_json

    def measure_json(document):
        raw = render_json(document)
        actual_json_sizes.append(len(raw))
        return raw

    monkeypatch.setattr(report_v2, "_render_json", measure_json)
    with pytest.raises(report_v2.ReportV2ServiceError) as error:
        _create(service, sources(1, [excerpt] * rows), "html-escape-boundary")
    _assert_capacity_error(error, "storage_capacity_exceeded")
    assert len(actual_json_sizes) == 1 and actual_json_sizes[0] < 16 * MIB
    assert _counts(store) == (0, 0, 0)
    print(f"P1_1_HTML_ESCAPE canonical_json={actual_json_sizes[0]} "
          f"escaped_html_lower_bound={escaped_lower_bound} html_limit={32 * MIB}")


def _valid_bundle(service, sources):
    run, assessment = sources(1)
    snapshot = _create(service, (run, assessment), "valid-bundle")
    return snapshot.model_dump(mode="json"), {
        fmt: service.artifact(run.id, assessment.id, snapshot.snapshot_id, fmt)
        for fmt in ("html", "json")
    }


def _new_store(path):
    store = ReportV2Store(path / "report_v2.db", max_snapshot_bytes=32 * MIB,
                          max_artifact_bytes=64 * MIB, min_free_bytes=0)
    store.initialize()
    return store


def _store_create(store, snapshot, artifacts, *, key):
    binding = snapshot["binding"]
    return store.create(
        binding["scan_ref"]["scan_id"], binding["assessment_ref"]["assessment_id"],
        key, snapshot["provenance"]["parameters_hash"], snapshot, artifacts,
        request_identity=binding_identity(binding, schema_version="1.1"),
    )


def test_snapshot_16_mib_envelope_limit_is_independent_of_attachment_byte_limits(
    capacity_environment, tmp_path,
):
    service, _, sources = capacity_environment
    snapshot, artifacts = _valid_bundle(service, sources)
    target = _new_store(tmp_path / "snapshot-boundary")
    scan = snapshot["binding"]["scan_ref"]["scan_id"]
    assessment = snapshot["binding"]["assessment_ref"]["assessment_id"]
    # Use envelope-only metadata. The exact boundary tests serialization and
    # size, not the later artifact URL/content consistency check.
    padded = deepcopy(snapshot)
    padding = 16 * MIB - len(_canonical(padded))
    padded["artifacts"][0]["href"] += "x" * padding
    assert len(target._snapshot_payload(padded, scan, assessment)) == 16 * MIB
    padded["artifacts"][0]["href"] += "x"
    assert len(_canonical(padded)) == 16 * MIB + 1
    assert max(map(len, artifacts.values())) < 16 * MIB
    with pytest.raises(ReportV2StoreError) as error:
        _store_create(target, padded, artifacts, key="over-envelope")
    assert error.value.code == "storage_capacity_exceeded"
    assert _counts(target) == (0, 0, 0)
    print("P1_1_SNAPSHOT_ENVELOPE exact=16777216 over=16777217 isolated_store=true")


def test_json_attachment_over_32_mib_rejected_at_store_before_content_validation(
    capacity_environment, tmp_path, monkeypatch,
):
    service, _, sources = capacity_environment
    snapshot, artifacts = _valid_bundle(service, sources)
    target = _new_store(tmp_path / "json-attachment-boundary")
    # The 16 MiB canonical writer ceiling prevents normal creation of a JSON
    # attachment this size. Lift only the document ceiling in this isolated
    # store check so rejection must come from the independent attachment cap.
    monkeypatch.setattr("app.p1.report_v2_store.MAX_REPORT_DOCUMENT_BYTES", 64 * MIB)
    artifacts["json"] += b" " * (32 * MIB + 1 - len(artifacts["json"]))
    assert len(artifacts["json"]) == 32 * MIB + 1
    meta = next(row for row in snapshot["artifacts"] if row["format"] == "json")
    meta["size_bytes"] = len(artifacts["json"])
    meta["content_hash"] = sha256(artifacts["json"]).hexdigest()

    def forbidden(*args, **kwargs):
        pytest.fail("Oversized JSON assembly must fail before parsing content")

    monkeypatch.setattr("app.p1.report_v2_store.validate_document", forbidden)
    with pytest.raises(ReportV2StoreError) as error:
        _store_create(target, snapshot, artifacts, key="over-json-attachment")
    assert error.value.code == "storage_capacity_exceeded"
    assert _counts(target) == (0, 0, 0)
    print("P1_1_JSON_ATTACHMENT over=33554433 canonical_writer_reachable=false isolated_store=true")


def test_injected_failure_after_snapshot_and_artifact_inserts_rolls_back_and_same_key_retries(
    capacity_environment, monkeypatch,
):
    service, store, sources = capacity_environment
    record = sources(1)
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute("CREATE TRIGGER fail_request BEFORE INSERT ON report_requests "
                   "BEGIN SELECT observe_then_fail(); END")

    original_connect = store._connect
    observed = []

    def injected(*, readonly=False):
        db = original_connect(readonly=readonly)
        if not readonly:
            def observe_then_fail():
                observed.append(_table_counts(db))
                raise sqlite3.OperationalError("TEST_ONLY injected request-row failure")
            db.create_function("observe_then_fail", 0, observe_then_fail)
        return db

    with monkeypatch.context() as context:
        context.setattr(store, "_connect", injected)
        with pytest.raises(report_v2.ReportV2ServiceError) as error:
            _create(service, record, "retryable-key")
        _assert_capacity_error(error, "storage_unavailable")

    assert observed == [(1, 2, 0)], "The test must reach the final request-row insertion"
    assert _counts(store) == (0, 0, 0)
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute("DROP TRIGGER fail_request")
    retried = _create(service, record, "retryable-key")
    assert retried.schema_version == "1.1" and _counts(store) == (1, 2, 1)
    assert _create(service, record, "retryable-key") == retried
    assert _counts(store) == (1, 2, 1)
    print("P1_1_SQLITE_ROLLBACK inserted_before_failure=1,2,0 after_failure=0,0,0 retry=1,2,1")
