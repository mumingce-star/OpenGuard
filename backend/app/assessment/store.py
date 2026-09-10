"""Private, bounded append-only assessment snapshots and pre-rendered reports.

The separate assessment.db never changes scans.db. Reads use mode=ro and do not
initialize storage. Budget failure refuses new data and keeps old records.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import html
import os
import shutil
import sqlite3
import stat
from pathlib import Path
from urllib.parse import quote
from app.domain.models import ScanRun
from .engine import canonical_bytes, facts_digest
from .models import Assessment


class AssessmentStoreError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def render_assessment_html(assessment: Assessment, run: ScanRun | None = None) -> bytes:
    """Escape all untrusted text; no external scripts, images or model HTML."""
    esc = lambda value: html.escape(str(value), quote=True)
    cards = "".join(f'<section><h2>{esc(d.title)}：{esc(d.conclusion)}</h2>'
        + '<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in [*d.conditions, *d.restrictions]) + '</ul>'
        + (f'<p>待核验 {len(d.unknowns)} 项，见下方完整依据。</p>' if d.unknowns else '') + '</section>' for d in assessment.dimensions)
    unique_obligations = list(dict.fromkeys(o.requirement for o in assessment.obligations))
    obligations = ''.join(f'<li>{esc(x)}（履行状态：待核实）</li>' for x in unique_obligations[:5])
    if len(unique_obligations) > 5:
        obligations += f'<li>另有 {len(unique_obligations)-5} 类义务，完整关联保留在附录。</li>'
    presets = {'personal':'个人学习','internal':'企业内部使用','open_source':'修改后开源发布','closed_source':'闭源产品交付','service':'对外提供服务','unknown':'用途未确定'}
    statuses = {'completed':'扫描完成','partial':'部分扫描完成','failed':'扫描失败','cancelled':'已取消'}
    ai_states = {'succeeded':'已生成本地 AI 说明','fallback':'AI说明暂不可用，保留确定性评估','failed':'AI说明失败','not_requested':'未启用 AI 说明'}
    actions = list(dict.fromkeys(x for r in assessment.resource_evaluations for x in r.next_steps))
    action_html = '<h2>优先核对材料</h2><ol>' + ''.join(f'<li>{esc(x)}</li>' for x in actions[:5]) + '</ol>'
    if len(actions)>5: action_html += f'<p>另有 {len(actions)-5} 条具体核验步骤，按资源保留在完整依据中。</p>'
    appendix = {"assessment": assessment.model_dump(mode="json")}
    if run is not None:
        appendix["scan_run"] = run.model_dump(mode="json")
    raw = canonical_bytes(appendix).decode()
    links = ''.join(f'<a href="/api/v1/scans/{quote(assessment.scan_id, safe="")}/report?format={fmt}&amp;download=true">原始 {name} 报告</a> ' for fmt, name in (("html", "HTML"), ("json", "JSON"), ("csv", "CSV"), ("resource_inventory", "资源清单")))
    content = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>OpenGuard 项目评估</title><style>body{max-width:1000px;margin:32px auto;padding:16px;font:16px/1.6 sans-serif}section{border:1px solid #ccc;padding:12px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}h2{font-size:19px}</style>'
        f'<h1>{esc(assessment.project_name)} · 项目评估</h1><p>正式评估版本 {assessment.version}</p>'
        f'<p>目标版本：{esc(assessment.revision or assessment.input_hash)} · 用途：{esc(presets[assessment.usage.preset])} · {esc(assessment.generated_at.isoformat())}</p>'
        f'<p>真实扫描状态：{esc(statuses.get(assessment.scan_status,assessment.scan_status))}</p><p>{esc(assessment.summary)}</p>'
        f'<p>AI说明状态：{esc(ai_states[assessment.ai_status])}</p><p>{esc(assessment.ai_summary or "尚无有效 AI 总评；以上为确定性评估。")}</p>'
        + cards + '<h2>必须履行的义务</h2><ul>' + (obligations or '<li>当前没有可确认的完整义务清单；不代表没有义务。</li>') + '</ul>' + action_html
        + '<p>这是证据与用途约束下的合规整理，不是法律保证。义务存在不表示已经违反或已经履行。</p>'
        + links + '<details><summary>完整资源、发现、证据与所有未核验事项</summary><pre>' + esc(raw) + '</pre></details></html>')
    return content.encode('utf-8')


class AssessmentStore:
    def __init__(self, path: str | Path, *, max_record_bytes: int = 8 * 1024 * 1024,
                 max_database_bytes: int = 128 * 1024 * 1024, min_free_bytes: int = 512 * 1024 * 1024):
        self.path = Path(path).absolute()
        self.max_record_bytes = max_record_bytes
        self.max_database_bytes = max_database_bytes
        self.min_free_bytes = min_free_bytes
        if min(max_record_bytes, max_database_bytes) <= 0 or min_free_bytes < 0:
            raise ValueError("invalid assessment storage budget")

    def _guard(self, *, create: bool = False) -> bool:
        if self.path.name != "assessment.db":
            raise AssessmentStoreError("assessment_store_invalid_path")
        parent = self.path.parent
        if create:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not parent.exists():
            return False
        if parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
            raise AssessmentStoreError("assessment_store_insecure_directory")
        if self.path.is_symlink():
            raise AssessmentStoreError("assessment_store_insecure_file")
        if not self.path.exists():
            return False
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise AssessmentStoreError("assessment_store_insecure_file")
        return True

    def _connect(self, *, readonly: bool = False):
        if readonly:
            if not self._guard():
                return None
            connection = sqlite3.connect(f"file:{quote(str(self.path), safe='/')}?mode=ro", uri=True, timeout=1)
            connection.execute("PRAGMA query_only=ON")
        else:
            if not self._guard():
                raise AssessmentStoreError("assessment_store_unavailable")
            connection = sqlite3.connect(str(self.path), timeout=1)
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            connection.execute(f"PRAGMA max_page_count={max(1, self.max_database_bytes // page_size)}")
        return connection

    def initialize(self) -> None:
        existed = self._guard(create=True)
        if not existed:
            if shutil.disk_usage(self.path.parent).free < self.min_free_bytes + 32768 or self.max_database_bytes < 32768:
                raise AssessmentStoreError("assessment_storage_capacity_exceeded")
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                os.close(fd)
            except FileExistsError:
                self._guard()
        try:
            with closing(self._connect()) as db, db:
                db.executescript('''
                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY, scan_id TEXT NOT NULL, version INTEGER NOT NULL,
                    cache_key TEXT NOT NULL, payload BLOB NOT NULL, html BLOB NOT NULL,
                    report_json BLOB NOT NULL, html_hash TEXT NOT NULL, json_hash TEXT NOT NULL,
                    UNIQUE(scan_id, version), UNIQUE(scan_id, cache_key));
                CREATE TABLE IF NOT EXISTS assessment_requests (
                    scan_id TEXT NOT NULL, request_key TEXT NOT NULL, cache_key TEXT NOT NULL,
                    assessment_id TEXT NOT NULL, PRIMARY KEY(scan_id, request_key));
                ''')
        except sqlite3.Error as error:
            raise AssessmentStoreError("assessment_store_unavailable") from error

    def _read(self, query: str, values: tuple) -> list:
        try:
            db = self._connect(readonly=True)
            if db is None:
                return []
            try:
                return db.execute(query, values).fetchall()
            finally:
                db.close()
        except sqlite3.Error as error:
            raise AssessmentStoreError("assessment_store_unavailable") from error

    def get(self, scan_id: str, assessment_id: str) -> Assessment | None:
        rows = self._read("SELECT payload FROM assessments WHERE scan_id=? AND id=?", (scan_id, assessment_id))
        return Assessment.model_validate_json(rows[0][0]) if rows else None

    def latest(self, scan_id: str) -> Assessment | None:
        rows = self.list(scan_id, limit=1)
        return rows[0] if rows else None

    def list(self, scan_id: str, *, limit: int = 20, offset: int = 0) -> list[Assessment]:
        if not 1 <= limit <= 100 or offset < 0:
            raise AssessmentStoreError("assessment_store_invalid_argument")
        return [Assessment.model_validate_json(row[0]) for row in self._read(
            "SELECT payload FROM assessments WHERE scan_id=? ORDER BY version DESC LIMIT ? OFFSET ?", (scan_id, limit, offset))]

    def report(self, scan_id: str, assessment_id: str, format: str = "html") -> bytes | None:
        if format not in {"html", "json"}:
            raise AssessmentStoreError("assessment_store_invalid_argument")
        column, hash_column = ("html", "html_hash") if format == "html" else ("report_json", "json_hash")
        rows = self._read(f"SELECT {column},{hash_column} FROM assessments WHERE scan_id=? AND id=?", (scan_id, assessment_id))
        if not rows:
            return None
        payload, expected = rows[0]
        if hashlib.sha256(payload).hexdigest() != expected:
            raise AssessmentStoreError("assessment_store_integrity_error")
        return payload

    def create(self, assessment: Assessment, *, idempotency_key: str, run: ScanRun | None = None) -> Assessment:
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 200:
            raise AssessmentStoreError("assessment_store_invalid_argument")
        if run is not None and (run.id != assessment.scan_id or facts_digest(run) != assessment.facts_hash):
            raise AssessmentStoreError("assessment_snapshot_mismatch")
        self.initialize()
        try:
            with closing(self._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                request = db.execute("SELECT cache_key,assessment_id FROM assessment_requests WHERE scan_id=? AND request_key=?", (assessment.scan_id, idempotency_key)).fetchone()
                if request and request[0] != assessment.cache_key:
                    raise AssessmentStoreError("assessment_idempotency_conflict")
                cached = db.execute("SELECT payload FROM assessments WHERE scan_id=? AND cache_key=?", (assessment.scan_id, assessment.cache_key)).fetchone()
                if cached:
                    saved = Assessment.model_validate_json(cached[0])
                else:
                    next_version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM assessments WHERE scan_id=?", (assessment.scan_id,)).fetchone()[0]
                    if assessment.version != next_version:
                        raise AssessmentStoreError("assessment_version_conflict")
                    payload = assessment.model_dump_json().encode()
                    document = {"assessment": assessment.model_dump(mode="json")}
                    if run is not None:
                        document["scan_run"] = run.model_dump(mode="json")
                    report_json = canonical_bytes(document)
                    report_html = render_assessment_html(assessment, run)
                    size = len(payload) + len(report_json) + len(report_html)
                    if size > self.max_record_bytes:
                        raise AssessmentStoreError("assessment_record_capacity_exceeded")
                    pages = (db.execute("PRAGMA page_count").fetchone()[0] - db.execute("PRAGMA freelist_count").fetchone()[0])
                    page_size = db.execute("PRAGMA page_size").fetchone()[0]
                    if pages * page_size + size + 8192 > self.max_database_bytes or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + size + 8192:
                        raise AssessmentStoreError("assessment_storage_capacity_exceeded")
                    db.execute("INSERT INTO assessments VALUES (?,?,?,?,?,?,?,?,?)", (assessment.id, assessment.scan_id, assessment.version, assessment.cache_key,
                        payload, report_html, report_json, hashlib.sha256(report_html).hexdigest(), hashlib.sha256(report_json).hexdigest()))
                    saved = assessment
                # Idempotency aliases also consume bounded storage, never unbounded rows.
                if not request:
                    page_size = db.execute("PRAGMA page_size").fetchone()[0]
                    if (db.execute("PRAGMA page_count").fetchone()[0] - db.execute("PRAGMA freelist_count").fetchone()[0]) * page_size + 8192 > self.max_database_bytes or shutil.disk_usage(self.path.parent).free < self.min_free_bytes + 8192:
                        raise AssessmentStoreError("assessment_storage_capacity_exceeded")
                    db.execute("INSERT INTO assessment_requests VALUES (?,?,?,?)", (assessment.scan_id, idempotency_key, assessment.cache_key, saved.id))
                return saved
        except sqlite3.Error as error:
            raise AssessmentStoreError("assessment_store_unavailable") from error
