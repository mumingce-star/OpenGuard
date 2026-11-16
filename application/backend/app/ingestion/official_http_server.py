"""Fixed public http-server source acquisition, isolated from P2 source admission.

Six HTTP intents/job (DoH included), eighteen/task by default; no replay after ambiguity.
Python audit permission is a narrow trusted-caller aid, not an OS sandbox.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import replace
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import threading
import time

from .metadata_egress import _json
from .metadata_types import ErrorCode, Limits, MetadataError
from .metadata_wire import Deadline, Wire, public_answers

COMMIT = '0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b'
PACKAGE = 'http-server'
VERSION = '14.1.2'
LICENSE_SHA256 = 'accfc4d5a588384b29c4817392854afb8f319b4568359ca8d063df8a9bc396b6'
LICENSE_BYTES = 1124
GIT_HOST = 'raw.githubusercontent.com'
NPM_HOST = 'registry.npmjs.org'
DOH_HOST = 'cloudflare-dns.com'
GIT_PATH = f'/http-party/http-server/{COMMIT}/LICENSE'
NPM_PATH = '/http-server/14.1.2'
VERSION_ID = 'fixed-http-server-official-sources/1'
MAX_JOB_HTTP = 6
MAX_TASK_HTTP = 18
MAX_FIXED_DNS_ANSWERS = 32
_CONNECTION = threading.local()
_SERIAL = threading.Lock()


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def allows_connection(address):
    """For the host audit hook: only current thread's actual numeric dial."""
    allowed = getattr(_CONNECTION, 'allowed', None)
    if allowed is None or not isinstance(address, tuple) or len(address) not in (2, 4):
        return False
    try:
        return (ipaddress.ip_address(address[0]).compressed, address[1]) == allowed and type(address[1]) is int
    except (ValueError, TypeError):
        return False


@contextmanager
def connection_window(endpoint):
    address = ipaddress.ip_address(endpoint.ip)
    if not address.is_global or endpoint.socket_address[1] != 443:
        raise MetadataError(ErrorCode.POLICY)
    if getattr(_CONNECTION, 'allowed', None) is not None:
        raise MetadataError(ErrorCode.POLICY)
    _CONNECTION.allowed = (address.compressed, 443)
    try:
        yield
    finally:
        _CONNECTION.allowed = None


def _directory(path):
    path = Path(path).absolute()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or path.resolve() != path
            or info.st_uid != os.geteuid() or info.st_mode & 0o022):
        raise ValueError('official_source_unsafe_path')
    return path


def _write_bytes(path, raw):
    # Every filename is generated below, never taken from upstream content.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())


