"""Authenticated TEST_ONLY ZIP-to-archive and persisted Report V2 1.1 behavior."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from hashlib import sha256
import json
import os
import socket
import sqlite3
from threading import Barrier

import pytest
from starlette.testclient import TestClient

from app.api.main import create_default_app
from app.assessment.engine import facts_digest
from app.local_accounts import LocalAccountGateway
from app.p1.report_v2 import ReportV2ServiceError
from test_task45_dependency_evidence_real_zip import (
    GatewayHarness, ISOLATED_ENV, ORIGIN, ROOT_PACKAGE, _checked, _frontend,
    _match_evidence, _uv,
)


SCHEMA = "openguard-report-v2-dependency-evidence/1"
WRITE_FLAG = "OPENGUARD_ENABLE_REPORT_V2_1_1_WRITES"
TABLES = ("report_snapshots", "report_artifacts", "report_requests")


@pytest.fixture
def open_report_gateway(tmp_path, monkeypatch):
    # The actual ZIP scanner and Assessment run in-process without DNS, public
    # Git, external scanners, P2, assistant, or any model provider.
    def deny_network(*args, **kwargs):
        pytest.fail("Report V2 integration must make no network calls")

    def guard_method(method):
        def guarded(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                deny_network()
            return method(sock, *args, **kwargs)
        return guarded

    for name in ("connect", "connect_ex", "sendto", "sendmsg"):
        method = getattr(socket.socket, name, None)
        if method is not None:
            monkeypatch.setattr(socket.socket, name, guard_method(method))
    for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
        monkeypatch.setattr(socket, name, deny_network)

    @contextmanager
    def opened(writes=True):
        safe_env = {**ISOLATED_ENV, "OPENGUARD_ENABLE_ASSESSMENTS": "1",
                    WRITE_FLAG: "1" if writes else "0"}
        with monkeypatch.context() as env:
            for name, value in safe_env.items():
                env.setenv(name, value)
            roots = {}

            def factory(path):
                app = create_default_app(data_dir=path)
                assert app.state.p2_service is None
                assert app.state.assistant_service is None
                assert app.state.git_scan_runtime is None
                assert app.state.zip_dispatcher is None
                assert app.state.zip_scan_runtime._ai_provider is None
                assert app.state.zip_scan_runtime._external_scanners is False
                assert app.state.assessment_service is not None
                assert app.state.assessment_service.provider is None
                assert app.state.report_v2_service.enable_v11_writes is writes
                roots[path.name] = path
                return app

            gateway = LocalAccountGateway(
                root=tmp_path / "accounts", origins=(ORIGIN,),
                cookie_name="og_session_451145114511", app_factory=factory, frontend=_frontend,
            )
            print("P1_1_REPORT_ACTIVE_ENV=" + json.dumps(
                {name: os.environ[name] for name in safe_env}, sort_keys=True
            ))
            with TestClient(gateway, base_url=ORIGIN) as client:
                yield GatewayHarness(client, gateway, roots)

            assert roots
            for path in roots.values():
                assert (path / "assessment.db").is_file()
                assert (path / "report_v2.db").is_file()
                assert not (path / "p2.db").exists()
                assert not (path / "assistant.db").exists()

    return opened


def _headers(session):
    return {"Origin": ORIGIN, "X-CSRF-Token": session["csrf_token"]}


def _login(harness, name):
    initial = _checked(harness.client.get("/api/v1/auth/session"), 200).json()
    return _checked(harness.client.post(
        "/api/v1/auth/login", headers=_headers(initial),
        json={"username": name, "password": "SparseSyntheticOnly45!"},
    ), 200).json()


def _post(harness, session, path, key, **fields):
    return harness.client.post(path, headers=_headers(session),
                               json={"idempotency_key": key, **fields})


def _error(response, status, code, reason):
    body = _checked(response, status).json()["error"]
    assert body["code"] == code
    assert body["details"]["reason"] == reason


def _assessment(harness, path, stored):
    # The original ZIP terminal observer generates a real persisted Assessment.
    job = _checked(harness.client.get(f"{path}/assessments/jobs/initial-{stored.run.id}"), 200).json()
    assert job["status"] == "succeeded"
    assert job["model_calls"] == 0
    fixed = _checked(harness.client.get(f"{path}/assessments/{job['assessment_id']}"), 200).json()
    assert fixed["formal"] is True
    assert fixed["scan_id"] == stored.run.id
    assert fixed["facts_hash"] == facts_digest(stored.run)
    return fixed


def _report_path(harness, path, stored):
    fixed = _assessment(harness, path, stored)
    return f"{path}/assessments/{fixed['id']}/report-v2", fixed


def _report_artifacts(harness, snapshot):
    return {row["format"]: _checked(harness.client.get(row["href"]), 200).content
            for row in snapshot["artifacts"]}


def _db_path(harness, session):
    return harness.roots[session["user"]["id"]] / "report_v2.db"


def _report_state(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        return [db.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in TABLES]


def _full_projection(harness, path):
    first = harness.project(path)
    items = list(first["items"])
    cursor = first["next_cursor"]
    for _ in range((first["total"] + first["limit"] - 1) // first["limit"]):
        if cursor is None:
            break
        page = harness.project(path, cursor=cursor)
        assert page["scan_ref"] == first["scan_ref"] and page["total"] == first["total"]
        items.extend(page["items"])
        cursor = page["next_cursor"]
    assert cursor is None and len(items) == first["total"]
    return {
        "schema_version": SCHEMA,
        "scan_ref": first["scan_ref"],
        "coverage": first["coverage"],
        "total": first["total"],
        "returned": len(items),
        "incomplete": first["scan_ref"]["status"] == "partial" or any(row["incomplete"] for row in items),
        "items": items,
    }


def _zip_members(case):
    if case == "completed":
        dependencies = b"".join(f"report-test-manifest-{i:03}==1.2.3\n".encode() for i in range(108))
        sbom = json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [
            {"bom-ref": "test-only-bom", "name": "report-test-sbom",
             "version": "1.2.3", "purl": "pkg:npm/report-test-sbom@1.2.3"},
        ]}).encode()
        return {"package.json": ROOT_PACKAGE, "requirements.txt": dependencies,
                "uv.lock": _uv("report-test-lock", "1.2.3"), "bom.json": sbom}
    if case == "partial":
        return {
            "package.json": ROOT_PACKAGE,
            "sub/pyproject.toml": (b'[project]\nname = "test-only-app"\nversion = "1.0.0"\n'
                                   b'dependencies = ["report-test-conflict==1.2.3"]\n'),
            "sub/uv.lock": _uv("report-test-conflict", "2.3.4"),
        }
    if case == "evidence-gap":
        return {"package.json": ROOT_PACKAGE, **{
            f"workspace-{i:02}/requirements.txt": b"report-test-repeated==1.2.3\n"
            for i in range(51)
        }}
    assert case == "empty"
    return {"package.json": ROOT_PACKAGE}


@pytest.mark.parametrize(("case", "status", "total"), [
    ("completed", "completed", 110),
    ("partial", "partial", 2),
    ("empty", "completed", 0),
    ("evidence-gap", "partial", 1),
])
def test_real_zip_archives_the_same_formal_assessment_and_full_p01_projection(
    open_report_gateway, case, status, total,
):
    with open_report_gateway() as harness:
        session = harness.register("report_zip_owner")
        files = _zip_members(case)
        path, stored = harness.upload(session, files)
        assert stored.run.status.value == status
        report_path, assessment = _report_path(harness, path, stored)
        snapshot = _checked(_post(harness, session, report_path, "test-only-v11",
                                  schema_version="1.1"), 200).json()
        assert snapshot["schema_version"] == "1.1"
        document = json.loads(_report_artifacts(harness, snapshot)["json"])
        assert document["snapshot_id"] == snapshot["snapshot_id"]
        assert document["binding"] == snapshot["binding"]
        ref = snapshot["binding"]["assessment_ref"]
        assert ref["formal"] is True and ref["assessment_id"] == assessment["id"]
        assert ref["scan_id"] == stored.run.id and ref["facts_hash"] == assessment["facts_hash"]
        (section,) = [row for row in document["sections"] if row["schema_version"] == SCHEMA]
        (descriptor,) = [row for row in snapshot["sections"] if row["schema_version"] == SCHEMA]
        assert {key: value for key, value in section.items() if key != "content"} == descriptor
        assert descriptor["authority"] == "observation"
        assert descriptor["source_ids"] == [stored.run.id]
        assert descriptor["title"] == "依赖证据"
        observation = section["content"]
        assert observation == _full_projection(harness, path)
        assert observation["scan_ref"] == snapshot["binding"]["scan_ref"]
        assert observation["total"] == observation["returned"] == total
        assert observation["incomplete"] is (case in ("partial", "evidence-gap"))
        evidence = {row.id: row for row in stored.run.evidence}
        for entry in observation["items"]:
            for reference in entry["evidence"]:
                _match_evidence(reference, evidence[reference["evidence_id"]], reference["file_path"], files)
        if case == "completed":
            assert {tuple(row["sources"]) for row in observation["items"]} == {
                ("manifest",), ("lock",), ("sbom",),
            }
            assert {row["role_state"] for row in observation["items"]} == {"observed", "inferred"}
        if case == "partial":
            for entry in observation["items"]:
                assert entry["role_state"] == "unknown"
                (conflict,) = entry["conflicts"]
                assert conflict["status"] == "confirmed" and conflict["code"] == "lock_version_conflict"
                for side, expected_path, expected_version in (
                    ("declaration", "sub/pyproject.toml", "1.2.3"),
                    ("lock", "sub/uv.lock", "2.3.4"),
                ):
                    assert conflict[side]["version"] == expected_version
                    (reference,) = conflict[side]["evidence"]
                    _match_evidence(reference, evidence[reference["evidence_id"]], expected_path, files)
        if case == "evidence-gap":
            (entry,) = observation["items"]
            assert entry["evidence_total"] == 51 and entry["evidence_returned"] == 50
            assert "evidence_limit_exceeded" in entry["gaps"]
            assert any(error.code == "python_dependency_scan_partial" for error in stored.run.errors)
        print(f"P1_1_REAL_ZIP case={case} terminal={status} rows={total} "
              f"incomplete={observation['incomplete']} p2=false formal=true")


def test_report_rejects_missing_and_other_scan_assessments(open_report_gateway):
    with open_report_gateway() as harness:
        session = harness.register("report_scope_owner")
        path, stored = harness.upload(session, _zip_members("empty"))
        other_path, other = harness.upload(session, _zip_members("partial"))
        formal = _assessment(harness, path, stored)
        assert other.run.id != stored.run.id
        _error(_post(harness, session, f"{other_path}/assessments/{formal['id']}/report-v2",
                     "wrong-scan", schema_version="1.1"), 409, "conflict", "assessment_scan_mismatch")
        _error(_post(harness, session, f"{path}/assessments/asm_missing/report-v2",
                     "missing", schema_version="1.1"), 404, "not_found", "assessment_not_found")
        assert _report_state(_db_path(harness, session)) == [[], [], []]


def test_scoped_replay_survives_disabling_new_v11_writes(open_report_gateway):
    with open_report_gateway() as harness:
        session = harness.register("report_reopen_owner")
        path, stored = harness.upload(session, _zip_members("empty"))
        report_path, _ = _report_path(harness, path, stored)
        old = _checked(_post(harness, session, report_path, "same-legacy-key"), 200).json()
        new = _checked(_post(harness, session, report_path, "same-new-key", schema_version="1.1"), 200).json()
        assert old["schema_version"] == "1.0" and new["schema_version"] == "1.1"
        assert old["binding"] == new["binding"]
        assert old["provenance"]["parameters_hash"] != new["provenance"]["parameters_hash"]
        old_artifacts = _report_artifacts(harness, old)
        new_artifacts = _report_artifacts(harness, new)
        persisted = _report_state(_db_path(harness, session))
        assert tuple(map(len, persisted)) == (2, 4, 2)
        for key, other_version in (("same-legacy-key", "1.1"), ("same-new-key", "1.0")):
            _error(_post(harness, session, report_path, key, schema_version=other_version),
                   409, "conflict", "idempotency_conflict")
        assert _report_state(_db_path(harness, session)) == persisted

    with open_report_gateway(writes=False) as harness:
        session = _login(harness, "report_reopen_owner")
        assert _checked(_post(harness, session, report_path, "same-legacy-key",
                              schema_version="1.0"), 200).json() == old
        assert _checked(_post(harness, session, report_path, "same-new-key",
                              schema_version="1.1"), 200).json() == new
        assert _report_artifacts(harness, old) == old_artifacts
        assert _report_artifacts(harness, new) == new_artifacts
        for key, other_version in (("same-legacy-key", "1.1"), ("same-new-key", "1.0")):
            _error(_post(harness, session, report_path, key, schema_version=other_version),
                   409, "conflict", "idempotency_conflict")
        _error(_post(harness, session, report_path, "never-stored", schema_version="1.1"),
               409, "not_ready", "report_v2_1_1_write_disabled")
        assert _report_state(_db_path(harness, session)) == persisted
        legacy = _checked(_post(harness, session, report_path, "new-legacy"), 200).json()
        assert legacy["schema_version"] == "1.0"
        assert tuple(map(len, _report_state(_db_path(harness, session)))) == (3, 6, 3)


@pytest.mark.parametrize("versions", [("1.1",) * 4, ("1.0", "1.1", "1.0", "1.1")],
                         ids=("same-version", "mixed-versions"))
def test_concurrent_initial_misses_produce_one_immutable_bundle(open_report_gateway, versions, monkeypatch):
    with open_report_gateway() as harness:
        session = harness.register("report_race_owner")
        path, stored = harness.upload(session, _zip_members("empty"))
        assessment = _assessment(harness, path, stored)
        tenant = harness.gateway.apps[session["user"]["id"]]
        service = tenant.state.report_v2_service
        barrier = Barrier(len(versions))
        original_replay = service.report_store.replay

        def simultaneous_misses(*args, **kwargs):
            result = original_replay(*args, **kwargs)
            assert result is None, "Every worker must reach the write path"
            barrier.wait(timeout=10)
            return result

        monkeypatch.setattr(service.report_store, "replay", simultaneous_misses)

        def worker(version):
            try:
                return service.create(
                    stored.run.id, assessment["id"], idempotency_key="concurrent",
                    schema_version=version,
                )
            except ReportV2ServiceError as error:
                assert error.code == "conflict" and error.reason == "idempotency_conflict"
                return None

        with ThreadPoolExecutor(max_workers=len(versions)) as pool:
            results = list(pool.map(worker, versions))
        first = next(record for record in results if record is not None)
        for requested, result in zip(versions, results, strict=True):
            assert result == (first if requested == first.schema_version else None)
        snapshots, artifacts, requests = _report_state(_db_path(harness, session))
        assert (len(snapshots), len(artifacts), len(requests)) == (1, 2, 1)
        assert snapshots[0][0] == requests[0][-1] == first.snapshot_id
        assert {row[0] for row in artifacts} == {first.snapshot_id}


@pytest.mark.parametrize("corruption", ["fingerprint", "artifact"])
def test_corrupt_v11_archive_cannot_be_treated_as_an_idempotency_miss(open_report_gateway, corruption, monkeypatch):
    with open_report_gateway() as harness:
        session = harness.register("report_integrity_owner")
        path, stored = harness.upload(session, _zip_members("empty"))
        report_path, _ = _report_path(harness, path, stored)
        _checked(_post(harness, session, report_path, "archived", schema_version="1.1"), 200)
        db_path = _db_path(harness, session)
        with closing(sqlite3.connect(db_path)) as db, db:
            if corruption == "fingerprint":
                db.execute("UPDATE report_requests SET fingerprint=? WHERE request_key=?", ("0" * 64, "archived"))
            else:
                payload, = db.execute("SELECT payload FROM report_artifacts WHERE format='json'").fetchone()
                changed = payload + b" "
                db.execute("UPDATE report_artifacts SET payload=?, payload_hash=?, size_bytes=? WHERE format='json'",
                           (changed, sha256(changed).hexdigest(), len(changed)))
        before = _report_state(db_path)
        service = harness.gateway.apps[session["user"]["id"]].state.report_v2_service

        def forbidden(*args, **kwargs):
            pytest.fail("Corrupt persisted request was treated as a miss")

        monkeypatch.setattr(service, "_fixed_inputs", forbidden)
        _error(_post(harness, session, report_path, "archived", schema_version="1.1"),
               503, "upstream_unavailable", "storage_unavailable")
        assert _report_state(db_path) == before
