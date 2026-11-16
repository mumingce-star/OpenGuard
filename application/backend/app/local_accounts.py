"""Loopback-only accounts and per-account composition of the existing API.

This does not change P0/P2 public objects or claim to be an internet deployment.
Passwords and bearer cookies must never enter request/response capture logs.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Any, Callable
from urllib.parse import urlsplit
import uuid

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse


USERNAME = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
ACCOUNT_ID = re.compile(r"^usr_[0-9a-f]{32}$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
COOKIE_NAME = re.compile(r"^og_session_[0-9a-f]{12}$")
SCRYPT_N = 1 << 17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 256 * 1024 * 1024
SESSION_SECONDS = 12 * 60 * 60
ANONYMOUS_SECONDS = 30 * 60
AUTH_BODY_MAX_BYTES = 4096


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(code)
        self.status, self.code, self.message = status, code, message


def _private_dir(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or value.st_uid != os.geteuid() or value.st_mode & 0o077:
        raise RuntimeError("Account storage directory must be private")
    return path


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N,
                          r=SCRYPT_R, p=SCRYPT_P, maxmem=SCRYPT_MAXMEM, dklen=32)


@dataclass(frozen=True)
class Session:
    token: str = field(repr=False)
    user: dict[str, str] | None
    expires_at: float


class AccountStore:
    """Short-lived SQLite connections; sessions persist, raw tokens do not."""
    def __init__(self, root: Path, *, max_accounts: int = 25, registration_attempts: int = 10,
                 clock: Callable[[], float] = time.time):
        self.root = _private_dir(root)
        self.accounts_root = _private_dir(root / "accounts")
        self.path = root / "accounts.sqlite3"
        self.max_accounts, self.clock = max_accounts, clock
        self.registration_attempts = registration_attempts
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username_key TEXT NOT NULL UNIQUE,
                    username TEXT NOT NULL, salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, account_id TEXT REFERENCES users(id),
                    created_at REAL NOT NULL, expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rate_limits (
                    bucket TEXT PRIMARY KEY, started_at REAL NOT NULL, attempts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL);
            """)
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('csrf_key',?)", (secrets.token_bytes(32),))
            self._csrf_key = bytes(db.execute("SELECT value FROM metadata WHERE key='csrf_key'").fetchone()[0])
        # A missing username still performs the same scrypt operation as a real
        # username. Never log these inputs or the session token.
        self._dummy_salt = secrets.token_bytes(32)

    def _db(self):
        value = self.path.lstat()
        if not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode) or value.st_uid != os.geteuid() or value.st_mode & 0o077:
            raise RuntimeError("Account database must be private")
        db = sqlite3.connect(str(self.path), timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        return _Connection(db)

    def csrf(self, token: str) -> str:
        return hmac.new(self._csrf_key, b"openguard-local-csrf\0" + token.encode("ascii"), hashlib.sha256).hexdigest()

    def current(self, token: str | None) -> Session | None:
        if token is None or not TOKEN.fullmatch(token):
            return None
        with self._db() as db:
            row = db.execute("""SELECT s.expires_at,u.id,u.username FROM sessions s
                               LEFT JOIN users u ON u.id=s.account_id WHERE s.token_hash=?""",
                             (hashlib.sha256(token.encode("ascii")).hexdigest(),)).fetchone()
        if row is None or row[0] <= self.clock():
            return None
        return Session(token, None if row[1] is None else {"id": row[1], "username": row[2]}, row[0])

    def _issue(self, db, user: dict[str, str] | None, old_token: str | None) -> Session:
        now = self.clock()
        db.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
        if old_token:
            old_hash = hashlib.sha256(old_token.encode("ascii")).hexdigest()
            if db.execute("SELECT 1 FROM sessions WHERE token_hash=?", (old_hash,)).fetchone() is None:
                raise AuthError(401, "auth_session_changed", "登录状态已变化，请重新读取登录状态。")
            db.execute("DELETE FROM sessions WHERE token_hash=?", (old_hash,))
        if db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= 2048:
            raise AuthError(429, "auth_capacity", "本机登录会话已达上限，请稍后再试。")
        token = secrets.token_urlsafe(32)
        expires = now + (SESSION_SECONDS if user else ANONYMOUS_SECONDS)
        db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode("ascii")).hexdigest(),
                   user["id"] if user else None, now, expires))
        return Session(token, user, expires)

    def anonymous(self, old_token: str | None = None) -> Session:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._issue(db, None, old_token)

    @staticmethod
    def credentials(body: Any, *, registering: bool = False) -> tuple[str, str]:
        if not isinstance(body, dict) or set(body) != {"username", "password"}:
            raise AuthError(422, "auth_input_invalid", "请填写用户名和密码。")
        username, password = body["username"], body["password"]
        if type(username) is not str or not USERNAME.fullmatch(username):
            raise AuthError(422, "auth_input_invalid", "用户名应为3—32位英文字母、数字、下划线或短横线。")
        # Login verifies the exact existing credential, including older long or
        # letters-only passwords. New registration rules never rewrite hashes.
        if type(password) is not str or not 1 <= len(password) <= 128:
            raise AuthError(422, "auth_input_invalid", "请输入注册时设置的密码。")
        if registering:
            if not 8 <= len(password) <= 24:
                raise AuthError(422, "auth_input_invalid", "密码应为8—24个字符。")
            if re.search(r"[A-Za-z]", password) is None or re.search(r"[0-9]", password) is None:
                raise AuthError(422, "auth_input_invalid", "密码必须同时包含英文字母和数字，可以包含符号。")
        try:
            password.encode("utf-8")
        except UnicodeEncodeError:
            raise AuthError(422, "auth_input_invalid", "密码含无法处理的字符。") from None
        return username, password

    def _rate(self, db, bucket: str, *, maximum: int, seconds: int, increment: bool):
        now = self.clock()
        row = db.execute("SELECT started_at,attempts FROM rate_limits WHERE bucket=?", (bucket,)).fetchone()
        if row and now - row[0] < seconds and row[1] >= maximum:
            raise AuthError(429, "auth_rate_limited", "尝试次数较多，请稍后再试。")
        if increment:
            started, count = (row[0], row[1] + 1) if row and now - row[0] < seconds else (now, 1)
            db.execute("INSERT OR REPLACE INTO rate_limits VALUES (?,?,?)", (bucket, started, count))

    def register(self, body: Any, old_token: str, client: str) -> Session:
        username, password = self.credentials(body, registering=True)
        # A separate committed reservation survives a duplicate-name/capacity
        # rollback and bounds expensive scrypt work before it is dispatched.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._rate(db, "register:" + client, maximum=self.registration_attempts, seconds=60, increment=True)
        salt = secrets.token_bytes(32)
        digest = _password_hash(password, salt)
        account_id = "usr_" + uuid.uuid4().hex
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= self.max_accounts:
                raise AuthError(409, "auth_account_capacity", "本机演示账号已达上限。")
            try:
                db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (account_id, username.lower(), username, salt, digest, self.clock()))
            except sqlite3.IntegrityError:
                raise AuthError(409, "auth_username_unavailable", "这个用户名暂不可用，请换一个。") from None
            return self._issue(db, {"id": account_id, "username": username}, old_token)

    def login(self, body: Any, old_token: str) -> Session:
        username, password = self.credentials(body)
        bucket = "login:" + hashlib.sha256(username.lower().encode("ascii")).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._rate(db, bucket, maximum=5, seconds=300, increment=True)
            row = db.execute("SELECT id,username,salt,password_hash FROM users WHERE username_key=?", (username.lower(),)).fetchone()
        expected = bytes(row[3]) if row else bytes(32)
        computed = _password_hash(password, bytes(row[2]) if row else self._dummy_salt)
        valid = hmac.compare_digest(computed, expected) and row is not None
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if valid:
                db.execute("DELETE FROM rate_limits WHERE bucket=?", (bucket,))
                return self._issue(db, {"id": row[0], "username": row[1]}, old_token)
        raise AuthError(401, "auth_credentials_invalid", "用户名或密码不正确。")

    def account_root(self, account_id: str) -> Path:
        if not ACCOUNT_ID.fullmatch(account_id):
            raise RuntimeError("Invalid internal account identity")
        return _private_dir(self.accounts_root / account_id)


