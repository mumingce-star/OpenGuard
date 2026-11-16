"""Real ASGI account boundary plus a fixed-local-source P2 material flow.

All accounts, passwords and stores here are SYNTHETIC_TEST_ONLY. Auth wire
bodies/cookies/CSRF values are deliberately excluded from evidence capture.
"""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.api.main import create_default_app
from app.ingestion.fixed_git_snapshot import FixedGitSnapshot
from app.ingestion.git_stream import GitIngestionService
from app.local_accounts import AccountStore, LocalAccountGateway, SESSION_SECONDS


TASK = Path(__file__).resolve().parents[4]
ORIGIN = "http://127.0.0.1:48123"
PASSWORD = "SyntheticTest2026!"
COOKIE = "og_session_0123456789ab"
OUT = Path(os.environ.get("OPENGUARD_AUTH_TEST_EVIDENCE", str(TASK / "evidence/accounts-asgi")))
if not OUT.is_relative_to(TASK):
    raise RuntimeError("Auth test evidence must stay in TASK")
OUT.mkdir(parents=True, exist_ok=True)
HTTP_LEDGER = []


def ensure(condition, message):
    # Do not let pytest's assertion rewriting print bearer or CSRF values.
    if not condition:
        raise AssertionError(message)


async def frontend(scope, receive, send):
    await JSONResponse({"public_frontend": "SYNTHETIC_TEST_ONLY"})(scope, receive, send)