def _atomic_json(path, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode()
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    os.replace(temporary, path)


def _read_json(path, limit=262144):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as inp:
        info = os.fstat(inp.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ValueError('official_source_unsafe_file')
        raw = inp.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('official_source_ledger_limit')
    return json.loads(raw)


class _AuditedWire(Wire):
    def __init__(self, owner, job, *, dialer=None, context_factory=None):
        kwargs = {'connection_scope': connection_window}
        if dialer is not None: kwargs['dialer'] = dialer
        if context_factory is not None: kwargs['context_factory'] = context_factory
        super().__init__(**kwargs)
        self.owner, self.job = owner, job
        self.resolving = None

    def resolve(self, host, budget, limits):
        if host not in (GIT_HOST, NPM_HOST):
            raise MetadataError(ErrorCode.INPUT)
        self.resolving = host
        try:
            # Both complete A/AAAA packets remain bounded and are consumed.
            # The fixed caller checks every returned address before any GET;
            # it never truncates later addresses or skips the AAAA query.
            return super().resolve(host, budget, limits, max_answers=MAX_FIXED_DNS_ANSWERS)
        finally:
            self.resolving = None

    def exchange(self, host, endpoints, path, budget, limits, *, dns_body=None, **ignored):
        is_dns = dns_body is not None
        if is_dns:
            if host != DOH_HOST or path != '/dns-query' or self.resolving not in (GIT_HOST, NPM_HOST):
                raise MetadataError(ErrorCode.INPUT)
            # Strictly bind question labels + class/type, even for trusted seams.
            labels = b''.join(bytes([len(x)]) + x.encode('ascii') for x in self.resolving.split('.')) + b'\x00'
            if type(dns_body) is not bytes or len(dns_body) != 12 + len(labels) + 4 or dns_body[12:-4] != labels or dns_body[-4:] not in (b'\x00\x01\x00\x01', b'\x00\x1c\x00\x01'):
                raise MetadataError(ErrorCode.INPUT)
        elif (host, path) not in ((GIT_HOST, GIT_PATH), (NPM_HOST, NPM_PATH)):
            raise MetadataError(ErrorCode.INPUT)
        if len(endpoints) < 1:
            raise MetadataError(ErrorCode.DNS)
        # Resolve() historically allows 64KiB DoH. This caller enforces 32KiB too.
        limits = replace(limits, attempts=1, body_bytes=32768, header_bytes=32768)
        item = self.owner._intent(self.job, host, path, 'POST' if is_dns else 'GET', self.resolving if is_dns else None,
                                  int.from_bytes(dns_body[-4:-2], 'big') if is_dns else None)
        wire_path = self.owner.root / 'jobs' / self.job['job_id'] / f"response-{item['job_number']:02d}.wire"
        wire_file = None
        request_wire = bytearray()
        dispatch_seen = sent_seen = False
        raw_sha = hashlib.sha256(); raw_size = 0

        def observe(event, value):
            nonlocal dispatch_seen, sent_seen, wire_file, raw_size
            if event == 'request_dispatch' and not dispatch_seen:
                dispatch_seen = True
                item['dispatch_attempt_utc'] = utc()
                item['state'] = 'DISPATCH_ATTEMPT_OUTCOME_UNKNOWN'
                self.owner._save()
            elif event == 'request_bytes':
                request_wire.extend(value)
            elif event == 'request_sent' and not sent_seen:
                sent_seen = True; item['first_sendall_completed_utc'] = utc(); self.owner._save()
            elif event == 'response_chunk' and value:
                if wire_file is None:
                    fd = os.open(wire_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    wire_file = os.fdopen(fd, 'wb')
                wire_file.write(value); raw_sha.update(value); raw_size += len(value)
            elif event in ('connected_peer', 'tls_peer'):
                item[event] = dict(value)
                self.owner._save()
            elif event == 'response_headers':
                item['http_status'] = value['status']
                # No cookies are exported. Fixed protocol fields only.
                item['headers'] = {k: v for k, v in value['headers'] if k in ('content-type', 'content-length', 'transfer-encoding', 'content-encoding')}
                item['response_headers_utc'] = utc(); self.owner._save()
        try:
            media = b'text/plain' if host == GIT_HOST else b'application/json'
            body = super().exchange(host, endpoints, path, budget, limits, dns_body=dns_body,
                                    content_type=media, observer=observe)
            path_body = self.owner.root / 'jobs' / self.job['job_id'] / f"response-{item['job_number']:02d}.body"
            _write_bytes(path_body, body)
            item.update(state='RESPONSE_COMPLETE', timed_out=False, response_sha256=sha(body), response_bytes=len(body), body_path=str(path_body))
            return body
        except Exception as exc:
            item.update(state='FAILED_NO_RETRY', timed_out=(exc.code == ErrorCode.TIMEOUT) if isinstance(exc, MetadataError) else None, error_code=exc.code.value if isinstance(exc, MetadataError) else 'transport_or_audit_failure')
            if isinstance(exc, MetadataError) and exc.upstream_status is not None:
                item['http_status'] = exc.upstream_status
            raise
        finally:
            if request_wire:
                request_path = wire_path.with_name(wire_path.name.replace('response-', 'request-'))
                _write_bytes(request_path, bytes(request_wire))
                item.update(request_wire_path=str(request_path), request_wire_sha256=sha(request_wire), request_wire_bytes=len(request_wire))
            if wire_file is not None:
                wire_file.flush(); os.fsync(wire_file.fileno()); wire_file.close()
                item.update(raw_wire_path=str(wire_path), raw_wire_sha256=raw_sha.hexdigest(), raw_wire_bytes=raw_size)
            item['finished_utc'] = utc(); self.owner._save()


class FixedOfficialFetcher:
    """Task-owned, fixed-target fetcher. Test seams cannot be HTTP caller input."""
    def __init__(self, root, *, budget_path=None, max_task_http=MAX_TASK_HTTP, _wire_factory=None, _clock=time.monotonic):
        if type(max_task_http) is not int or max_task_http not in (18, 24, 29, 35):
            raise ValueError('official_source_http_limit_invalid')
        self.max_task_http = max_task_http
        self.root = _directory(root)
        _directory(self.root / 'jobs')
        self.budget_path = Path(budget_path).absolute() if budget_path else self.root / 'HTTP_BUDGET.json'
        _directory(self.budget_path.parent)
        if self.budget_path.is_symlink():
            raise ValueError('official_source_unsafe_budget')
        self.namespace = sha(str(self.root).encode())[:24]
        self._wire_factory = _wire_factory
        self._clock = _clock
        self._ledger = None

    def _save(self):
        _atomic_json(self.budget_path, self._ledger)

    def _check_ledger(self, ledger):
        # A new explicit limit never migrates or resets an existing ledger.
        # Both limits and inherited request count must match this instance.
        if (type(ledger) is not dict or ledger.get('version') != VERSION_ID
                or type(ledger.get('max_task_http')) is not int or ledger['max_task_http'] != self.max_task_http
                or type(ledger.get('max_job_http')) is not int or ledger['max_job_http'] != MAX_JOB_HTTP
                or type(ledger.get('requests')) is not list or type(ledger.get('jobs')) is not dict
                or len(ledger['requests']) > self.max_task_http):
            raise ValueError('official_source_budget_invalid')

    def _intent(self, job, host, path, method, dns_host, dns_type):
        self._check_ledger(self._ledger)
        if len(self._ledger['requests']) >= self.max_task_http or len(job['request_numbers']) >= MAX_JOB_HTTP:
            raise ValueError('official_source_http_budget_exhausted')
        item = {'number': len(self._ledger['requests']) + 1, 'job_number': len(job['request_numbers']) + 1,
                'job_id': job['job_id'], 'job_key': job['job_key'], 'intent_utc': utc(), 'method': method, 'url': f'https://{host}{path}',
                'dns_host': dns_host, 'dns_type': dns_type, 'state': 'INTENT_BEFORE_NETWORK',
                'dispatch_attempt_utc': None, 'first_sendall_completed_utc': None,
                'http_status': None, 'response_sha256': None, 'response_bytes': None, 'timed_out': None}
        self._ledger['requests'].append(item); job['request_numbers'].append(item['number']); self._save()
        return item

    def _early_result(self, job_id, status, error):
        # Read only an atomic ledger snapshot; a busy caller cannot reserve work.
        # Unknown records expose actual prior dispatch counts rather than zero.
        ledger = _read_json(self.budget_path) if self.budget_path.exists() else {'version': VERSION_ID,
            'max_task_http': self.max_task_http, 'max_job_http': MAX_JOB_HTTP, 'requests': [], 'jobs': {}}
        self._check_ledger(ledger)
        key = self.namespace + ':' + job_id
        requests = [r for r in ledger['requests'] if r.get('job_key') == key]
        return {'version': VERSION_ID, 'job_id': job_id, 'status': status, 'error_code': error,
                'sources': [], 'automatic_replay': False, 'http_intents': len(requests),
                'http_dispatched': sum(r.get('dispatch_attempt_utc') is not None for r in requests),
                'http_sendall_completed': sum(r.get('first_sendall_completed_utc') is not None for r in requests),
                'http_responses': sum(r.get('http_status') is not None for r in requests),
                'task_http_intents': len(ledger['requests']), 'max_job_http': MAX_JOB_HTTP, 'max_task_http': self.max_task_http,
                'requests': requests, 'formal_effect': 'none', 'network_control': 'APPLICATION_TCB_NOT_OS_SANDBOX'}

    def fetch(self, job_id):
        if type(job_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', job_id):
            raise ValueError('official_source_job_id_invalid')
        if not _SERIAL.acquire(blocking=False):
            return self._early_result(job_id, 'failed', 'official_source_busy')
        lockfd = None
        try:
            lock_path = self.budget_path.with_name(self.budget_path.name + '.lock')
            lockfd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            lock_info = os.fstat(lockfd)
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1 or lock_info.st_uid != os.geteuid() or lock_info.st_mode & 0o022:
                raise ValueError('official_source_unsafe_lock')
            try: fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return self._early_result(job_id, 'failed', 'official_source_busy')
            self._ledger = _read_json(self.budget_path) if self.budget_path.exists() else {'version': VERSION_ID, 'max_task_http': self.max_task_http, 'max_job_http': MAX_JOB_HTTP, 'requests': [], 'jobs': {}}
            self._check_ledger(self._ledger)
            receipt_path = self.root / 'jobs' / job_id / 'RECEIPT.json'
            job_key = self.namespace + ':' + job_id
            if job_key in self._ledger['jobs']:
                if receipt_path.exists():
                    return _read_json(receipt_path)
                return self._early_result(job_id, 'outcome_unknown', 'official_source_previous_outcome_unknown')
            job_dir = _directory(self.root / 'jobs' / job_id)
            job = {'job_id': job_id, 'job_key': job_key, 'started_utc': utc(), 'status': 'running', 'request_numbers': []}
            self._ledger['jobs'][job_key] = job; self._save()
            sources = []; error = None; status = 'failed'
            try:
                # Reserve feasibility for the entire fixed plan before first DNS.
                if len(self._ledger['requests']) + MAX_JOB_HTTP > self.max_task_http:
                    raise ValueError('official_source_http_budget_exhausted')
                limits = Limits(body_bytes=32768, header_bytes=32768, attempts=1)
                deadline = Deadline(limits, self._clock)
                wire = self._wire_factory(self, job) if self._wire_factory else _AuditedWire(self, job)
                for kind, host, path in (('git_license', GIT_HOST, GIT_PATH), ('npm_metadata', NPM_HOST, NPM_PATH)):
                    answers = wire.resolve(host, deadline, limits)
                    endpoints = public_answers(host, answers, limits, max_answers=MAX_FIXED_DNS_ANSWERS)
                    job.setdefault('validated_dns_answer_counts', {})[host] = len(answers)
                    self._save()
                    raw = wire.exchange(host, endpoints, path, deadline, limits)
                    if kind == 'git_license':
                        if len(raw) != LICENSE_BYTES or sha(raw) != LICENSE_SHA256:
                            raise ValueError('official_source_license_identity_mismatch')
                        raw.decode('utf-8', 'strict')
                    else:
                        data = _json(raw, limits, deadline)
                        if data.get('name') != PACKAGE or data.get('version') != VERSION:
                            raise ValueError('official_source_npm_identity_mismatch')
                    body_path = job_dir / f'source-{kind}.body'; _write_bytes(body_path, raw)
                    sources.append({'kind': kind, 'status': 'observed', 'url': f'https://{host}{path}',
                                    'name': PACKAGE, 'version': VERSION, 'commit': COMMIT if kind == 'git_license' else None,
                                    'sha256': sha(raw), 'byte_count': len(raw), 'body_path': str(body_path),
                                    'content_type': 'text/plain' if kind == 'git_license' else 'application/json',
                                    'source_level': 'official_repository_bytes_observed' if kind == 'git_license' else 'provider_declared_unverified',
                                    'verification_state': 'pending', 'observed_at': utc(), 'retrieved_at': self._ledger['requests'][-1]['finished_utc'],
                                    'scope': 'fixed_git_root_file' if kind == 'git_license' else 'npm_version_metadata_only',
                                    'npm_release_license_proven': False, 'formal_source_issued': False})
                status = 'succeeded'
            except Exception as exc:
                if isinstance(exc, MetadataError): error = exc.code.value
                elif isinstance(exc, ValueError) and str(exc).startswith('official_source_'): error = str(exc)
                else: error = 'official_source_read_failed'
            requests = [r for r in self._ledger['requests'] if r['job_key'] == job_key]
            receipt = {'version': VERSION_ID, 'job_id': job_id, 'status': status, 'error_code': error,
                       'package': PACKAGE, 'version_name': VERSION, 'commit': COMMIT, 'sources': sources,
                       'started_utc': job['started_utc'], 'finished_utc': utc(), 'automatic_replay': False,
                       'http_intents': len(requests), 'http_dispatched': sum(r['dispatch_attempt_utc'] is not None for r in requests),
                       'http_sendall_completed': sum(r['first_sendall_completed_utc'] is not None for r in requests),
                       'http_responses': sum(r['http_status'] is not None for r in requests),
                       'validated_dns_answer_counts': job.get('validated_dns_answer_counts', {}),
                       'max_job_http': MAX_JOB_HTTP, 'max_task_http': self.max_task_http, 'task_http_intents': len(self._ledger['requests']),
                       'requests': requests, 'formal_effect': 'none', 'network_control': 'APPLICATION_TCB_NOT_OS_SANDBOX'}
            _atomic_json(receipt_path, receipt)
            job['status'] = status; job['finished_utc'] = receipt['finished_utc']; self._save()
            return receipt
        finally:
            if lockfd is not None: os.close(lockfd)
            _SERIAL.release()
