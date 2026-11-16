"""Pure, exact-result material-clause view. Never an applicability signature.

Source trust is a separately pinned operator profile, never upload text or a URL.
Only complete standard MIT text has a rule here. Existing P2 objects stay intact.
"""
from __future__ import annotations

import base64
import hashlib
import gzip
import zlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import Field, ValidationError
from app.p2b.material_claims import PERMISSION, CONDITION, WARRANTY, complete_mit

from .contract import Binding, DTO, ID, SHA, Subject, Use, P2Error, digest, strict_json

VERSION = 'openguard-p2-preliminary-advice/1'
RULE = 'mit-complete-text/1'
USES = ('commercial', 'modified', 'distributed', 'network_service', 'training', 'redistributed_assets', 'source_disclosure')
SUPPORTED = {'commercial', 'modified', 'distributed', 'network_service'}
CONDITIONS = ['在软件副本或实质部分中保留原版权声明和完整 MIT 许可声明', '按实际交付范围确认该精确资源版本，并保留可追溯的发行来源记录']
LIMITATIONS = ['仅为已绑定材料的条款初评，来源适用性及实际履行尚未经人工签认', '依据为该精确版本的官方发行材料；项目实际安装副本尚未逐文件比对', '不覆盖其他资源、其他版本、商标、专利或未提供的附加条款；不代表项目整体获得授权']


class SourcePackage(DTO):
    package: str = Field(min_length=1, max_length=214)
    version: str = Field(pattern=r'^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')
    metadata_file: str
    metadata_sha256: SHA
    tarball_file: str
    tarball_sha256: SHA
    license_file: str
    license_sha256: SHA
    member: str
    metadata_url: str
    tarball_url: str
    fetched_at: str = Field(min_length=10, max_length=64)
    applicability_review: Literal['NOT_SIGNED']


class SourceProfile(DTO):
    schema_version: Literal['openguard-public-npm-source-profile/1']
    data_scope: Literal['OWNER', 'TEST_ONLY']
    packages: list[SourcePackage] = Field(max_length=20)


class ResourceAdvice(DTO):
    subject: Subject
    name: str
    state: Literal['CONDITIONAL_TEXT_BASIS'] = 'CONDITIONAL_TEXT_BASIS'
    recommendation: str
    conditions: list[str]
    limitations: list[str]
    material_ids: list[ID]
    material_sha256: list[SHA]
    evidence_ids: list[ID]
    source_urls: list[str]
    rule_id: Literal['mit-complete-text/1'] = RULE


class UsageAdvice(DTO):
    usage: Use
    saved_value: bool | None
    selection: Literal['SELECTED', 'NOT_SELECTED', 'UNKNOWN']
    state: Literal['CONDITIONAL_TEXT_BASIS', 'NO_SUPPORTED_BASIS', 'NOT_SELECTED', 'USAGE_UNDECLARED']
    summary: str
    resources: list[ResourceAdvice]
    uncovered_resource_ids: list[ID]


class PreliminaryAdvice(DTO):
    schema_version: Literal['openguard-p2-preliminary-advice/1'] = VERSION
    rule_version: Literal['mit-complete-text/1'] = RULE
    recommendation_id: ID
    result_id: ID
    result_sha256: SHA
    binding: Binding
    data_scope: Literal['OWNER', 'TEST_ONLY']
    source_profile_sha256: SHA | None
    source_status: Literal['CHECKED', 'NOT_CONFIGURED']
    scope: Literal['RESOURCE_SUBSET'] = 'RESOURCE_SUBSET'
    total_resources: int = Field(ge=0)
    supported_resource_ids: list[ID]
    uncovered_resource_ids: list[ID]
    advice: list[UsageAdvice]
    limitations: list[str]
    formal_effect: Literal['none'] = 'none'
    model_calls: Literal[0] = 0
    applicability_review: Literal['NOT_SIGNED'] = 'NOT_SIGNED'


