"""P0.1 contract negatives using constructed, persisted TEST_ONLY records.

The genuine ZIP/gateway coverage has a separate test module. These records
exercise states such as historical missing hashes and ambiguous ownership
that the current scanner may not generate.
"""

from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.assessment.engine import facts_digest
from app.domain.models import CONTRACT_VERSION, Component, Evidence, ScanError, ScanRun
from app.persistence import SQLiteScanRunRegistry


_TEST_ACCOUNT_A = "usr_" + "1" * 32
_TEST_ACCOUNT_B = "usr_" + "2" * 32
_NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
_PRODUCER = {
    "manifest": "openguard-python-manifest-parser",
    "lock": "openguard.dependency-observations.lock",
    "sbom": "openguard.dependency-observations.sbom",
}


def _identifier(prefix, number):
    return f"{prefix}_{UUID(int=number)}"


def _sha256(label):
    return sha256(f"SYNTHETIC_TEST_ONLY:{label}".encode()).hexdigest()


def _evidence(number, source="manifest", *, hashed=True, version="1.0.0", locator=None):
    if locator is None:
        locator = {
            "manifest": f"pyproject.toml:project.dependencies[{number}]",
            "lock": f"uv.lock:/package/{number}",
            "sbom": f"bom.json:/components/{number}",
        }[source]
    return Evidence(
        id=_identifier("evd", number),
        kind="manifest_field",
        locator=locator,
        excerpt=f"test-dep=={version}" if source == "manifest" else None,
        content_hash={"algorithm": "sha256", "value": _sha256(locator.split(":")[0])} if hashed else None,
        detected_by="manifest_parser",
        producer={"type": "parser", "name": _PRODUCER[source], "version": "0.1.0" if source == "manifest" else "b58/1"},
        observed_at=_NOW,
        verification_status="pending",
    )


def _component(number, *evidence, version="1.0.0", component_type="library"):
    return Component(
        id=_identifier("cmp", number),
        name="test-dep",
        version=version,
        ecosystem="pypi",
        component_type=component_type,
        evidence_ids=[item.id for item in evidence],
        detected_by=["manifest_parser"],
        confidence=1.0,
    )


def _conflict(*evidence):
    return ScanError(
        code="lock_version_conflict",
        stage="scan",
        message="TEST_ONLY dependency version conflict",
        recoverable=True,
        evidence_ids=[item.id for item in evidence],
    )


@dataclass
class _Harness:
    client: TestClient
    registry: SQLiteScanRunRegistry
    database: Path
    account: str | None = _TEST_ACCOUNT_A

    def enqueue(self, number):
        run = ScanRun(
            contract_version=CONTRACT_VERSION,
            id=_identifier("scn", number),
            status="queued",
            stage="queued",
            progress=0,
            project={
                "id": _identifier("prj", number),
                "name": "SYNTHETIC_TEST_ONLY boundary fixture",
                "source_type": "zip",
                "source": "test-only.zip",
                "created_at": _NOW,
            },
            provenance={
                "input_digest": {"algorithm": "sha256", "value": _sha256(f"input:{number}")},
                "ruleset_version": "TEST_ONLY",
                "contract_version": CONTRACT_VERSION,
                "ai_enabled": False,
                "run_environment": {
                    "python_version": "TEST_ONLY",
                    "platform": "TEST_ONLY",
                    "openguard_version": "TEST_ONLY",
                },
            },
            summary={
                "component_count": 0,
                "ai_asset_count": 0,
                "evidence_count": 0,
                "finding_counts": {"pass": 0, "warning": 0, "review_required": 0, "unknown": 0},
            },
            created_at=_NOW,
        )
        return self.registry.create(run)

    def save(self, number, components=(), evidence=(), errors=()):
        queued = self.enqueue(number)
        data = queued.run.model_dump(mode="python")
        data.update(status="running", stage="ingestion", progress=10, started_at=_NOW + timedelta(seconds=1))
        running = self.registry.replace(ScanRun.model_validate(data), expected_revision=queued.revision)
        data.update(
            status="partial" if errors else "completed",
            stage="scan" if errors else "completed",
            progress=90 if errors else 100,
            components=list(components),
            evidence=list(evidence),
            errors=list(errors),
            finished_at=_NOW + timedelta(seconds=2),
        )
        data["summary"].update(component_count=len(components), evidence_count=len(evidence))
        return self.registry.replace(ScanRun.model_validate(data), expected_revision=running.revision)

    def read(self, record, params=None, **kwargs):
        return self.client.get(f"/api/v1/scans/{record.run.id}/dependency-evidence", params=params, **kwargs)


