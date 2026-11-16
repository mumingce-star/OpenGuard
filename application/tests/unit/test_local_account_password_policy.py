"""SYNTHETIC_TEST_ONLY account policy through the real ASGI gateway.

Only fresh pytest TASK databases are used. Auth request bodies, credentials,
cookies and CSRF tokens are never captured in logs or parameter identifiers.
"""
import hashlib
import sqlite3
import uuid

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from app.local_accounts import (
    AccountStore, LocalAccountGateway, SCRYPT_N, SCRYPT_R, SCRYPT_P,
    SCRYPT_MAXMEM,
)


ORIGIN = "http://127.0.0.1:48123"
COOKIE = "og_session_1023456789ab"


def ensure(condition, message):
    # Avoid assertion rewriting of credential-bearing request values.
    if not condition:
        raise AssertionError(message)


async def frontend(scope, receive, send):
    await JSONResponse({"scope": "SYNTHETIC_TEST_ONLY"})(scope, receive, send)


def gateway(root):
    def no_business_app(_):
        raise AssertionError("Password policy test must not create a business app")
    store = AccountStore(root)
    return LocalAccountGateway(
        root=root, origins=(ORIGIN,), cookie_name=COOKIE,
        app_factory=no_business_app, frontend=frontend, store=store,
    )


def session(client):
    response = client.get("/api/v1/auth/session", headers={"Origin": ORIGIN})
    ensure(response.status_code == 200, "Session GET failed")
    return response.json()


def post(client, action, current, username, password):
    response = client.post(
        "/api/v1/auth/" + action,
        headers={"Origin": ORIGIN, "X-CSRF-Token": current["csrf_token"]},
        json={"username": username, "password": password},
    )
    ensure(response.headers.get("cache-control") == "no-store", "Auth must be uncached")
    return response


@pytest.mark.parametrize("password,expected", [
    pytest.param("Alpha123", 201, id="eight-codepoints-accepted"),
    pytest.param("A1" + "x" * 22, 201, id="twenty-four-codepoints-accepted"),
    pytest.param("Alpha12", 422, id="seven-codepoints-rejected"),
    pytest.param("A1" + "x" * 23, 422, id="twenty-five-codepoints-rejected"),
    pytest.param("AlphaOnlyPassword", 422, id="letters-only-rejected"),
    pytest.param("1234567890123456", 422, id="numbers-only-rejected"),
    pytest.param("A1!@#-$%", 201, id="additional-symbols-accepted"),
    pytest.param("A1" + "🔐" * 6, 201, id="unicode-eight-codepoints-accepted"),
    pytest.param("A1" + "🔐" * 22, 201, id="unicode-twenty-four-codepoints-accepted"),
    pytest.param("A1" + "🔐" * 23, 422, id="unicode-twenty-five-codepoints-rejected"),
    pytest.param("字" * 7 + "1", 422, id="non-ascii-letter-does-not-satisfy-letter"),
    pytest.param("A" + "１" * 7, 422, id="non-ascii-digit-does-not-satisfy-digit"),
    pytest.param(True, 422, id="boolean-rejected"),
], ids=None)
def test_registration_password_policy_through_asgi(tmp_path, password, expected):
    app = gateway(tmp_path / "synthetic-accounts")
    with TestClient(app, base_url=ORIGIN) as client:
        response = post(client, "register", session(client), "policy_owner", password)
        ensure(response.status_code == expected, "Registration status does not match policy")
        current = session(client)
        ensure((current["user"] is not None) == (expected == 201), "Registration authentication state incorrect")
    with sqlite3.connect(app.store.path) as db:
        count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        ensure(count == (1 if expected == 201 else 0), "Rejected registration created an account")


@pytest.mark.parametrize("legacy_password", [
    pytest.param("Legacy synthetic phrase with spaces 2026!", id="legacy-over-twenty-four-with-spaces"),
    pytest.param("LegacyLettersOnlyPassword", id="legacy-letters-only"),
    pytest.param("L" * 128, id="legacy-one-hundred-twenty-eight"),
])
def test_legacy_password_login_preserves_original_hash(tmp_path, legacy_password):
    app = gateway(tmp_path / "synthetic-legacy-accounts")
    # Reproduce the already-used algorithm, not the new registration API.
    # This models an existing database row without changing its password.
    salt = bytes(range(32))
    original_hash = hashlib.scrypt(
        legacy_password.encode("utf-8"), salt=salt, n=SCRYPT_N,
        r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM, dklen=32,
    )
    account_id = "usr_" + uuid.uuid4().hex
    with sqlite3.connect(app.store.path) as db:
        db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (
            account_id, "legacy_owner", "Legacy_Owner", salt, original_hash, app.store.clock(),
        ))
    with TestClient(app, base_url=ORIGIN) as client:
        response = post(client, "login", session(client), "legacy_owner", legacy_password)
        ensure(response.status_code == 200, "Existing legacy credential must remain usable")
        current = session(client)
        ensure(current["user"] is not None and current["user"]["id"] == account_id,
               "Legacy login selected the wrong account")
    with sqlite3.connect(app.store.path) as db:
        row = db.execute("SELECT salt,password_hash FROM users WHERE id=?", (account_id,)).fetchone()
        ensure(row == (salt, original_hash), "Login must not rewrite the existing hash or salt")
