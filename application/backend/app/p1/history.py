"""Bounded-page registry reads, explicit safe projection, no scan/model/store writes."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit
from pydantic import ValidationError
from app.api.service import ApiError
from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStoreError
from app.domain.models import ScanStatus, SourceType
from app.ingestion.url_policy import parse_public_git_url
from app.persistence import ScanRegistryError
from app.security.errors import IngestionSecurityError
from .models import P1AssessmentRef, P1HistoryPage, P1ScanHistoryItem

SORT = 'created_at:desc,scan_id:asc'


def fail(code, status=400):
    raise ApiError(status_code=status, code=code, message='历史查询参数无效。' if status == 400 else '历史存储暂不可用。', reason=code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def public_source(run):
    """Never search or return stored upload names or local paths."""
    if run.project.source_type == SourceType.GIT:
        try:
            parsed = parse_public_git_url(run.project.source)
            return parsed.canonical, True
        except IngestionSecurityError:
            pass
    return ('ZIP upload' if run.project.source_type == SourceType.ZIP else 'Source withheld'), False


def identity(run, source, searchable):
    result = {'method': 'scan_only', 'key': run.id, 'source_project_id': run.project.id}
    if run.project.source_type == SourceType.GIT and searchable:
        parsed = urlsplit(source)
        if parsed.hostname == 'github.com':
            owner, repo = [unquote(x).casefold() for x in parsed.path.strip('/').split('/')]
            repo = repo.removesuffix('.git')
            if owner and repo and not any(c in owner + repo for c in '/?#\\'):
                result.update(method='canonical_github_repo_v1', key=f'github.com/{owner}/{repo}')
    return result


def safe_name(name):
    # Historical local project names may themselves be paths.
    return '' if '/' in name or '\\' in name else name


class HistoryReader:
    def __init__(self, registry, assessment_store, cursor_key):
        self.registry, self.assessment_store, self.cursor_key = registry, assessment_store, cursor_key

    def encode(self, run, binding):
        payload = canonical({'v': 1, 'anchor': run.id, 'created_at': utc(run.created_at), 'filters': binding, 'sort': SORT})
        signature = hmac.digest(self.cursor_key, payload, 'sha256')
        return base64.urlsafe_b64encode(signature + payload).decode().rstrip('=')

    def decode(self, token, binding):
        try:
            if len(token) > 2048:
                raise ValueError()
            data = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
            sig, payload = data[:32], data[32:]
            if not hmac.compare_digest(sig, hmac.digest(self.cursor_key, payload, 'sha256')):
                raise ValueError()
            value = json.loads(payload)
            if set(value) != {'v','anchor','created_at','filters','sort'} or value['v'] != 1 or value['filters'] != binding or value['sort'] != SORT:
                raise ValueError()
            return value
        except (ValueError, TypeError, KeyError, UnicodeError):
            fail('cursor_invalid')

    def page(self, *, cursor=None, limit='20', status=None, source_type=None, q=None, project_key=None):
        try:
            size = int(limit)
            if not 1 <= size <= 100 or str(size) != str(limit):
                raise ValueError()
            if status is not None:
                ScanStatus(status)
            if source_type is not None:
                SourceType(source_type)
        except (ValueError, TypeError):
            fail('invalid_argument')
        query = (q or '').strip().casefold() or None
        filters = {'status': status, 'source_type': source_type, 'q': query, 'project_key': project_key}
        binding = hashlib.sha256(canonical(filters)).hexdigest()
        anchor = self.decode(cursor, binding) if cursor is not None else None
        after = anchor['anchor'] if anchor else None
        try:
            if anchor:
                try:
                    row = self.registry.get(after)
                except ScanRegistryError as error:
                    if error.code in {'registry_not_found','registry_invalid_argument'}:
                        fail('cursor_invalid')
                    raise
                if utc(row.run.created_at) != anchor['created_at']:
                    fail('cursor_invalid')
            found = []
            while True:
                page = self.registry.list_runs(limit=100, after_scan_id=after)
                for row in page.items:
                    run = row.run
                    source, searchable = public_source(run)
                    pid = identity(run, source, searchable)
                    if status is not None and run.status.value != status:
                        continue
                    if source_type is not None and run.project.source_type.value != source_type:
                        continue
                    if project_key is not None and pid['key'] != project_key:
                        continue
                    if query and query not in safe_name(run.project.name).casefold() and not (searchable and query in source.casefold()):
                        continue
                    found.append((row, source, pid))
                    if len(found) > size:
                        break
                if len(found) > size or page.next_after_scan_id is None:
                    break
                after = page.next_after_scan_id
            items = [self.project(row, source, pid, binding) for row, source, pid in found[:size]]
            next_cursor = self.encode(found[size-1][0].run, binding) if len(found) > size else None
            return P1HistoryPage(items=items, next_cursor=next_cursor)
        except (ScanRegistryError, AssessmentStoreError, ValidationError):
            fail('upstream_unavailable', 503)

    def project(self, stored, source, pid, binding):
        run = stored.run
        latest = self.assessment_store.latest(run.id) if self.assessment_store is not None else None
        assessment = None
        if latest is not None:
            assessment = P1AssessmentRef(assessment_id=latest.id, version=latest.version, scan_id=latest.scan_id, facts_hash=latest.facts_hash, usage_hash=latest.usage_hash, rule_version=latest.rule_version, formal=latest.formal)
            if assessment.scan_id != run.id:
                fail('upstream_unavailable', 503)
        scan_ref = dict(scan_id=run.id, revision=run.project.revision, facts_hash=facts_digest(run), input_hash=run.provenance.input_digest.value, inventory_hash=run.provenance.inventory_digest.value if run.provenance.inventory_digest else None, status=run.status, registry_revision=stored.revision)
        return P1ScanHistoryItem(scan_id=run.id, project_identity=pid, source_type=run.project.source_type, source=source, revision=run.project.revision, input_hash=scan_ref['input_hash'], inventory_hash=scan_ref['inventory_hash'], status=run.status, stage=run.stage, created_at=utc(run.created_at), finished_at=utc(run.finished_at) if run.finished_at else None, component_count=len(run.components), ai_asset_count=len(run.ai_assets), finding_count=len(run.findings), summary=run.summary, latest_assessment=assessment, provenance=dict(producer={'name':'openguard-history','version':'1.0'}, source_refs=[scan_ref], assessment_refs=[assessment] if assessment else [], generated_at=utc(datetime.now(timezone.utc)), algorithm_version='history/1.0', parameters_hash=binding))