@pytest.fixture
def contract_harness(tmp_path):
    tmp_path.chmod(0o700)
    database = tmp_path / "scans.db"
    with closing(SQLiteScanRunRegistry(database)) as registry:
        api = create_app(registry)

        async def trusted_scope(scope, receive, send):
            # A controlled equivalent of the gateway's trusted scope state for
            # these contract tests only. Never read identity from HTTP headers.
            if scope["type"] == "http" and harness.account is not None:
                state = {**scope.get("state", {}), "local_account_id": harness.account}
                scope = {**scope, "state": state}
            await api(scope, receive, send)

        with TestClient(trusted_scope) as client:
            harness = _Harness(client, registry, database)
            yield harness


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _error(response, status, code=None):
    assert response.status_code == status, response.text
    if code is not None:
        assert response.json()["error"]["code"] == code


def _many_components(harness, scan_number, count):
    sources = [_evidence(number, "lock") for number in range(1, count + 1)]
    components = [_component(number, item) for number, item in enumerate(sources, start=1)]
    return harness.save(scan_number, list(reversed(components)), list(reversed(sources)))


def test_task45_dependency_evidence_contract_is_get_only(contract_harness):
    route = "/api/v1/scans/{scan_id}/dependency-evidence"
    routes = contract_harness.client.get("/openapi.json").json()["paths"]
    assert set(routes[route]) == {"get"}


def test_task45_dependency_evidence_contract_default_maximum_and_stable_pages(contract_harness):
    stored = _many_components(contract_harness, 1, 105)
    first = _ok(contract_harness.read(stored))
    assert first["schema_version"] == "openguard-dependency-evidence/1"
    assert first["scan_ref"] == {
        "scan_id": stored.run.id,
        "registry_revision": stored.revision,
        "revision": None,
        "status": "completed",
        "facts_hash": facts_digest(stored.run),
        "input_hash": stored.run.provenance.input_digest.value,
        "inventory_hash": None,
    }
    assert first["source"] is None
    assert (first["limit"], first["total"], first["returned"]) == (50, 105, 50)
    second = _ok(contract_harness.read(stored, {"cursor": first["next_cursor"]}))
    third = _ok(contract_harness.read(stored, {"cursor": second["next_cursor"]}))
    assert third["next_cursor"] is None and third["returned"] == 5
    combined = [item["resource_id"] for page in (first, second, third) for item in page["items"]]
    assert combined == sorted(component.id for component in stored.run.components)
    assert first["items"][0]["role_state"] == "inferred"
    assert first["items"][0]["evidence"][0]["verification_status"] == "pending"
    assert first["items"][0]["evidence"][0]["source_sha256"] != first["scan_ref"]["facts_hash"]
    maximum = _ok(contract_harness.read(stored, {"limit": 100}))
    assert (maximum["limit"], maximum["total"], maximum["returned"]) == (100, 105, 100)
    assert maximum["next_cursor"]
    _error(contract_harness.read(stored, {"limit": 101}), 422)
    _error(contract_harness.read(stored, {"limit": 0}), 422)
    _error(contract_harness.read(stored, [("source", "lock"), ("source", "sbom")]),
           400, "dependency_evidence_query_invalid")


def test_task45_dependency_evidence_contract_empty_completed_and_unready(contract_harness):
    stored = contract_harness.save(1)
    empty = _ok(contract_harness.read(stored))
    assert empty["scan_ref"]["status"] == "completed"
    assert (empty["total"], empty["returned"], empty["items"], empty["next_cursor"]) == (0, 0, [], None)
    assert empty["incomplete"] is False
    _error(contract_harness.read(contract_harness.enqueue(2)), 409, "scan_not_ready")