def _read(root: Path, name: str, maximum: int) -> bytes:
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', name) or name in {'.', '..'}:
        raise ValueError('source_path')
    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= maximum:
            raise ValueError('source_file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != before.st_size:
            raise ValueError('source_changed')
        return raw
    finally:
        os.close(fd)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()



def _npm_url(url):
    u = urlsplit(url)
    if u.scheme != 'https' or u.netloc != 'registry.npmjs.org' or u.query or u.fragment or not u.path:
        raise ValueError('source_url')


def _package_files(raw: bytes, license_member: str):
    return _package_files_expanded(_bounded_gzip_bytes(raw), license_member)


def _package_files_expanded(expanded: bytes, license_member: str):
    """Inspect bytes already fully decompressed by this request's source gate."""
    wanted = {'package/package.json', license_member}
    seen, found, size = set(), {}, 0
    with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            normalized = str(path)
            if (normalized in seen or member.name not in ({normalized, normalized + '/'} if member.isdir() else {normalized})
                    or len(seen) >= 2000 or path.is_absolute() or '..' in path.parts
                    or '\\' in member.name or not member.name.startswith('package/')
                    or not (member.isdir() or member.isreg()) or member.size < 0):
                raise ValueError('unsafe_tar_member')
            seen.add(normalized)
            size += member.size
            if size > 20 * 1024 * 1024 or member.size > 4 * 1024 * 1024:
                raise ValueError('tar_limit')
            if member.name in wanted:
                if not member.isreg() or member.size > 65536:
                    raise ValueError('source_member')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('source_member')
                content = stream.read(65537)
                if len(content) != member.size:
                    raise ValueError('source_member_size')
                found[member.name] = content
    if set(found) != wanted:
        raise ValueError('source_member_missing')
    return found


# Strict source-member inspection is opt-in for material-claims/3 only.
# Normal legacy advice semantics stay unchanged; corrupt compression fails the source gate.
_NOTICE_LIMIT = 65536
_NOTICE_COUNT = 20
_NOTICE_TOTAL = 1024 * 1024
# Bounded decompression also accounts for tar headers/padding, not just declared data.
_TAR_ENVELOPE_LIMIT = 20 * 1024 * 1024 + 2000 * 2048 + 10240


def _bounded_gzip_bytes(raw: bytes) -> bytes:
    """Consume compression trailers within the existing envelope budget.

    read(maximum + 1) either reaches EOF (including CRC/trailer validation) or
    refuses an oversized expansion. Tar member/tail policy remains separate.
    """
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('SOURCE_ARCHIVE_LIMIT')
    with gzip.GzipFile(fileobj=io.BytesIO(raw), mode='rb') as stream:
        expanded = stream.read(_TAR_ENVELOPE_LIMIT + 1)
    if len(expanded) > _TAR_ENVELOPE_LIMIT:
        raise ValueError('SOURCE_EXPANSION_LIMIT')
    return expanded


def _notice_inventory(raw: bytes):
    # Direct callers still pass through the complete bounded Gzip check.
    try:
        expanded = _bounded_gzip_bytes(raw)
    except (OSError, EOFError, zlib.error, ValueError, tarfile.TarError):
        return {'status': 'INCOMPLETE', 'reason': 'SOURCE_MEMBER_INSPECTION_INCOMPLETE',
                'member_count': 0, 'enumeration_complete': False, 'members': [], 'raw_notices': {}}
    return _notice_inventory_expanded(expanded)


def _notice_inventory_expanded(expanded: bytes):
    """Keep NOTICE-specific member and tail checks on the same verified bytes."""
    result = {'status': 'INCOMPLETE', 'reason': 'NOT_INSPECTED', 'member_count': 0,
              'enumeration_complete': False, 'members': [], 'raw_notices': {}}
    try:
        seen = set()
        total = 0
        notice_total = 0
        last_end = 0
        invalid = False
        with tarfile.open(fileobj=io.BytesIO(expanded), mode='r:') as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                canonical = str(path)
                if (len(seen) >= 2000 or canonical in seen or path.is_absolute()
                        or '..' in path.parts or '\\' in member.name
                        or len(member.name) > 4096 or not member.name.startswith('package/')
                        or member.name not in ({canonical, canonical + '/'} if member.isdir() else {canonical})
                        or not (member.isreg() or member.isdir()) or member.size < 0):
                    raise ValueError('UNSAFE_OR_UNBOUNDED_MEMBER')
                seen.add(canonical); total += member.size
                result['member_count'] = len(seen)
                if total > 20 * 1024 * 1024 or member.size > 4 * 1024 * 1024:
                    raise ValueError('TAR_DECLARED_SIZE_LIMIT')
                last_end = member.offset_data + ((member.size + 511) // 512) * 512
                base = path.name.upper()
                if base != 'NOTICE' and not base.startswith('NOTICE.'):
                    continue
                if len(result['members']) >= _NOTICE_COUNT:
                    raise ValueError('NOTICE_COUNT_LIMIT')
                item = {'path': canonical, 'bytes': member.size, 'sha256': None,
                        'inspection_state': 'INVALID_TYPE'}
                result['members'].append(item)
                notice_total += member.size
                if not member.isreg():
                    invalid = True; continue
                if member.size > _NOTICE_LIMIT or notice_total > _NOTICE_TOTAL:
                    item['inspection_state'] = 'LIMIT_EXCEEDED'; invalid = True; continue
                item['inspection_state'] = 'READ_FAILED'
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('NOTICE_READ_UNAVAILABLE')
                content = stream.read(_NOTICE_LIMIT + 1)
                if len(content) != member.size:
                    raise ValueError('NOTICE_INCOMPLETE_READ')
                item['sha256'] = _sha(content)
                result['raw_notices'][member.name] = content
                if not re.fullmatch(r'NOTICE(?:\.(?:TXT|MD|RST))?', base):
                    item['inspection_state'] = 'UNSUPPORTED_FORMAT'; invalid = True; continue
                try:
                    text = content.decode('utf-8', errors='strict')
                    if not text.strip() or '\x00' in text:
                        raise ValueError('invalid_text')
                except (UnicodeError, ValueError):
                    item['inspection_state'] = 'PARSE_FAILED'; invalid = True; continue
                item['inspection_state'] = 'EXTRACTED_UNREVIEWED'
        if not seen:
            raise ValueError('EMPTY_TAR')
        # Reject a second archive or nonzero data hidden beyond the first tar EOF.
        # A supported tar must have at least two zero blocks and no nonzero tail.
        tail = expanded[last_end:]
        if len(tail) < 1024 or any(tail):
            raise ValueError('TAR_END_OR_TRAILING_DATA_INVALID')
        result['enumeration_complete'] = True
        result['status'] = 'INVALID' if invalid else 'PRESENT_UNREVIEWED' if result['members'] else 'ABSENT_COMPLETE'
        result['reason'] = 'NOTICE_MEMBER_UNUSABLE' if invalid else 'NOTICE_NOT_INTERPRETED' if result['members'] else 'COMPLETE_SUPPORTED_ARCHIVE_NO_NOTICE'
    except (OSError, EOFError, zlib.error, ValueError, tarfile.TarError):
        result['status'] = 'INCOMPLETE'
        result['reason'] = 'SOURCE_MEMBER_INSPECTION_INCOMPLETE'
    return result


def load_sources(root, expected_sha, data_scope, *, inspect_notices=False):
    if not root and not expected_sha:
        return {}, None
    try:
        if not root or not isinstance(expected_sha, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha):
            raise ValueError('source_config')
        directory = Path(root)
        if not directory.is_absolute() or not stat.S_ISDIR(directory.lstat().st_mode) or directory.is_symlink():
            raise ValueError('source_root')
        raw = _read(directory, 'profile.json', 65536)
        if _sha(raw) != expected_sha:
            raise ValueError('source_profile_hash')
        profile = SourceProfile.model_validate(strict_json(raw))
        if profile.data_scope != data_scope:
            raise ValueError('source_scope')
        sources = {}
        for item in profile.packages:
            identity = (item.package, item.version)
            if identity in sources or not re.fullmatch(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+', item.package):
                raise ValueError('source_identity')
            _npm_url(item.metadata_url)
            _npm_url(item.tarball_url)
            expected_paths = {'/' + item.package + '/' + item.version, '/' + quote(item.package, safe='') + '/' + item.version}
            if urlsplit(item.metadata_url).path not in expected_paths:
                raise ValueError('metadata_version_url')
            metadata_raw = _read(directory, item.metadata_file, 1024 * 1024)
            tar_raw = _read(directory, item.tarball_file, 4 * 1024 * 1024)
            license_raw = _read(directory, item.license_file, 65536)
            if (_sha(metadata_raw), _sha(tar_raw), _sha(license_raw)) != (item.metadata_sha256, item.tarball_sha256, item.license_sha256):
                raise ValueError('source_file_hash')
            metadata = strict_json(metadata_raw)
            if not isinstance(metadata, dict) or (metadata.get('name'), metadata.get('version'), metadata.get('license')) != (item.package, item.version, 'MIT'):
                raise ValueError('metadata_identity')
            dist = metadata.get('dist')
            if not isinstance(dist, dict) or dist.get('tarball') != item.tarball_url:
                raise ValueError('dist_identity')
            sri = dist.get('integrity')
            if not isinstance(sri, str) or sri != 'sha512-' + base64.b64encode(hashlib.sha512(tar_raw).digest()).decode():
                raise ValueError('dist_integrity')
            if 'shasum' in dist and dist['shasum'] != hashlib.sha1(tar_raw).hexdigest():
                raise ValueError('dist_shasum')
            if not re.fullmatch(r'package/(?:LICENSE|LICENCE|license|licence)(?:\.(?:txt|md|rst))?', item.member):
                raise ValueError('license_member')
            # Reuse only this package's immutable, fully checked expansion within
            # this load_sources call. Never cache across requests or source pins.
            expanded = _bounded_gzip_bytes(tar_raw)
            members = _package_files_expanded(expanded, item.member)
            package = strict_json(members['package/package.json'])
            if not isinstance(package, dict) or (package.get('name'), package.get('version'), package.get('license')) != (item.package, item.version, 'MIT') or members[item.member] != license_raw:
                raise ValueError('package_identity')
            sources[identity] = {'record': item, 'bytes': license_raw, 'complete_mit': complete_mit(license_raw)}
            if inspect_notices:
                sources[identity]['notice_inventory'] = _notice_inventory_expanded(expanded)
        return sources, expected_sha
    except (OSError, EOFError, zlib.error, ValueError, TypeError, UnicodeError, ValidationError, tarfile.TarError) as exc:
        raise P2Error('p2_public_source_invalid', 503) from exc


def project(result, resources, materials, source_root, source_sha, declared_licenses):
    sources, profile_sha = load_sources(source_root, source_sha, result['data_scope'])
    return _project_sources(result, resources, materials, declared_licenses, sources, profile_sha)


def _project_sources(result, resources, materials, declared_licenses, sources, profile_sha):
    # Shared old projection body; the source snapshot is validated before this call.
    supported = {}
    all_ids = sorted(row['subject']['resource_id'] for row in result['resources'])
    for row in result['resources']:
        rid, version = row['subject']['resource_id'], row['subject']['version']
        resource = resources[rid]
        source = sources.get((resource.name, version))
        if (row['resource_kind'] != 'component' or not source or not source['complete_mit']
                or getattr(resource, 'ecosystem', None) != 'npm'
                or declared_licenses.get(rid) not in {'MIT', 'UNOBSERVED'} or any('conflict' in gap for gap in row['gaps'])):
            continue
        purl = getattr(resource, 'purl', None)
        if purl is not None and purl not in {f'pkg:npm/{resource.name}@{version}', f'pkg:npm/{quote(resource.name, safe="/")}@{version}'}:
            continue
        source_url = getattr(resource, 'source_url', None)
        if source_url is not None and source_url != source['record'].tarball_url:
            continue
        if any(m['subject'] == row['subject'] and m['filename'].split('.')[0] == 'NOTICE' for m, _ in materials):
            continue  # This closed rule cannot safely interpret additional notices.
        license_materials = [(m, raw) for m, raw in materials if m['subject'] == row['subject']
                             and m['filename'].split('.')[0] in {'LICENSE', 'LICENCE'}]
        # One matching document cannot outweigh a different bound LICENSE.
        if any(raw != source['bytes'] for _, raw in license_materials):
            continue
        matching = []
        for material, raw in materials:
            if (material['subject'] == row['subject'] and material['binding'] == result['binding']
                    and material['material_id'] in row['material_ids'] and material['completeness'] == 'FULL_TEXT_CLAIMED'
                    and material['filename'].split('.')[0] in {'LICENSE', 'LICENCE'}
                    and raw == source['bytes'] and material['source_sha256'] == source['record'].license_sha256):
                matching.append(material)
        if matching:
            supported[rid] = (row, resource, source, matching)
    advice = []
    active_support = set()
    for usage in USES:
        value = result['usage'][usage]
        entries = []
        for rid, (row, resource, source, matching) in supported.items():
            if value is not True or usage not in SUPPORTED:
                continue
            if usage == 'distributed' and row['user_assertions'].get('DELIVERY_SCOPE_FOR_RESOURCES') == 'NO_EXCLUDE':
                continue
            label = {'commercial': '商业集成', 'modified': '修改与二次开发', 'distributed': '随产品分发或交付', 'network_service': '在线服务中的使用'}[usage]
            entries.append(ResourceAdvice(subject=row['subject'], name=resource.name,
                recommendation=f'{resource.name} {row["subject"]["version"]}：现有完整 MIT 文本支持将{label}作为有条件方案。',
                conditions=CONDITIONS, limitations=LIMITATIONS + (['当前扫描覆盖仍有缺口，此条款判断不表示所有依赖均已覆盖。'] if 'scan_coverage_incomplete' in row['gaps'] else []) + (['当前用户已明确排除该资源的交付；此判断不扩大实际交付范围。'] if row['user_assertions'].get('DELIVERY_SCOPE_FOR_RESOURCES') == 'NO_EXCLUDE' else []),
                material_ids=[m['material_id'] for m in matching], material_sha256=[m['source_sha256'] for m in matching],
                evidence_ids=sorted(set(e for m in matching for e in m['evidence_ids'])),
                source_urls=[source['record'].metadata_url, source['record'].tarball_url]))
            active_support.add(rid)
        state = 'NOT_SELECTED' if value is False else 'USAGE_UNDECLARED' if value is None else 'CONDITIONAL_TEXT_BASIS' if entries else 'NO_SUPPORTED_BASIS'
        summary = (f'{len(entries)} 个明确资源可作为有条件使用方案；其余范围仍需补证。' if entries else
                   '本次未选择该用途。' if value is False else '该用途尚未声明，不推定为允许或不适用。' if value is None else
                   '当前先保持未核验范围，补齐精确版本的完整许可材料后再扩展建议。')
        advice.append(UsageAdvice(usage=usage, saved_value=value, selection='UNKNOWN' if value is None else 'SELECTED' if value else 'NOT_SELECTED', state=state,
                                  summary=summary, resources=entries, uncovered_resource_ids=[rid for rid in all_ids if rid not in {e.subject.resource_id for e in entries}]))
    payload = PreliminaryAdvice(recommendation_id='p2pre_pending', result_id=result['result_id'], result_sha256=result['result_sha256'], binding=result['binding'],
        data_scope=result['data_scope'], source_profile_sha256=profile_sha, source_status='CHECKED' if profile_sha else 'NOT_CONFIGURED',
        total_resources=len(all_ids), supported_resource_ids=sorted(active_support), uncovered_resource_ids=sorted(set(all_ids)-active_support), advice=advice,
        limitations=LIMITATIONS).model_dump(mode='json')
    payload['recommendation_id'] = 'p2pre_' + digest({k: v for k, v in payload.items() if k != 'recommendation_id'})
    return payload