def gateway(root, monkeypatch, *, clock=None, max_accounts=25, registration_attempts=10):
    for key, value in {
        "OPENGUARD_ENABLE_AI": "0", "OPENGUARD_OLLAMA_DOCKER_HOST": "0",
        "OPENGUARD_ENABLE_PROFILE_METADATA": "0", "OPENGUARD_ENABLE_EXTERNAL_SCANNERS": "0",
        "OPENGUARD_ENABLE_DURABLE_ZIP": "0", "OPENGUARD_ENABLE_PROGRESS_EVENTS": "1",
        "OPENGUARD_ENABLE_ASSESSMENTS": "1", "OPENGUARD_ENABLE_PUBLIC_GIT": "1",
        "OPENGUARD_ENABLE_P2": "1", "OPENGUARD_P2_READONLY": "0",
        "OPENGUARD_P2_DATA_SCOPE": "TEST_ONLY", "OPENGUARD_WEB_ORIGINS": ORIGIN,
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("OPENGUARD_P2_PUBLIC_SOURCE_ROOT", "OPENGUARD_P2_PUBLIC_SOURCE_PROFILE_SHA256",
                "OPENGUARD_P2_AUTOMATIC_SOURCE_ROOT", "OPENGUARD_P2_AUTOMATIC_SOURCE_PROFILE_SHA256"):
        monkeypatch.delenv(key, raising=False)
    profile = FixedGitSnapshot(
        bundle_path=TASK / "runtime/fixed-source/http-server.bundle",
        source_url="https://github.com/http-party/http-server",
        revision="0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b",
        bundle_sha256="b4d28764503ce135702d948878d8604495fd0addf38c7a070892e93d038c714b",
        bundle_size=462976, captured_at="2026-10-13T09:28:06.962574+00:00",
        capture_receipt_sha256="1b8cf6cdcb85778448b37eb838d395081a15bf378fe3a5ab37445d7d233d0045")
    apps, roots = [], []
    def factory(data_root):
        roots.append(data_root)
        app = create_default_app(data_dir=data_root,
            git_ingestion_factory=lambda workspace: GitIngestionService(workspace, snapshot=profile))
        apps.append(app)
        return app
    arguments = {"max_accounts": max_accounts, "registration_attempts": registration_attempts}
    if clock is not None:
        arguments["clock"] = clock
    store = AccountStore(root, **arguments)
    app = LocalAccountGateway(root=root, origins=(ORIGIN,), cookie_name=COOKIE,
                              app_factory=factory, frontend=frontend, store=store)
    app.observed_apps, app.observed_roots = apps, roots
    return app


def request(client, method, path, *, csrf=None, body=None, **kwargs):
    headers = {"Origin": ORIGIN}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    headers.update(kwargs.pop("headers", {}))
    if body is not None:
        kwargs["json"] = body
    response = client.request(method, path, headers=headers, **kwargs)
    identifier = uuid.uuid4().hex
    auth = path.startswith("/api/v1/auth/")
    row = {"id": identifier, "method": method, "url": path,
           "status": response.status_code, "data_scope": "SYNTHETIC_TEST_ONLY",
           "headers": "NOT_RETAINED", "auth_wire": "NOT_RETAINED" if auth else None}
    if not auth:
        raw_request = response.request.content
        raw_response = response.content
        for name, raw in (("request", raw_request), ("response", raw_response)):
            file = OUT / (identifier + "." + name + ".raw")
            file.write_bytes(raw)
            row[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "file": file.name}
    HTTP_LEDGER.append(row)
    (OUT / "RAW_HTTP_INDEX.json").write_text(json.dumps(HTTP_LEDGER, indent=2) + "\n")
    if path.startswith("/api/"):
        ensure(response.headers.get("cache-control") == "no-store", "API response must disable caching")
    return response


def session(client):
    response = request(client, "GET", "/api/v1/auth/session")
    ensure(response.status_code == 200, "Session endpoint failed")
    return response.json()


def register(client, username="test_owner"):
    initial = session(client)
    response = request(client, "POST", "/api/v1/auth/register", csrf=initial["csrf_token"],
                       body={"username": username, "password": PASSWORD})
    ensure(response.status_code == 201, "Registration did not succeed")
    return response.json()


def test_anonymous_session_stable_csrf_host_origin_and_no_business_access(tmp_path, monkeypatch):
    app = gateway(tmp_path / "accounts", monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        first, second = session(client), session(client)
        ensure(first["user"] is None and second["user"] is None, "Anonymous session must not own an account")
        ensure(first["csrf_token"] == second["csrf_token"], "CSRF must remain stable across session GETs")
        assert request(client, "GET", "/").status_code == 200
        assert request(client, "GET", "/api/v1/scans").status_code == 401
        assert request(client, "GET", "/api/v1/auth/session", headers={"Host": "evil.example"}).status_code == 403
        assert request(client, "POST", "/api/v1/auth/register", body={"username": "valid_name", "password": PASSWORD}).status_code == 403
        assert request(client, "POST", "/api/v1/auth/register", csrf=first["csrf_token"],
                       headers={"Origin": "https://evil.example"}, body={"username": "valid_name", "password": PASSWORD}).status_code == 403
        assert request(client, "POST", "/api/v1/auth/register", csrf="0" * 64,
                       body={"username": "valid_name", "password": PASSWORD}).status_code == 403
        assert request(client, "GET", "/api/v1/auth/logout").status_code == 405
        ensure(session(client)["csrf_token"] == first["csrf_token"], "GET logout must have no side effects")
        assert app.observed_apps == []


@pytest.mark.parametrize("body", [
    {"username": "../escape", "password": PASSWORD},
    {"username": "valid_name", "password": "x" * 14},
    {"username": "valid_name", "password": "x" * 129},
    {"username": "valid_name", "password": True},
    {"username": "valid_name", "password": PASSWORD, "role": "admin"},
])
def test_registration_rejects_invalid_credentials_without_creating_account(tmp_path, monkeypatch, body):
    app = gateway(tmp_path / "accounts", monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        current = session(client)
        response = request(client, "POST", "/api/v1/auth/register", csrf=current["csrf_token"], body=body)
        assert response.status_code == 422
    with sqlite3.connect(app.store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_bounded_json_and_duplicate_headers(tmp_path, monkeypatch):
    app = gateway(tmp_path / "accounts", monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        token = session(client)["csrf_token"]
        assert request(client, "POST", "/api/v1/auth/register", csrf=token,
                       content=b"x" * 4097, headers={"Content-Type": "application/json"}).status_code == 413
        assert request(client, "POST", "/api/v1/auth/register", csrf=token,
                       content=b'{"username":"first","username":"second","password":"valid synthetic phrase"}',
                       headers={"Content-Type": "application/json"}).status_code == 400
        assert request(client, "POST", "/api/v1/auth/register", csrf=token,
                       content=b"{}", headers={"Content-Type": "text/plain"}).status_code == 415
        response = client.get("/api/v1/auth/session", headers=[("host", "127.0.0.1:48123"), ("host", "evil.example")])
        assert response.status_code == 400


def test_cookie_password_storage_login_logout_and_expiry(tmp_path, monkeypatch):
    now = [1_000_000.0]
    app = gateway(tmp_path / "accounts", monkeypatch, clock=lambda: now[0])
    with TestClient(app, base_url=ORIGIN) as client:
        anon = session(client)
        old_cookie = client.cookies.get(COOKIE)
        response = request(client, "POST", "/api/v1/auth/register", csrf=anon["csrf_token"],
                           body={"username": "Case_Name", "password": PASSWORD})
        ensure(response.status_code == 201, "Registration failed")
        current = response.json()
        cookie = client.cookies.get(COOKIE)
        ensure(old_cookie != cookie, "Login must rotate the anonymous cookie")
        ensure(app.store.current(old_cookie) is None, "Anonymous cookie must be revoked")
        flags = response.headers["set-cookie"].lower()
        ensure("httponly" in flags and "samesite=strict" in flags and "path=/" in flags, "Required cookie flags missing")
        ensure("secure" not in flags, "This fixture is explicitly HTTP loopback-only")
        with sqlite3.connect(app.store.path) as db:
            row = db.execute("SELECT salt,password_hash FROM users").fetchone()
            ensure(len(row[0]) == 32 and len(row[1]) == 32, "Salt/hash size incorrect")
            ensure(db.execute("SELECT token_hash FROM sessions").fetchone()[0] == hashlib.sha256(cookie.encode()).hexdigest(), "Only token hashes should be stored")
        disk = app.store.path.read_bytes()
        ensure(PASSWORD.encode() not in disk and cookie.encode() not in disk, "Plaintext credential found in account database")
        assert request(client, "POST", "/api/v1/scans", csrf=anon["csrf_token"], body={}).status_code == 403
        assert request(client, "GET", "/api/v1/scans").status_code == 200
        assert request(client, "POST", "/api/v1/auth/logout", csrf=current["csrf_token"], body={}).status_code == 200
        ensure(app.store.current(cookie) is None, "Logout must revoke the previous cookie server-side")
        assert request(client, "GET", "/api/v1/scans").status_code == 401
        logged_out = session(client)
        response = request(client, "POST", "/api/v1/auth/login", csrf=logged_out["csrf_token"],
                           body={"username": "case_name", "password": PASSWORD})
        ensure(response.status_code == 200 and response.json()["user"] == current["user"], "Case-insensitive username login failed")
        now[0] += SESSION_SECONDS + 1
        assert request(client, "GET", "/api/v1/scans").status_code == 401
        ensure(session(client)["user"] is None, "Expired session must not remain authenticated")
    ensure(all(item.state.scan_api_service._registry._closed for item in app.observed_apps), "Child registry lifespan must close")


def test_failed_login_generic_error_throttle_and_account_limit(tmp_path, monkeypatch):
    app = gateway(tmp_path / "accounts", monkeypatch, max_accounts=1)
    with TestClient(app, base_url=ORIGIN) as client:
        user = register(client)
        unavailable = request(client, "POST", "/api/v1/auth/register", csrf=user["csrf_token"],
                              body={"username": "another_owner", "password": PASSWORD})
        assert unavailable.status_code == 409
        assert request(client, "POST", "/api/v1/auth/logout", csrf=user["csrf_token"], body={}).status_code == 200
        current = session(client)
        failed = []
        for name in ("test_owner", "unknown_owner"):
            response = request(client, "POST", "/api/v1/auth/login", csrf=current["csrf_token"],
                               body={"username": name, "password": "Incorrect synthetic phrase!"})
            assert response.status_code == 401
            failed.append(response.json())
        ensure(failed[0] == failed[1], "Login error must not disclose whether username exists")
        for _ in range(4):
            response = request(client, "POST", "/api/v1/auth/login", csrf=current["csrf_token"],
                               body={"username": "test_owner", "password": "Incorrect synthetic phrase!"})
            assert response.status_code == 401
        assert request(client, "POST", "/api/v1/auth/login", csrf=current["csrf_token"],
                       body={"username": "test_owner", "password": PASSWORD}).status_code == 429


def test_duplicate_registration_consumes_pre_hash_attempt_budget(tmp_path, monkeypatch):
    app = gateway(tmp_path / "accounts", monkeypatch, registration_attempts=2)
    with TestClient(app, base_url=ORIGIN) as client:
        current = register(client, "budget_user")
        duplicate = {"username": "budget_user", "password": PASSWORD}
        assert request(client, "POST", "/api/v1/auth/register", csrf=current["csrf_token"], body=duplicate).status_code == 409
        assert request(client, "POST", "/api/v1/auth/register", csrf=current["csrf_token"], body=duplicate).status_code == 429
    with sqlite3.connect(app.store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert db.execute("SELECT attempts FROM rate_limits WHERE bucket LIKE 'register:%'").fetchone()[0] == 2


def test_username_uniqueness_and_session_survives_gateway_restart(tmp_path, monkeypatch):
    root = tmp_path / "accounts"
    app = gateway(root, monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        saved = register(client, "Persist_User")
        cookie = client.cookies.get(COOKIE)
        duplicate = request(client, "POST", "/api/v1/auth/register", csrf=saved["csrf_token"],
                            body={"username": "persist_user", "password": PASSWORD})
        assert duplicate.status_code == 409
    second = gateway(root, monkeypatch)
    with TestClient(second, base_url=ORIGIN) as client:
        client.cookies.set(COOKIE, cookie, domain="127.0.0.1", path="/")
        recovered = session(client)
        ensure(recovered == saved, "Persistent session and CSRF should survive service restart")
        assert request(client, "GET", "/api/v1/scans").json()["items"] == []


def test_real_default_app_scan_material_and_cross_account_all_object_reads(tmp_path, monkeypatch):
    app = gateway(tmp_path / "accounts", monkeypatch)
    original_env = os.environ.get("OPENGUARD_DATA_DIR")
    with TestClient(app, base_url=ORIGIN) as client:
        account_a = register(client, "scan_owner_a")
        csrf_a = account_a["csrf_token"]
        cookie_a = client.cookies.get(COOKIE)
        assert request(client, "GET", "/api/v1/scans").json()["items"] == []
        usage = {"preset": "open_source", "commercial": False, "modified": True, "distributed": False,
                 "network_service": True, "training": False, "redistributed_assets": False, "source_disclosure": True,
                 "declared_at": "2026-10-22T12:00:00+00:00"}
        response = request(client, "POST", "/api/v1/scans", csrf=csrf_a,
                           body={"source_type": "git", "source": "https://github.com/http-party/http-server",
                                 "idempotency_key": "test_account_scan", "usage": usage})
        assert response.status_code == 202
        scan_id = response.json()["scan_id"]
        scan_path = "/api/v1/scans/" + scan_id
        assert request(client, "GET", scan_path).json()["status"] == "completed"
        assessments = request(client, "GET", scan_path + "/assessments").json()["items"]
        assert len(assessments) == 1
        assessment_id = assessments[0]["id"]
        base = scan_path + "/assessments/" + assessment_id
        binding = request(client, "GET", base + "/p2/binding").json()
        initial = request(client, "POST", base + "/p2/results", csrf=csrf_a,
                          body={"binding": binding, "expected_revision": 0, "parent_result_id": None,
                                "idempotency_key": "account_result_initial"})
        assert initial.status_code == 201
        r1 = initial.json()["result"]
        result1 = base + "/p2/results/" + r1["result_id"] + "?assessment_version=1"
        summary1 = base + "/p2/results/" + r1["result_id"] + "/summary?assessment_version=1"
        old_bytes = request(client, "GET", result1).content
        old_summary = request(client, "GET", summary1).content
        resources = request(client, "GET", scan_path + "/resources").json()["items"]
        component = next(item["resource"] for item in resources if item["resource"]["name"] == "http-server")
        target = next(row for row in r1["resources"] if row["subject"]["resource_id"] == component["id"])
        license_bytes = (TASK / "delivery/recording-materials/LICENSE.txt").read_bytes()
        assert len(license_bytes) == 1124
        assert hashlib.sha256(license_bytes).hexdigest() == "accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6"
        payload = {"binding": binding, "expected_revision": 1, "parent_result_id": r1["result_id"],
                   "idempotency_key": "account_license_material", "subject": target["subject"],
                   "evidence_ids": target["evidence_ids"], "filename": "LICENSE",
                   "content_base64": base64.b64encode(license_bytes).decode(),
                   "source_sha256": hashlib.sha256(license_bytes).hexdigest(),
                   "source_description": "SYNTHETIC_TEST_ONLY usage; real Git root LICENSE at fixed source commit, not npm release profile.",
                   "completeness": "FULL_TEXT_CLAIMED"}
        material = request(client, "POST", base + "/p2/materials", csrf=csrf_a, body=payload)
        assert material.status_code == 201
        receipt = material.json()
        assert receipt["material"]["source_level"] == "user_supplied_unverified"
        assert receipt["material"]["verification_state"] == "pending"
        r2 = receipt["result"]
        assert r2["revision"] == 2
        assert r2["binding"] == r1["binding"]
        assert request(client, "GET", base).json()["version"] == 1
        assert request(client, "GET", result1).content == old_bytes
        assert request(client, "GET", summary1).content == old_summary
        untouched = [row for row in r2["resources"] if row["subject"] != target["subject"]]
        assert all(row == next(old for old in r1["resources"] if old["subject"] == row["subject"]) for row in untouched)
        assert request(client, "POST", base + "/p2/materials", csrf=csrf_a, body=payload).json() == receipt
        conflict = dict(payload, idempotency_key="account_stale_cas_material")
        assert request(client, "POST", base + "/p2/materials", csrf=csrf_a, body=conflict).status_code == 409
        archive = request(client, "POST", base + "/report-v2", csrf=csrf_a, body={"idempotency_key": "account_archive_v1"})
        assert archive.status_code == 200
        snapshot_id = archive.json()["snapshot_id"]
        r2_path = base + "/p2/results/" + r2["result_id"]
        owned_reads = [scan_path, scan_path + "/resources", scan_path + "/graph", scan_path + "/progress-events",
            scan_path + "/assessments", base, base + "/p2/binding", result1, summary1,
            r2_path + "?assessment_version=1", r2_path + "/summary?assessment_version=1",
            base + "/p2/results?assessment_version=1",
            base + "/p2/materials/" + receipt["material"]["material_id"] + "?assessment_version=1",
            base + "/report?format=json", scan_path + "/report?format=json&download=true",
            base + "/report-v2/" + snapshot_id + "?format=json",
            base + "/report-v2/" + snapshot_id + "?format=html"]
        for path in owned_reads:
            assert request(client, "GET", path).status_code == 200, path
        assert request(client, "POST", "/api/v1/auth/logout", csrf=csrf_a, body={}).status_code == 200
        for path in owned_reads:
            assert request(client, "GET", path).status_code == 401, path
        account_b = register(client, "scan_owner_b")
        csrf_b = account_b["csrf_token"]
        assert request(client, "GET", "/api/v1/scans").json()["items"] == []
        for path in owned_reads:
            assert request(client, "GET", path).status_code == 404, path
        assert request(client, "POST", base + "/p2/materials", csrf=csrf_b, body=payload).status_code == 404
        # An old A tab may resume with its original CSRF after the browser has
        # switched to B's cookie. Deny it before selecting any tenant or write.
        assert request(client, "POST", base + "/p2/materials", csrf=csrf_a, body=payload).status_code == 403
        assert request(client, "GET", "/api/v1/scans").json()["items"] == []
        assert request(client, "POST", scan_path + "/chat", csrf=csrf_b, body={}).status_code == 403
        assert len(app.observed_roots) == 2 and app.observed_roots[0] != app.observed_roots[1]
        ensure(app.store.current(cookie_a) is None, "Logged-out account A cookie must remain revoked")
        assert os.environ.get("OPENGUARD_DATA_DIR") == original_env
        (OUT / "OWNERSHIP_AND_REAL_FLOW.json").write_text(json.dumps({
            "data_scope": "SYNTHETIC_TEST_ONLY", "input": "FIXED_LOCAL_GIT_BUNDLE_REPARSED",
            "scan_id": scan_id, "assessment_id": assessment_id, "assessment_version": 1,
            "result_r1": r1["result_id"], "result_r2": r2["result_id"],
            "material_id": receipt["material"]["material_id"], "summary_r2": r2["companion_summary_id"],
            "material_status": "user_supplied_unverified/pending", "cross_account_read_paths": owned_reads,
            "cross_account_read_status": 404, "anonymous_read_status": 401,
            "old_result_and_summary_unchanged": True, "peer_rows_unchanged": len(untouched),
            "model_calls": 0, "official_npm_source": "NOT_CONFIGURED", "M1": "STOP"
        }, indent=2) + "\n")
    ensure(all(item.state.scan_api_service._registry._closed for item in app.observed_apps), "All tenant registries must close with gateway lifespan")