def test_task45_dependency_evidence_contract_cursor_scope_and_tamper(contract_harness):
    left = _many_components(contract_harness, 1, 3)
    right = _many_components(contract_harness, 2, 3)
    filters = {"source": "lock", "limit": 1}
    page = _ok(contract_harness.read(left, filters))
    assert page["source"] == "lock" and page["total"] == 3
    token = page["next_cursor"]
    assert isinstance(token, str) and token
    good = {**filters, "cursor": token}
    assert _ok(contract_harness.read(left, good))["items"][0]["resource_id"] == _identifier("cmp", 2)
    changed_token = ("A" if token[0] != "A" else "B") + token[1:]
    for record, query in (
        (left, {**good, "cursor": changed_token}),
        (right, good),
        (left, {**good, "source": "sbom"}),
        (left, {**good, "limit": 2}),
    ):
        _error(contract_harness.read(record, query), 400, "dependency_evidence_cursor_invalid")

    # Use the same app, registry and signing key to prove that the explicit
    # trusted account identity also participates in the cursor binding.
    contract_harness.account = _TEST_ACCOUNT_B
    _error(contract_harness.read(left, good), 400, "dependency_evidence_cursor_invalid")
    contract_harness.account = None
    _error(contract_harness.read(left, good, headers={"X-Local-Account-Id": _TEST_ACCOUNT_A}),
           401, "auth_login_required")


@pytest.mark.parametrize("change", ("facts", "registry_revision"))
def test_task45_dependency_evidence_contract_rejects_stale_cursor_without_writing(
    contract_harness, monkeypatch, change,
):
    stored = _many_components(contract_harness, 1, 3)
    untouched = contract_harness.database.read_bytes()
    initial = _ok(contract_harness.read(stored, {"limit": 1}))
    assert initial["next_cursor"]
    if change == "facts":
        data = stored.run.model_dump(mode="python")
        data["components"][0]["version"] = "9.1.0"
        replacement = replace(stored, run=ScanRun.model_validate(data))
        assert facts_digest(replacement.run) != facts_digest(stored.run)
        assert replacement.revision == stored.revision
    else:
        replacement = replace(stored, revision=stored.revision + 1)
        assert facts_digest(replacement.run) == facts_digest(stored.run)

    # Terminal ScanRun records are immutable. Inject a different validated
    # registry read only for the stale-cursor negative; never revise the DB.
    real_get = contract_harness.registry.get
    seen_ids = []

    def read_changed_snapshot(scan_id):
        seen_ids.append(scan_id)
        return replacement if scan_id == stored.run.id else real_get(scan_id)

    monkeypatch.setattr(contract_harness.registry, "get", read_changed_snapshot)
    response = contract_harness.read(stored, {"limit": 1, "cursor": initial["next_cursor"]})
    _error(response, 409, "dependency_evidence_cursor_stale")
    assert seen_ids == [stored.run.id]
    assert contract_harness.database.read_bytes() == untouched
    assert real_get(stored.run.id) == stored


def test_task45_dependency_evidence_contract_preserves_missing_sha_and_persisted_state(contract_harness):
    evidence = _evidence(1, "lock", hashed=False)
    component = _component(1, evidence)
    stored = contract_harness.save(1, [component], [evidence])
    untouched = contract_harness.database.read_bytes()
    body = _ok(contract_harness.read(stored))
    item, = body["items"]
    projected, = item["evidence"]
    assert projected["source"] == "lock"
    assert projected["evidence_id"] == evidence.id
    assert projected["file_path"] == "uv.lock"
    assert projected["source_sha256"] is None
    assert projected["verification_status"] == "pending"
    assert item["incomplete"] and "source_sha256_missing" in item["gaps"]
    assert item["role_state"] == "unknown"
    assert contract_harness.database.read_bytes() == untouched
    assert contract_harness.registry.get(stored.run.id) == stored


