"""A06 Report V2 immutable snapshot store tests."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import sqlite3

import pytest

from app.p1.report_v2_store import (
    ReportV2Store,
    ReportV2StoreError,
)


SCAN_ID = "scn_00000000-0000-0000-0000-000000000001"
ASSESSMENT_ID = "asm_report_store_test"

FACTS_HASH = "a" * 64
INPUT_HASH = "b" * 64
INVENTORY_HASH = "c" * 64
USAGE_HASH = "d" * 64
PARAMETERS_HASH = "e" * 64
ALGORITHM_HASH = "f" * 64
SECTION_HASH = "1" * 64

SNAPSHOT_ID = (
    "rptv2_123e4567-e89b-12d3-a456-426614174000"
)

SECOND_SNAPSHOT_ID = (
    "rptv2_123e4567-e89b-12d3-a456-426614174001"
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def report_content_hash(snapshot: dict) -> str:
    value = dict(snapshot)

    value.pop("content_hash", None)
    value.pop("artifacts", None)

    return digest(canonical_bytes(value))


def report_fixture(
    *,
    snapshot_id: str = SNAPSHOT_ID,
) -> tuple[dict, dict[str, bytes]]:
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from app.assessment.engine import build_assessment, facts_digest
    from test_p1_history_api import seed
    # Real models and full synthetic scan facts; the seed registry is a write sink.
    registry=SimpleNamespace(create=lambda *a,**kw:None,replace=lambda *a,**kw:None)
    run=seed(SimpleNamespace(registry=registry),1,'completed',revision='abc123')
    assessment=build_assessment(run,version=2,generated_at=datetime(2026,9,14,12,tzinfo=timezone.utc))
    assessment=assessment.model_copy(update={'id':ASSESSMENT_ID})
    scan_ref=dict(scan_id=SCAN_ID,revision=run.project.revision,facts_hash=facts_digest(run),
        input_hash=run.provenance.input_digest.value,
        inventory_hash=run.provenance.inventory_digest.value if run.provenance.inventory_digest else None,
        status=run.status.value,registry_revision=3)
    assessment_ref=dict(assessment_id=ASSESSMENT_ID,version=2,scan_id=SCAN_ID,facts_hash=assessment.facts_hash,
        usage_hash=assessment.usage_hash,rule_version=assessment.rule_version,formal=True)
    binding=dict(scan_ref=scan_ref,assessment_ref=assessment_ref,task_refs=[],notice_refs=[],algorithm_refs=[])
    created='2026-09-14T12:00:00Z'
    base=f'/api/v1/scans/{SCAN_ID}/assessments/{ASSESSMENT_ID}/report-v2/{snapshot_id}'
    contents=[('scan_facts',run.contract_version,[SCAN_ID],run.model_dump(mode='json')),
        ('formal_assessment',assessment.schema_version,[ASSESSMENT_ID],assessment.model_dump(mode='json')),
        ('workflow','1.0',[],{'task_refs':[],'tasks':[]}),
        ('ai_explanation',assessment.schema_version,[ASSESSMENT_ID],dict(assessment_id=ASSESSMENT_ID,
            assessment_version=2,ai_status=assessment.ai_status,ai_summary=assessment.ai_summary,
            ai_evidence_ids=assessment.ai_evidence_ids))]
    sections=[dict(authority=a,schema_version=v,source_ids=ids,content_hash=digest(canonical_bytes(content)),
        snapshot_ref=f'{base}?format=json#/sections/{i}/content',content=content)
        for i,(a,v,ids,content) in enumerate(contents)]
    document=dict(schema_version='1.0',snapshot_id=snapshot_id,binding=binding,created_at=created,
        generator_version='report-v2/1.1',sections=sections,provenance=dict(
            producer=dict(name='openguard-report-v2',version='1.1'),source_refs=[scan_ref],assessment_refs=[assessment_ref],
            generated_at=created,algorithm_version='report-v2/1.1',parameters_hash=digest(canonical_bytes({'schema_version':'1.0',**binding}))))
    artifact_payloads={'json':canonical_bytes(document),'html':b'<!doctype html><html><body>Synthetic full report</body></html>'}
    snapshot=deepcopy(document)
    snapshot['sections']=[{k:v for k,v in row.items() if k!='content'} for row in sections]
    snapshot['artifacts']=[dict(format=fmt,content_hash=digest(raw),size_bytes=len(raw),href=base+'?format='+fmt)
        for fmt,raw in artifact_payloads.items()]
    snapshot['content_hash']=report_content_hash(snapshot)
    return snapshot,artifact_payloads


@pytest.fixture
def store(tmp_path) -> ReportV2Store:
    value = ReportV2Store(
        tmp_path
        / "report"
        / "report_v2.db",
        min_free_bytes=0,
    )

    value.initialize()

    return value


def assert_store_error(
    error: pytest.ExceptionInfo,
    code: str,
) -> None:
    assert error.value.code == code


def test_readonly_missing_store_creates_nothing(
    tmp_path,
) -> None:
    path = (
        tmp_path
        / "missing"
        / "report_v2.db"
    )

    store = ReportV2Store(
        path,
        min_free_bytes=0,
    )

    assert (
        store.get(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )
        is None
    )

    assert (
        store.get_artifact(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
            "json",
        )
        is None
    )

    assert (
        store.request_fingerprint(
            SCAN_ID,
            ASSESSMENT_ID,
            "missing-request",
        )
        is None
    )

    assert not path.exists()
    assert not path.parent.exists()


def test_create_round_trip_snapshot_and_artifacts(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    created = store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "create-request",
        "fingerprint-v1",
        snapshot,
        artifacts,
    )

    assert created == snapshot

    assert (
        store.get(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )
        == snapshot
    )

    assert (
        store.get_artifact(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
            "json",
        )
        == artifacts["json"]
    )

    assert (
        store.get_artifact(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
            "html",
        )
        == artifacts["html"]
    )

    assert (
        store.request_fingerprint(
            SCAN_ID,
            ASSESSMENT_ID,
            "create-request",
        )
        == "fingerprint-v1"
    )


def test_same_idempotency_key_same_input_returns_original(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    first = store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "same-request",
        "same-fingerprint",
        snapshot,
        artifacts,
    )

    second = store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "same-request",
        "same-fingerprint",
        snapshot,
        artifacts,
    )

    assert first == snapshot
    assert second == first

    with sqlite3.connect(store.path) as db:
        snapshot_count = db.execute(
            """
            SELECT COUNT(*)
            FROM report_snapshots
            """
        ).fetchone()[0]

        request_count = db.execute(
            """
            SELECT COUNT(*)
            FROM report_requests
            """
        ).fetchone()[0]

        artifact_count = db.execute(
            """
            SELECT COUNT(*)
            FROM report_artifacts
            """
        ).fetchone()[0]

    assert snapshot_count == 1
    assert request_count == 1
    assert artifact_count == 2


def test_same_idempotency_key_different_input_conflicts(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "conflict-request",
        "fingerprint-one",
        snapshot,
        artifacts,
    )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "conflict-request",
            "fingerprint-two",
            snapshot,
            artifacts,
        )

    assert_store_error(
        error,
        "idempotency_conflict",
    )

    assert (
        store.request_fingerprint(
            SCAN_ID,
            ASSESSMENT_ID,
            "conflict-request",
        )
        == "fingerprint-one"
    )


def test_new_request_cannot_overwrite_existing_snapshot_id(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "first-request",
        "fingerprint-one",
        snapshot,
        artifacts,
    )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "second-request",
            "fingerprint-two",
            snapshot,
            artifacts,
        )

    assert_store_error(
        error,
        "conflict",
    )

    assert (
        store.request_fingerprint(
            SCAN_ID,
            ASSESSMENT_ID,
            "second-request",
        )
        is None
    )

    assert (
        store.get(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )
        == snapshot
    )


def test_snapshot_and_artifacts_are_scope_bound(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "scope-request",
        "scope-fingerprint",
        snapshot,
        artifacts,
    )

    assert (
        store.get(
            SCAN_ID,
            "asm_other",
            SNAPSHOT_ID,
        )
        is None
    )

    assert (
        store.get(
            "scn_other",
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )
        is None
    )

    assert (
        store.get_artifact(
            SCAN_ID,
            "asm_other",
            SNAPSHOT_ID,
            "json",
        )
        is None
    )

    assert (
        store.get_artifact(
            "scn_other",
            ASSESSMENT_ID,
            SNAPSHOT_ID,
            "html",
        )
        is None
    )


def test_invalid_report_content_hash_is_atomic(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    snapshot["content_hash"] = "9" * 64

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "bad-hash-request",
            "bad-hash-fingerprint",
            snapshot,
            artifacts,
        )

    assert_store_error(
        error,
        "invalid_argument",
    )

    assert (
        store.get(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )
        is None
    )

    assert (
        store.request_fingerprint(
            SCAN_ID,
            ASSESSMENT_ID,
            "bad-hash-request",
        )
        is None
    )


def test_artifact_hash_mismatch_is_atomic(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    bad_artifacts = dict(artifacts)
    bad_artifacts["json"] = (
        b'{"tampered":true}'
    )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "artifact-hash-request",
            "artifact-hash-fingerprint",
            snapshot,
            bad_artifacts,
        )

    assert_store_error(
        error,
        "invalid_argument",
    )

    assert (
        store.get(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )
        is None
    )


def test_zero_byte_runtime_artifact_rejected(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    artifacts = dict(artifacts)
    artifacts["html"] = b""

    snapshot = deepcopy(snapshot)

    for artifact in snapshot["artifacts"]:
        if artifact["format"] == "html":
            artifact["content_hash"] = digest(
                b""
            )
            artifact["size_bytes"] = 0

    # Report content hash excludes artifacts,
    # so changing artifact metadata does not alter it.
    assert (
        snapshot["content_hash"]
        == report_content_hash(snapshot)
    )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "empty-artifact-request",
            "empty-artifact-fingerprint",
            snapshot,
            artifacts,
        )

    assert_store_error(
        error,
        "invalid_argument",
    )


def test_missing_runtime_artifact_rejected(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    artifacts = {
        "json": artifacts["json"],
    }

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "missing-artifact-request",
            "missing-artifact-fingerprint",
            snapshot,
            artifacts,
        )

    assert_store_error(
        error,
        "invalid_argument",
    )


def test_invalid_snapshot_identifier_rejected(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    snapshot["snapshot_id"] = (
        "rptv2_not-a-uuid"
    )

    snapshot["content_hash"] = (
        report_content_hash(snapshot)
    )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.create(
            SCAN_ID,
            ASSESSMENT_ID,
            "bad-id-request",
            "bad-id-fingerprint",
            snapshot,
            artifacts,
        )

    assert_store_error(
        error,
        "invalid_argument",
    )


def test_corrupted_snapshot_storage_is_rejected(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "corrupt-snapshot-request",
        "corrupt-snapshot-fingerprint",
        snapshot,
        artifacts,
    )

    with sqlite3.connect(store.path) as db:
        db.execute(
            """
            UPDATE report_snapshots
            SET payload_hash=?
            WHERE snapshot_id=?
            """,
            (
                "0" * 64,
                SNAPSHOT_ID,
            ),
        )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.get(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
        )

    assert_store_error(
        error,
        "storage_unavailable",
    )


def test_corrupted_artifact_storage_is_rejected(
    store,
) -> None:
    snapshot, artifacts = report_fixture()

    store.create(
        SCAN_ID,
        ASSESSMENT_ID,
        "corrupt-artifact-request",
        "corrupt-artifact-fingerprint",
        snapshot,
        artifacts,
    )

    with sqlite3.connect(store.path) as db:
        db.execute(
            """
            UPDATE report_artifacts
            SET payload_hash=?
            WHERE snapshot_id=?
              AND format='json'
            """,
            (
                "0" * 64,
                SNAPSHOT_ID,
            ),
        )

    with pytest.raises(
        ReportV2StoreError
    ) as error:
        store.get_artifact(
            SCAN_ID,
            ASSESSMENT_ID,
            SNAPSHOT_ID,
            "json",
        )

    assert_store_error(
        error,
        "storage_unavailable",
    )

@pytest.mark.parametrize('fault', ['placeholder','snapshot','binding','version','section_missing','section_metadata',
    'other_pointer','latest_pointer','missing_pointer','section_hash','duplicate_key','nan','overflow','invalid_json'])
def test_complete_json_mismatch_rejected_atomically(store,fault):
    snapshot,artifacts=report_fixture()
    doc=json.loads(artifacts['json'])
    if fault=='placeholder':doc={'kind':'openguard-report-v2','format':'json'}
    elif fault=='snapshot':doc['snapshot_id']=SECOND_SNAPSHOT_ID
    elif fault=='binding':doc['binding']['assessment_ref']['assessment_id']='asm_other'
    elif fault=='version':doc['generator_version']='other'
    elif fault=='section_missing':del doc['sections'][0]['content']
    elif fault=='section_metadata':doc['sections'][0]['authority']='formal_assessment'
    elif fault in {'other_pointer','latest_pointer','missing_pointer'}:
        suffix={'other_pointer':SECOND_SNAPSHOT_ID,'latest_pointer':'latest','missing_pointer':SNAPSHOT_ID}[fault]
        ref=f'/api/v1/scans/{SCAN_ID}/assessments/{ASSESSMENT_ID}/report-v2/{suffix}?format=json#/sections/99/content'
        doc['sections'][0]['snapshot_ref']=snapshot['sections'][0]['snapshot_ref']=ref
    elif fault=='section_hash':doc['sections'][0]['content']['details']=[]
    raw=canonical_bytes(doc)
    if fault=='duplicate_key':raw=b'{"snapshot_id":"first",'+raw[1:]
    elif fault=='nan':raw=raw.replace(b'"version":2',b'"version":NaN',1)
    elif fault=='overflow':raw=raw.replace(b'"version":2',b'"version":1e999',1)
    elif fault=='invalid_json':raw=b'{'
    artifacts['json']=raw
    for item in snapshot['artifacts']:
        if item['format']=='json':item.update(content_hash=digest(raw),size_bytes=len(raw))
    snapshot['content_hash']=report_content_hash(snapshot)
    before=store.path.read_bytes()
    with pytest.raises(ReportV2StoreError) as error:
        store.create(SCAN_ID,ASSESSMENT_ID,'bad-json','fp',snapshot,artifacts)
    assert error.value.code=='invalid_argument'
    assert store.path.read_bytes()==before
    with sqlite3.connect(store.path) as db:
        assert [db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('report_snapshots','report_artifacts','report_requests')]==[0,0,0]


def test_summary_only_content_rejected_even_with_matching_section_hash(store):
    snapshot,artifacts=report_fixture()
    doc=json.loads(artifacts['json'])
    doc['sections'][1]['content']={'id':ASSESSMENT_ID,'summary':'Only a summary'}
    sha=digest(canonical_bytes(doc['sections'][1]['content']))
    doc['sections'][1]['content_hash']=snapshot['sections'][1]['content_hash']=sha
    artifacts['json']=canonical_bytes(doc)
    for item in snapshot['artifacts']:
        if item['format']=='json':item.update(content_hash=digest(artifacts['json']),size_bytes=len(artifacts['json']))
    snapshot['content_hash']=report_content_hash(snapshot)
    before=store.path.read_bytes()
    with pytest.raises(ReportV2StoreError) as error:
        store.create(SCAN_ID,ASSESSMENT_ID,'summary','fp',snapshot,artifacts)
    assert error.value.code=='invalid_argument'
    assert store.path.read_bytes()==before