class _Connection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, kind, value, traceback):
        try:
            self.db.rollback() if kind else self.db.commit()
        finally:
            self.db.close()


class LocalAccountGateway:
    """Authenticate before selecting an existing default app and its stores."""
    def __init__(self, *, root: Path, origins: tuple[str, ...], cookie_name: str,
                 app_factory: Callable[[Path], Any], frontend: Any, store: AccountStore | None = None):
        if not COOKIE_NAME.fullmatch(cookie_name):
            raise ValueError("Use a unique TASK-scoped cookie name")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path or parsed.query or parsed.fragment or not parsed.port:
                raise ValueError("Accounts are enabled only on explicit loopback origins")
        if not origins:
            raise ValueError("An exact loopback origin is required")
        self.origins = frozenset(origins)
        self.hosts = frozenset(urlsplit(origin).netloc for origin in origins)
        self.cookie_name = cookie_name
        self.store = store or AccountStore(root)
        self.app_factory, self.frontend = app_factory, frontend
        self.apps: dict[str, Any] = {}
        self._stack: AsyncExitStack | None = None
        self._lock = asyncio.Lock()
        self._password_slots = asyncio.Semaphore(2)
        self.lifecycle = Starlette(lifespan=self._lifespan)

    @asynccontextmanager
    async def _lifespan(self, _):
        async with AsyncExitStack() as stack:
            self._stack = stack
            try:
                yield
            finally:
                self._stack = None
        self.apps.clear()

    async def _tenant(self, user):
        async with self._lock:
            if self._stack is None:
                raise RuntimeError("Account gateway lifespan is not active")
            if user["id"] not in self.apps:
                root = await run_in_threadpool(self.store.account_root, user["id"])
                app = await run_in_threadpool(self.app_factory, root)
                await self._stack.enter_async_context(app.router.lifespan_context(app))
                self.apps[user["id"]] = app
            return self.apps[user["id"]]

    def _reply(self, data, status=200, *, session: Session | None = None):
        response = JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store", "Vary": "Cookie", "X-Content-Type-Options": "nosniff"})
        if session is not None:
            response.set_cookie(self.cookie_name, session.token, max_age=SESSION_SECONDS if session.user else ANONYMOUS_SECONDS,
                                httponly=True, secure=False, samesite="strict", path="/")
        return response

    def _session_reply(self, session, *, rotate=False, status=200):
        return self._reply({"user": session.user, "csrf_token": self.store.csrf(session.token)},
                           status, session=session if rotate else None)

    def _cookie(self, headers) -> str | None:
        raw = headers.get("cookie", "")
        if len(raw) > 8192 or sum(part.strip().startswith(self.cookie_name + "=") for part in raw.split(";")) > 1:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except CookieError:
            return None
        value = cookie.get(self.cookie_name)
        return value.value if value else None

    @staticmethod
    async def _json(receive, headers):
        if headers.get("content-type", "").split(";", 1)[0].lower().strip() != "application/json":
            raise AuthError(415, "auth_json_required", "此操作需要JSON请求。")
        length = headers.get("content-length")
        if length and (not length.isdecimal() or int(length) > AUTH_BODY_MAX_BYTES):
            raise AuthError(413, "auth_body_too_large", "请求过大。")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                raise AuthError(400, "auth_request_incomplete", "请求未完成。")
            body.extend(message.get("body", b""))
            if len(body) > AUTH_BODY_MAX_BYTES:
                raise AuthError(413, "auth_body_too_large", "请求过大。")
            if not message.get("more_body"):
                break
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON field")
                result[key] = value
            return result
        try:
            return json.loads(body, object_pairs_hook=unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        except (ValueError, UnicodeError):
            raise AuthError(400, "auth_json_invalid", "JSON请求无法读取。") from None

    def _csrf(self, headers, session):
        value = headers.get("x-csrf-token", "")
        if session is None or not re.fullmatch(r"[0-9a-f]{64}", value) or not hmac.compare_digest(value, self.store.csrf(session.token)):
            raise AuthError(403, "auth_csrf_rejected", "页面登录状态已变化，请刷新登录状态后重试；操作不会自动重放。")

    async def _auth(self, scope, receive, headers, session):
        path, method = scope["path"], scope["method"]
        if path == "/api/v1/auth/session" and method == "GET":
            if session is None:
                session = await run_in_threadpool(self.store.anonymous)
                return self._session_reply(session, rotate=True)
            return self._session_reply(session)
        if path not in {"/api/v1/auth/register", "/api/v1/auth/login", "/api/v1/auth/logout"}:
            return self._reply({"error": {"code": "auth_not_found", "message": "没有这个账号接口。"}}, 404)
        if method != "POST":
            return self._reply({"error": {"code": "auth_method_not_allowed", "message": "请求方式不支持。"}}, 405)
        self._csrf(headers, session)
        body = await self._json(receive, headers)
        if path.endswith("/register"):
            client = scope.get("client") or ("loopback", 0)
            async with self._password_slots:
                result = await run_in_threadpool(self.store.register, body, session.token, client[0])
            return self._session_reply(result, rotate=True, status=201)
        if path.endswith("/login"):
            async with self._password_slots:
                result = await run_in_threadpool(self.store.login, body, session.token)
            return self._session_reply(result, rotate=True)
        if body != {}:
            raise AuthError(422, "auth_input_invalid", "退出请求不包含额外内容。")
        result = await run_in_threadpool(self.store.anonymous, session.token)
        return self._session_reply(result, rotate=True)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.lifecycle(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 1008})
        downstream_send = send
        if scope["path"] == "/api" or scope["path"].startswith("/api/"):
            async def no_cache(message):
                if message["type"] == "http.response.start":
                    message = dict(message)
                    message["headers"] = [(key, value) for key, value in message.get("headers", [])
                                          if key.lower() != b"cache-control"] + [(b"cache-control", b"no-store")]
                await downstream_send(message)
            send = no_cache
        try:
            headers = {}
            critical = {"host", "origin", "cookie", "x-csrf-token", "content-type", "content-length"}
            for key, value in scope.get("headers", []):
                name = key.decode("latin-1").lower()
                if name in critical and name in headers:
                    raise AuthError(400, "auth_duplicate_header", "请求包含重复的安全字段。")
                headers[name] = value.decode("latin-1")
            if headers.get("host") not in self.hosts:
                raise AuthError(403, "auth_host_rejected", "仅允许当前本机入口。")
            origin = headers.get("origin")
            if origin is not None and origin not in self.origins:
                raise AuthError(403, "auth_origin_rejected", "仅允许当前本机页面。")
            method, path = scope["method"], scope["path"]
            if method not in {"GET", "HEAD", "POST"}:
                raise AuthError(403, "demo_operation_disabled", "演示入口不支持此操作。")
            if method == "POST" and (origin not in self.origins or headers.get("sec-fetch-site") == "cross-site"):
                raise AuthError(403, "auth_origin_rejected", "写入必须来自当前本机页面。")
            if path == "/api" or path.startswith("/api/"):
                session = await run_in_threadpool(self.store.current, self._cookie(headers))
                if path.startswith("/api/v1/auth/"):
                    response = await self._auth(scope, receive, headers, session)
                    return await response(scope, receive, send)
                if session is None or session.user is None:
                    raise AuthError(401, "auth_login_required", "请先登录，再进入个人工作台。")
                if method == "POST":
                    self._csrf(headers, session)
                    permitted = (path == "/api/v1/assistant/conversations"
                                 or re.fullmatch(r"/api/v1/assistant/conversations/chat_[0-9a-f]{32}/messages", path)
                                 or re.fullmatch(r"/api/v1/assistant/conversations/chat_[0-9a-f]{32}/messages/[A-Za-z0-9_-]{8,100}/stop", path)
                                 or path == "/api/v1/scans" or re.fullmatch(r"/api/v1/scans/scn_[^/]+/assessments", path)
                                 or re.fullmatch(r"/api/v1/scans/scn_[^/]+/assessments/asm_[^/]+/p2/(results|materials|ai-analyses|project-chat)", path)
                                 or re.fullmatch(r"/api/v1/scans/scn_[^/]+/assessments/asm_[^/]+/p2/official-sources/(adopt|fetch|analyze)", path)
                                 or re.fullmatch(r"/api/v1/scans/scn_[^/]+/assessments/asm_[^/]+/report-v2", path))
                    if not permitted:
                        raise AuthError(403, "demo_operation_disabled", "该操作未在本机演示入口开放；M1及其他写入保持关闭。")
                app = await self._tenant(session.user)
                account_scope = dict(scope)
                account_scope["state"] = dict(scope.get("state", {}))
                account_scope["state"]["local_account_id"] = session.user["id"]
                return await app(account_scope, receive, send)
            if method == "POST":
                raise AuthError(404, "not_found", "没有这个接口。")
            return await self.frontend(scope, receive, send)
        except AuthError as error:
            response = self._reply({"error": {"code": error.code, "message": error.message}}, error.status)
            return await response(scope, receive, send)


__all__ = ["AccountStore", "AuthError", "LocalAccountGateway", "Session"]