def test_task45_dependency_evidence_contract_only_interprets_proven_path_syntax(contract_harness):
    encoded = _evidence(1, locator="project%20files/pyproject.toml:project.dependencies[0]")
    malformed = _evidence(2, locator="project/%2e%2e/pyproject.toml:project.dependencies[0]")
    unknown_data = _evidence(3).model_dump(mode="python")
    unknown_data["producer"]["name"] = "test-only-unclassified-parser"
    unclassified = Evidence.model_validate(unknown_data)
    evidence = [encoded, malformed, unclassified]
    stored = contract_harness.save(1, [_component(index, entry) for index, entry in enumerate(evidence, start=1)],
                                   evidence)
    items = _ok(contract_harness.read(stored))["items"]
    good, invalid, unknown = (item["evidence"][0] for item in items)
    assert good["file_path"] == "project files/pyproject.toml"
    assert good["locator"] == encoded.locator and good["source_sha256"] == encoded.content_hash.value
    assert invalid["file_path"] is invalid["locator"] is None
    assert items[1]["incomplete"] and items[1]["role_state"] == "unknown"
    assert unknown["source"] == "unknown" and unknown["file_path"] is None
    assert items[2]["incomplete"] and items[2]["role_state"] == "unknown"


@pytest.mark.parametrize("locked_owners,expected", [(0, "incomplete"), (2, "ambiguous")])
def test_task45_dependency_evidence_contract_never_guesses_conflict_ownership(
    contract_harness, locked_owners, expected,
):
    declared = _evidence(1)
    lock = _evidence(2, "lock")
    left = _component(1, declared)
    competing = [_component(number, lock, version="2.0.0") for number in range(2, 2 + locked_owners)]
    stored = contract_harness.save(1, [left, *competing], [declared, lock], [_conflict(declared, lock)])
    page = _ok(contract_harness.read(stored))
    assert page["scan_ref"]["status"] == "partial"
    row = next(item for item in page["items"] if item["resource_id"] == left.id)
    conflict, = row["conflicts"]
    assert conflict["code"] == "lock_version_conflict" and conflict["status"] == expected
    assert conflict["lock"] is None
    assert row["incomplete"] and row["role_state"] == "unknown"


def test_task45_dependency_evidence_contract_marks_truncated_evidence_incomplete(contract_harness):
    evidence = [_evidence(number, "lock") for number in range(1, 52)]
    stored = contract_harness.save(1, [_component(1, *reversed(evidence))], list(reversed(evidence)))
    page = _ok(contract_harness.read(stored))
    row, = page["items"]
    assert page["incomplete"] and row["incomplete"] and row["gaps"]
    assert (row["evidence_total"], row["evidence_returned"]) == (51, 50)
    projected_ids = [item["evidence_id"] for item in row["evidence"]]
    assert len(set(projected_ids)) == 50
    assert set(projected_ids) < {item.id for item in evidence}
    repeated = _ok(contract_harness.read(stored))["items"][0]
    assert [item["evidence_id"] for item in repeated["evidence"]] == projected_ids


def test_task45_dependency_evidence_contract_marks_truncated_conflicts_and_side_incomplete(contract_harness):
    declared = [_evidence(number) for number in range(1, 10)]
    locked = [_evidence(number, "lock") for number in range(10, 19)]
    left = _component(1, *declared)
    others = [_component(number, item, version="2.0.0")
              for number, item in enumerate(locked, start=2)]
    errors = [_conflict(*declared, item) for item in locked]
    stored = contract_harness.save(1, [left, *others], [*declared, *locked], errors)
    page = _ok(contract_harness.read(stored))
    row = next(item for item in page["items"] if item["resource_id"] == left.id)
    assert page["incomplete"] and row["incomplete"]
    assert (row["conflicts_total"], row["conflicts_returned"]) == (9, 8)
    assert len(row["conflicts"]) == 8
    for conflict in row["conflicts"]:
        side = conflict["declaration"]
        assert side["resource_id"] == left.id and side["incomplete"]
        assert (side["evidence_total"], side["evidence_returned"], len(side["evidence"])) == (9, 8, 8)
