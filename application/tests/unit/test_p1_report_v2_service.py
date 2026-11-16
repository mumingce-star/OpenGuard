"""A06 Report V2 immutable service tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.assessment.store import AssessmentStore
from app.persistence import SQLiteScanRunRegistry
from app.p1.models import (
    P1AlgorithmRef,
    P1NoticeRef,
    P1TaskDeriveRequest,
    P1TaskRef,
)
from app.p1.remediation import RemediationService
from app.p1.remediation_store import RemediationTaskStore
from app.p1.report_v2 import (
    ReportV2Service,
    ReportV2ServiceError,
)
from app.p1.report_v2_store import ReportV2Store

from test_p1_contract_schema import validator
from test_p1_diff_api import assessment as make_assessment
from test_p1_history_api import seed


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: object) -> str:
    if isinstance(value, bytes):
        payload = value
    else:
        payload = canonical_bytes(value)

    return hashlib.sha256(payload).hexdigest()


def db_hash(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def pointer(document: object, path: str) -> object:
    value = document

    for token in path[1:].split("/"):
        token = (
            token
            .replace("~1", "/")
            .replace("~0", "~")
        )

        if isinstance(value, list):
            value = value[int(token)]
        else:
            value = value[token]

    return value


def service_error(
    error: pytest.ExceptionInfo,
    code: str,
    reason: str,
) -> None:
    assert error.value.code == code
    assert error.value.reason == reason


@pytest.fixture
def report_env(
    tmp_path,
    monkeypatch,
):
    tmp_path.chmod(0o700)

    env = SimpleNamespace(
        path=tmp_path,
    )

    env.registry = SQLiteScanRunRegistry(
        tmp_path / "scans.db"
    )

    env.assessment_store = AssessmentStore(
        tmp_path / "assessment.db",
        min_free_bytes=0,
    )
    env.assessment_store.initialize()

    # test_p1_diff_api.assessment() expects env.store.
    env.store = env.assessment_store

    env.run = seed(
        env,
        1,
        "completed",
        revision="report-v2-fixture",
    )

    def assessment_sources(data: dict) -> None:
        row = data["resource_evaluations"][0]

        row["conditions"] = [
            "保留许可证声明"
        ]
        row["gaps"] = [
            "补充固定版本的许可证据"
        ]
        row["next_steps"] = [
            "核对该固定版本来源"
        ]

        # Existing AI explanation is historical input only.
        # Report V2 must copy it rather than generate another one.
        data["ai_status"] = "fallback"
        data["ai_summary"] = (
            "已有评估中的 AI 说明；"
            "Report V2 不重新生成。"
        )

    env.assessment = make_assessment(
        env,
        env.run,
        mutate=assessment_sources,
    )

    env.task_store = RemediationTaskStore(
        tmp_path
        / "tasks"
        / "remediation.db",
        min_free_bytes=0,
    )
    env.task_store.initialize()

    env.task_service = RemediationService(
        env.registry,
        env.assessment_store,
        env.task_store,
        cursor_key=b"a06-fixed-test-key",
    )

    derived = env.task_service.derive(
        env.run.id,
        env.assessment.id,
        P1TaskDeriveRequest(
            idempotency_key="a06-task-seed",
            expected_facts_hash=(
                env.assessment.facts_hash
            ),
        ),
    )

    assert derived.items

    env.task = derived.items[0]

    env.report_store = ReportV2Store(
        tmp_path
        / "reports"
        / "report_v2.db",
        min_free_bytes=0,
    )
    env.report_store.initialize()

    env.service = ReportV2Service(
        env.registry,
        env.assessment_store,
        env.task_store,
        env.report_store,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "A06 Report V2 must not invoke "
            "network or subprocess work"
        )

    monkeypatch.setattr(
        "subprocess.Popen",
        forbidden,
    )
    monkeypatch.setattr(
        "socket.socket.connect",
        forbidden,
    )

    yield env

    env.registry.close()


def create_report(
    env,
    *,
    key: str = "report-first",
    task_refs: list[P1TaskRef] | None = None,
):
    return env.service.create(
        env.run.id,
        env.assessment.id,
        idempotency_key=key,
        task_refs=task_refs,
    )


def test_create_report_snapshot_and_artifacts(
    report_env,
) -> None:
    env = report_env

    report = create_report(env)

    value = report.model_dump(
        mode="json"
    )

    validator(
        "ReportV2Snapshot"
    ).validate(value)

    assert report.snapshot_id.startswith(
        "rptv2_"
    )

    assert (
        report.binding.scan_ref.scan_id
        == env.run.id
    )

    assert (
        report.binding.assessment_ref.assessment_id
        == env.assessment.id
    )

    assert (
        report.binding.assessment_ref.version
        == env.assessment.version
    )

    assert (
        report.binding.assessment_ref.facts_hash
        == env.assessment.facts_hash
    )

    assert (
        report.binding.assessment_ref.usage_hash
        == env.assessment.usage_hash
    )

    assert (
        report.binding.assessment_ref.rule_version
        == env.assessment.rule_version
    )

    assert report.binding.task_refs == []
    assert report.binding.notice_refs == []
    assert report.binding.algorithm_refs == []

    assert {
        artifact.format
        for artifact in report.artifacts
    } == {
        "html",
        "json",
    }

    json_payload = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "json",
    )

    html_payload = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "html",
    )

    assert json_payload
    assert html_payload

    artifact_map = {
        artifact.format: artifact
        for artifact in report.artifacts
    }

    assert (
        digest(json_payload)
        == artifact_map[
            "json"
        ].content_hash
    )

    assert (
        len(json_payload)
        == artifact_map[
            "json"
        ].size_bytes
    )

    assert (
        digest(html_payload)
        == artifact_map[
            "html"
        ].content_hash
    )

    assert (
        len(html_payload)
        == artifact_map[
            "html"
        ].size_bytes
    )


def test_report_json_contains_complete_fixed_sources(
    report_env,
) -> None:
    env = report_env

    report = create_report(
        env,
        key="complete-sources",
    )

    raw = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "json",
    )

    document = json.loads(raw)

    by_authority = {
        section["authority"]: section
        for section in document["sections"]
    }

    assert {
        "scan_facts",
        "formal_assessment",
        "workflow",
        "ai_explanation",
    } == set(by_authority)

    assert (
        by_authority[
            "scan_facts"
        ]["content"]
        == env.run.model_dump(mode="json")
    )

    assert (
        by_authority[
            "formal_assessment"
        ]["content"]
        == env.assessment.model_dump(
            mode="json"
        )
    )

    ai = by_authority[
        "ai_explanation"
    ]["content"]

    assert (
        ai["ai_status"]
        == env.assessment.ai_status
        == "fallback"
    )

    assert (
        ai["ai_summary"]
        == env.assessment.ai_summary
    )

    assert (
        ai["ai_evidence_ids"]
        == env.assessment.ai_evidence_ids
    )


def test_snapshot_refs_resolve_to_immutable_content(
    report_env,
) -> None:
    env = report_env

    report = create_report(
        env,
        key="snapshot-ref",
    )

    raw = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "json",
    )

    document = json.loads(raw)

    for section in document["sections"]:
        prefix, fragment = (
            section[
                "snapshot_ref"
            ].split("#", 1)
        )

        assert prefix.endswith(
            (
                f"/report-v2/"
                f"{report.snapshot_id}"
                "?format=json"
            )
        )

        resolved = pointer(
            document,
            fragment,
        )

        assert (
            digest(resolved)
            == section[
                "content_hash"
            ]
        )


def test_same_request_replays_original_snapshot(
    report_env,
) -> None:
    env = report_env

    first = create_report(
        env,
        key="same-request",
    )

    second = create_report(
        env,
        key="same-request",
    )

    assert (
        second.snapshot_id
        == first.snapshot_id
    )

    assert (
        second.created_at
        == first.created_at
    )

    assert (
        second.content_hash
        == first.content_hash
    )

    assert (
        second.model_dump(mode="json")
        == first.model_dump(mode="json")
    )


def test_report_uses_requested_historical_task_version(
    report_env,
) -> None:
    env = report_env

    original = env.task

    changed = env.task_store.patch(
        env.run.id,
        env.assessment.id,
        original.task_id,
        original.version,
        {
            "status": "in_progress",
            "note": "报告创建前已经继续处理",
        },
    )

    assert changed["version"] == 2

    report = create_report(
        env,
        key="historical-task",
        task_refs=[
            P1TaskRef(
                task_id=original.task_id,
                version=1,
            )
        ],
    )

    assert (
        report.binding.task_refs[0].version
        == 1
    )

    raw = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "json",
    )

    document = json.loads(raw)

    workflow = next(
        section
        for section in document["sections"]
        if section["authority"]
        == "workflow"
    )

    saved_task = workflow[
        "content"
    ]["tasks"][0]

    assert saved_task["version"] == 1
    assert saved_task["status"] == "todo"
    assert saved_task["note"] == ""

    current = env.task_store.get(
        env.run.id,
        env.assessment.id,
        original.task_id,
    )

    assert current["version"] == 2
    assert current["status"] == "in_progress"


def test_later_task_change_does_not_change_old_report(
    report_env,
) -> None:
    env = report_env

    original = env.task

    report = create_report(
        env,
        key="immutable-task-report",
        task_refs=[
            P1TaskRef(
                task_id=original.task_id,
                version=1,
            )
        ],
    )

    before_json = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "json",
    )

    before_html = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "html",
    )

    env.task_store.patch(
        env.run.id,
        env.assessment.id,
        original.task_id,
        1,
        {
            "status": "in_progress",
            "note": "后续状态变化",
        },
    )

    after_json = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "json",
    )

    after_html = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "html",
    )

    assert after_json == before_json
    assert after_html == before_html

    stored = env.service.get(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
    )

    assert (
        stored.model_dump(mode="json")
        == report.model_dump(mode="json")
    )


def test_missing_task_version_is_not_replaced_by_latest(
    report_env,
) -> None:
    env = report_env

    with pytest.raises(
        ReportV2ServiceError
    ) as error:
        create_report(
            env,
            key="missing-version",
            task_refs=[
                P1TaskRef(
                    task_id=env.task.task_id,
                    version=999,
                )
            ],
        )

    service_error(
        error,
        "not_found",
        "task_version_not_found",
    )


@pytest.mark.parametrize(
    ("kind", "value", "reason"),
    [
        (
            "notice",
            P1NoticeRef(
                draft_id="ntc_not_wired",
                content_hash="a" * 64,
            ),
            "notice_snapshot_reader_not_available",
        ),
        (
            "algorithm",
            P1AlgorithmRef(
                kind="graph",
                version="resource-graph/1.0",
                content_hash="b" * 64,
            ),
            "observation_snapshot_reader_not_available",
        ),
    ],
)
def test_unverified_external_snapshot_refs_are_not_trusted(
    report_env,
    kind,
    value,
    reason,
) -> None:
    env = report_env

    kwargs = {
        "idempotency_key": (
            f"unsupported-{kind}"
        )
    }

    if kind == "notice":
        kwargs["notice_refs"] = [value]
    else:
        kwargs["algorithm_refs"] = [value]

    with pytest.raises(
        ReportV2ServiceError
    ) as error:
        env.service.create(
            env.run.id,
            env.assessment.id,
            **kwargs,
        )

    service_error(
        error,
        "not_ready",
        reason,
    )


def test_non_reportable_scan_is_rejected_before_generation(
    report_env,
) -> None:
    env = report_env

    queued = seed(
        env,
        2,
        "queued",
    )

    with pytest.raises(
        ReportV2ServiceError
    ) as error:
        env.service.create(
            queued.id,
            "asm_not_needed",
            idempotency_key="queued-report",
        )

    service_error(
        error,
        "not_ready",
        "scan_not_reportable",
    )


def test_report_generation_does_not_mutate_source_stores(
    report_env,
) -> None:
    env = report_env

    before = {
        "scan": db_hash(
            env.path / "scans.db"
        ),
        "assessment": db_hash(
            env.path / "assessment.db"
        ),
        "tasks": db_hash(
            env.task_store.path
        ),
    }

    report = create_report(
        env,
        key="readonly-sources",
        task_refs=[
            P1TaskRef(
                task_id=env.task.task_id,
                version=env.task.version,
            )
        ],
    )

    assert report.snapshot_id

    after = {
        "scan": db_hash(
            env.path / "scans.db"
        ),
        "assessment": db_hash(
            env.path / "assessment.db"
        ),
        "tasks": db_hash(
            env.task_store.path
        ),
    }

    assert after == before


def test_html_is_self_contained_and_truth_preserving(
    report_env,
) -> None:
    env = report_env

    report = create_report(
        env,
        key="html-report",
    )

    raw = env.service.artifact(
        env.run.id,
        env.assessment.id,
        report.snapshot_id,
        "html",
    )

    text = raw.decode("utf-8")

    assert (
        "报告生成成功不表示合规已经验证"
        in text
    )

    assert (
        "任务完成也不表示相关义务已经履行"
        in text
    )

    assert "file://" not in text
    assert "/Users/" not in text
    assert "/workspace/" not in text
    assert "/tmp/" not in text
    assert "<script" not in text.lower()

@pytest.mark.parametrize('blocked', ['scan', 'assessment', 'task', 'json', 'html'])
def test_replay_never_reads_sources_or_renders(report_env, monkeypatch, blocked):
    env=report_env
    refs=[P1TaskRef(task_id=env.task.task_id,version=1)]
    first=create_report(env,key='offline-replay',task_refs=refs)
    before=db_hash(env.report_store.path)
    def forbidden(*args,**kwargs):
        raise AssertionError('replay touched unavailable '+blocked)
    targets={'scan':(env.registry,'get'),'assessment':(env.assessment_store,'get'),
             'task':(env.task_store,'get_version')}
    if blocked in targets:
        monkeypatch.setattr(*targets[blocked],forbidden)
    else:
        monkeypatch.setattr('app.p1.report_v2._render_'+blocked,forbidden)
    replay=create_report(env,key='offline-replay',task_refs=refs)
    assert replay==first
    assert db_hash(env.report_store.path)==before


def test_replay_conflict_precedes_unavailable_sources(report_env,monkeypatch):
    env=report_env
    create_report(env,key='conflict-first')
    before=db_hash(env.report_store.path)
    def forbidden(*args,**kwargs):raise AssertionError('conflict must not read sources')
    monkeypatch.setattr(env.registry,'get',forbidden)
    with pytest.raises(ReportV2ServiceError) as error:
        create_report(env,key='conflict-first',task_refs=[P1TaskRef(task_id='missing',version=1)])
    service_error(error,'conflict','idempotency_conflict')
    assert db_hash(env.report_store.path)==before


def test_replay_sorted_refs_and_legacy_fingerprint_survive_environment_changes(report_env,monkeypatch):
    env=report_env
    with __import__('sqlite3').connect(env.task_store.path) as db:
        ids=[row[0] for row in db.execute('SELECT task_id FROM tasks ORDER BY task_id LIMIT 2')]
    refs=[P1TaskRef(task_id=tid,version=1) for tid in ids]
    first=create_report(env,key='legacy-sorted',task_refs=refs)
    fp=env.report_store.request_fingerprint(env.run.id,env.assessment.id,'legacy-sorted')
    assert fp==digest({'schema_version':'1.0',**first.binding.model_dump(mode='json')})
    raw={fmt:env.service.artifact(env.run.id,env.assessment.id,first.snapshot_id,fmt) for fmt in ('html','json')}
    env.service.max_document_bytes=1;env.service.max_included_items=1
    env.report_store.max_artifact_bytes=1;env.report_store.max_snapshot_bytes=1
    monkeypatch.setattr('app.p1.report_v2.REPORT_V2_VERSION','future-generator')
    def forbidden(*args,**kwargs):raise AssertionError('old replay read source or renderer')
    for obj,name in ((env.registry,'get'),(env.assessment_store,'get'),(env.task_store,'get_version')):
        monkeypatch.setattr(obj,name,forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_json',forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_html',forbidden)
    assert create_report(env,key='legacy-sorted',task_refs=list(reversed(refs)))==first
    for fmt in raw:assert env.service.artifact(env.run.id,env.assessment.id,first.snapshot_id,fmt)==raw[fmt]


@pytest.mark.parametrize('budget',['max_included_items','max_document_bytes'])
def test_new_generation_budget_fails_before_renderer(report_env,monkeypatch,budget):
    env=report_env;setattr(env.service,budget,1)
    before=db_hash(env.report_store.path)
    def forbidden(*args,**kwargs):raise AssertionError('budget must precede render')
    monkeypatch.setattr('app.p1.report_v2._render_json',forbidden)
    monkeypatch.setattr('app.p1.report_v2._render_html',forbidden)
    with pytest.raises(ReportV2ServiceError) as error:create_report(env,key='budget')
    service_error(error,'upstream_unavailable','report_generation_capacity_exceeded')
    assert db_hash(env.report_store.path)==before


def test_new_key_still_reads_unavailable_source(report_env,monkeypatch):
    from app.persistence import ScanRegistryError
    env=report_env;create_report(env,key='existing')
    before=db_hash(env.report_store.path)
    def unavailable(*args,**kwargs):raise ScanRegistryError('registry_io_failed')
    monkeypatch.setattr(env.registry,'get',unavailable)
    with pytest.raises(ReportV2ServiceError) as error:create_report(env,key='new')
    service_error(error,'upstream_unavailable','scan_store_unavailable')
    assert db_hash(env.report_store.path)==before
