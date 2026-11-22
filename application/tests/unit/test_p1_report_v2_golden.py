"""Exact legacy requests and archive bytes, captured before the 1.1 writer."""
from base64 import b64encode
from contextlib import closing
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sqlite3
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.local_accounts import LocalAccountGateway
from app.p1 import report_v2
from app.p1.models import P1Binding
from app.p1.report_v2_store import ReportV2Store


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/p1"
ARCHIVE = FIXTURES / "report-v2-golden/legacy-v1.zip"
ORIGIN = "http://127.0.0.1:48123"
ACCOUNT = {"username": "legacy_golden", "password": "SyntheticTest2026!"}
EXPECTED = {
    "a": {
        "key": "semifinal-report",
        "snapshot": "rptv2_231ff532-57e1-4bfb-beec-5584facd6274",
        "canonical.json": (877, "025fd024dd929879275cd65f7404d2317eac4f64dc717f63315c841c5a64d705"),
        "request.json": (39, "5bfc9de06c949af2397a28c26c3a7d612c839edaf6f1fe0dfdf337c541d9a687"),
        "snapshot.json": (4355, "be64dd8203ef99efa24cad100b80967b7ed2c971310484d15c6795d727d26157"),
        "report.html": (80468, "7eb181cf719f438a338eaf0c7592fedce7c2e1c635d1ed8bdbb1cdb12b2feed7"),
        "report.json": (38779, "ee4687fd8490a55b6bee3e186bb2bf6a28cabbf6fcd38998bc3c877ca158d134"),
    },
    "b": {
        "key": "dev-test-report",
        "snapshot": "rptv2_5edad68e-cb0f-47b9-b534-74e45db7d55b",
        "canonical.json": (958, "d7f1c78e110252c87f3e3aeb62f39c3de9ecd6abbe165808c4f34c04a212f788"),
        "request.json": (155, "77de4ad9593f9ae40fb7d830cc03bc5703b7e3520c057b2ea095c8cc6c2e6313"),
        "snapshot.json": (4493, "b07f46f6a551d32aec7094d5211a825f92b2ce4df67d46bb571cdf25c4bf4acd"),
        "report.html": (54140, "757dc601d14d386cdea5eb82a20dcfe71cff9b7f72d2ac8450285826ee22d94d"),
        "report.json": (23447, "c80c84854f7f8ab6063f25381bcd3af9caf862a51cf03b97e35066bae120d9eb"),
    },
}
MEMBERS = ("canonical.json", "request.json", "snapshot.json", "report.html", "report.json")


@pytest.fixture(params=EXPECTED, ids=["historical-http-a", "historical-task-b"])
def golden(request):
    label = request.param
    expected = EXPECTED[label]
    with ZipFile(ARCHIVE) as archive:
        assert sorted(archive.namelist()) == sorted(
            f"{case}/{name}" for case in EXPECTED for name in MEMBERS
        )
        payloads = {name: archive.read(f"{label}/{name}") for name in MEMBERS}
    for name, raw in payloads.items():
        assert (len(raw), sha256(raw).hexdigest()) == expected[name]

    snapshot = json.loads(payloads["snapshot.json"])
    body = json.loads(payloads["request.json"])
    assert snapshot["schema_version"] == "1.0"
    assert snapshot["snapshot_id"] == expected["snapshot"]
    assert snapshot["provenance"]["parameters_hash"] == expected["canonical.json"][1]
    assert body["idempotency_key"] == expected["key"]
    assert "schema_version" not in body
    return expected, payloads, snapshot, body


def test_historical_canonical_preimage_and_writer_fingerprint(golden):
    expected, payloads, snapshot, _ = golden
    original_path = FIXTURES / "report-v2-legacy-writer/report_v2.py"
    assert sha256(original_path.read_bytes()).hexdigest() == (
        "3aa1a3ab82f51e096bc3586f2969fb56f16f734921f93b656b229d6488a92272"
    )
    spec = importlib.util.spec_from_file_location("app.p1._golden_a06_writer", original_path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    binding = P1Binding.model_validate(snapshot["binding"])
    value = {"schema_version": "1.0", **binding.model_dump(mode="json")}
    args = (binding.scan_ref, binding.assessment_ref, binding.task_refs,
            binding.notice_refs, binding.algorithm_refs)
    for writer in (original, report_v2):
        assert writer._canonical_bytes(value) == payloads["canonical.json"]
        assert writer.ReportV2Service._fingerprint(*args) == expected["canonical.json"][1]


def seed_historical_rows(store, golden):
    expected, payloads, snapshot, _ = golden
    binding = snapshot["binding"]
    scan_id = binding["scan_ref"]["scan_id"]
    assessment_id = binding["assessment_ref"]["assessment_id"]
    snapshot_id = expected["snapshot"]
    store.initialize()
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute(
            "INSERT INTO report_snapshots VALUES (?, ?, ?, ?, ?, ?)",
            (snapshot_id, scan_id, assessment_id, snapshot["created_at"],
             payloads["snapshot.json"], expected["snapshot.json"][1]),
        )
        for fmt in ("html", "json"):
            name = f"report.{fmt}"
            size, digest = expected[name]
            db.execute(
                "INSERT INTO report_artifacts VALUES (?, ?, ?, ?, ?)",
                (snapshot_id, fmt, payloads[name], digest, size),
            )
        db.execute(
            "INSERT INTO report_requests VALUES (?, ?, ?, ?, ?)",
            (scan_id, assessment_id, expected["key"], expected["canonical.json"][1], snapshot_id),
        )


class UnavailableSources:
    def __getattr__(self, name):
        raise AssertionError(f"Historical replay cannot consult a live source ({name})")


def forbidden_render(*args, **kwargs):
    raise AssertionError("Historical replay cannot render or create a replacement")


def report_state(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        rows = (
            db.execute("SELECT * FROM report_requests").fetchall(),
            db.execute("SELECT * FROM report_snapshots").fetchall(),
            db.execute("SELECT * FROM report_artifacts ORDER BY format").fetchall(),
        )
    return path.read_bytes(), rows


def test_historical_http_replay_and_download_use_the_original_archive(golden, tmp_path, monkeypatch):
    expected, payloads, snapshot, body = golden
    monkeypatch.setenv("OPENGUARD_WEB_ORIGINS", ORIGIN)
    monkeypatch.setattr(report_v2, "_render_html", forbidden_render)
    monkeypatch.setattr(report_v2, "_render_json", forbidden_render)
    monkeypatch.setattr(ReportV2Store, "create", forbidden_render)
    snapshots = []

    def tenant_factory(root):
        store = ReportV2Store(root / "report_v2.db", min_free_bytes=0)
        if not store.path.exists():
            seed_historical_rows(store, golden)
        snapshots.append((store.path, report_state(store.path)))
        sources = UnavailableSources()
        service = report_v2.ReportV2Service(
            sources, sources, sources, store, graph_reader=sources, notice_reader=sources
        )
        return create_app(sources, report_v2_service=service)

    binding = snapshot["binding"]
    scan_id = binding["scan_ref"]["scan_id"]
    assessment_id = binding["assessment_ref"]["assessment_id"]
    url = f"/api/v1/scans/{scan_id}/assessments/{assessment_id}/report-v2"
    for auth_action, auth_status in (("register", 201), ("login", 200)):
        gateway = LocalAccountGateway(
            root=tmp_path / "accounts", origins=(ORIGIN,), cookie_name="og_session_45a012345678",
            app_factory=tenant_factory, frontend=forbidden_render,
        )
        with TestClient(gateway, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
            session = client.get("/api/v1/auth/session")
            auth = client.post(
                f"/api/v1/auth/{auth_action}", json=ACCOUNT,
                headers={"X-CSRF-Token": session.json()["csrf_token"]},
            )
            assert auth.status_code == auth_status
            headers = {"X-CSRF-Token": auth.json()["csrf_token"]}
            omitted = client.post(
                url, content=payloads["request.json"],
                headers={**headers, "Content-Type": "application/json"},
            )
            explicit = client.post(url, json={**body, "schema_version": "1.0"}, headers=headers)
            assert omitted.status_code == explicit.status_code == 200
            assert omitted.json() == explicit.json() == snapshot
            disabled = client.post(
                url, json={"idempotency_key": "new-version", "schema_version": "1.1"},
                headers=headers,
            )
            assert disabled.status_code == 409
            assert disabled.json()["error"]["code"] == "not_ready"
            for fmt in ("html", "json"):
                name = f"report.{fmt}"
                size, digest = expected[name]
                download = client.get(f'{url}/{expected["snapshot"]}', params={"format": fmt})
                assert download.status_code == 200
                assert download.content == payloads[name]
                assert download.headers["Content-Length"] == str(size)
                assert download.headers["ETag"] == f'"sha256:{digest}"'
                base64_digest = b64encode(bytes.fromhex(digest)).decode("ascii")
                assert download.headers["Content-Digest"] == f"sha-256=:{base64_digest}:"

        path, before = snapshots[-1]
        assert tuple(map(len, before[1])) == (1, 1, 2)
        assert report_state(path) == before
    assert len(snapshots) == 2
    assert snapshots[0] == snapshots[1]
