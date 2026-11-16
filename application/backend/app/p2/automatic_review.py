"""Pinned npm material review, independent of immutable Formal/P2 conclusions.

No network, model, persistence, trust issuance, or applicability signature occurs
here. The policy is deliberately closed: only complete standard MIT/ISC texts
support conditional observations. Uninterpreted terms remain manual work.
"""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import Field, ValidationError

from .contract import DTO, ID, SHA, Subject, P2Error, digest, strict_json
from .preliminary import PERMISSION, CONDITION, WARRANTY

VERSION = 'openguard-auto-review/1'
RULE = 'npm-full-license-review/1'
LEGAL_NAME = re.compile(r'^(?:licen[cs]e|copying|notice)(?:[._-].*)?$', re.I)
PACKAGE_NAME = re.compile(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+')
ISC_PERMISSION = ('Permission to use, copy, modify, and/or distribute this software for any purpose '
                  'with or without fee is hereby granted, provided that the above copyright notice '
                  'and this permission notice appear in all copies.')
ISC_WARRANTY = ('THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD '
                'TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. '
                'IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR '
                'CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA '
                'OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, '
                'ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.')
LIMITATIONS = [
    '依据为精确版本的官方 npm 发行材料；项目实际安装字节未逐文件核验。',
    '处理优先级用于安排审查工作，不是漏洞严重度或违法判定。',
    '条款初评不代表人工适用性签认、义务已履行或整个项目获得授权；不改写正式评估。',
    '仅解释完整标准 MIT/ISC 文本；其他条款、附加声明及未覆盖来源保留人工关注。',
]


class Receipt(DTO):
    file: str
    bytes: int = Field(ge=1)
    sha256: SHA
    url: str
    utc: str = Field(min_length=10, max_length=64)
    status: Literal[200]
    headers: dict[str, str]


class Member(DTO):
    member: str
    file: str
    bytes: int = Field(ge=0, le=1024 * 1024)
    sha256: SHA


class Package(DTO):
    subject: Subject
    name: str = Field(min_length=1, max_length=214)
    purl: str | None
    evidence_ids: list[ID] = Field(max_length=200)
    status: Literal['FETCHED', 'UNAVAILABLE', 'UNSUPPORTED_RESOURCE']
    error_code: str | None = Field(default=None, max_length=80)
    metadata: Receipt | None
    tarball: Receipt | None
    members: list[Member] = Field(max_length=10000)


class Profile(DTO):
    schema_version: Literal['openguard-auto-npm-source/1']
    data_scope: Literal['OWNER', 'TEST_ONLY']
    scan_id: ID
    facts_hash: SHA
    project_revision: str | None
    packages: list[Package] = Field(max_length=1000)


class CaptureAnchor(DTO):
    file: str
    bytes: int = Field(ge=1, le=2 * 1024 * 1024)
    sha256: SHA


class CacheProfile(DTO):
    """Administrator-pinned opt-in to reuse bytes, never old scan conclusions."""
    schema_version: Literal['openguard-auto-npm-cache/1']
    mode: Literal['EXACT_NPM_COORDINATE']
    data_scope: Literal['OWNER', 'TEST_ONLY']
    anchor: CaptureAnchor


class CachedSources(dict):
    """Marks historical acquisition provenance without altering the wire DTO."""


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(root: Path, name: str, maximum: int) -> bytes:
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,180}', name) or name in {'.', '..'}:
        raise ValueError('source_path')
    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 <= before.st_size <= maximum:
            raise ValueError('source_file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if key(before) != key(after) or len(raw) != before.st_size:
            raise ValueError('source_changed')
        return raw
    finally:
        os.close(fd)


def _pinned_file(root, item, maximum):
    raw = _read(root, item.file, maximum)
    if len(raw) != item.bytes or _sha(raw) != item.sha256:
        raise ValueError('source_hash')
    return raw


def _npm_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.netloc != 'registry.npmjs.org' or parsed.query or parsed.fragment:
        raise ValueError('npm_source_url')
    return parsed.path


def _members(raw):
    seen, legal, expanded = set(), {}, 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        for member in archive:
            p = PurePosixPath(member.name); normalized = str(p)
            permitted = {normalized, normalized + '/'} if member.isdir() else {normalized}
            if (normalized in seen or member.name not in permitted or len(seen) >= 10000
                    or p.is_absolute() or '..' in p.parts or '\\' in member.name
                    or not (normalized == 'package' and member.isdir() or normalized.startswith('package/'))
                    or not (member.isdir() or member.isreg()) or member.size < 0):
                raise ValueError('unsafe_archive')
            seen.add(normalized); expanded += member.size
            if expanded > 64 * 1024 * 1024 or member.size > 16 * 1024 * 1024:
                raise ValueError('archive_limit')
            if member.isreg() and (normalized == 'package/package.json' or LEGAL_NAME.fullmatch(p.name)):
                if member.size > 1024 * 1024:
                    raise ValueError('legal_member_limit')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('archive_member')
                data = stream.read(1024 * 1024 + 1)
                if len(data) != member.size:
                    raise ValueError('archive_member_size')
                legal[normalized] = data
    if 'package/package.json' not in legal:
        raise ValueError('package_json_missing')
    return legal


def classify_text(raw):
    """Match complete bodies; declarations, snippets and appended terms fail closed."""
    try:
        text = raw.decode('utf-8', errors='strict').replace('\r\n', '\n').strip()
    except UnicodeError:
        return None
    if '\x00' in text or '\r' in text:
        return None
    for license_id, first, body in [
        ('MIT', 'Permission is hereby granted,', ' '.join([PERMISSION, CONDITION, WARRANTY])),
        ('ISC', 'Permission to use, copy, modify,', ' '.join([ISC_PERMISSION, ISC_WARRANTY])),
    ]:
        position = text.find(first)
        if position < 0 or ' '.join(text[position:].split()) != body:
            continue
        prefix = [line.strip() for line in text[:position].splitlines() if line.strip()]
        titles = ({'MIT License', 'The MIT License', 'The MIT License (MIT)', '(The MIT License)'}
                  if license_id == 'MIT' else {'ISC License', 'ISC License (ISC)'})
        if prefix and prefix[0] in titles:
            prefix.pop(0)
        if prefix and all(_copyright_attribution(p) for p in prefix):
            return license_id
    return None


def _copyright_attribution(line):
    """A narrow attribution grammar, not arbitrary prose preceding permission.

    Unfamiliar copyright lines stay manual. This rejects attached sentences and
    clause words instead of interpreting them as a person's or company's name.
    No positive license decision is made from any of these words.
    """
    match = re.fullmatch(r'Copyright(?: \(c\)| \(C\)| ©)? (.+)', line)
    if not match:
        return False
    holder = re.sub(r'^\d{4}(?:[-–]\d{4})?(?:, ?\d{4})* ', '', match.group(1))
    contact = (r' (?:<[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+>|'
               r'\((?:https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[A-Za-z0-9./_%-]*)?\))$')
    # A name may carry an email and a website, but never an arbitrary
    # parenthesized sentence. Repeated removal is bounded by line length.
    for _ in range(2):
        holder = re.sub(contact, '', holder)
    holder = re.sub(r'(?: and (?:other )?contributors| & the Contributors)\.?$', '', holder)
    holder = re.sub(r', (Inc\.|Ltd\.)$', r' \1', holder)
    if holder.endswith('.') and not holder.endswith(('Inc.', 'Ltd.')):
        holder = holder[:-1]
    if set(re.findall(r'[a-z]+', holder.lower())) & {
        'permission', 'license', 'licensed', 'licensing', 'condition', 'conditions', 'restriction', 'restricted',
        'prohibit', 'prohibited', 'commercial', 'noncommercial', 'use', 'uses', 'only', 'must', 'shall',
        'provided', 'subject', 'except', 'excluding', 'not', 'no', 'without', 'rights', 'reserved',
        'distribution', 'redistribution', 'selling', 'sales', 'forbidden', 'internal', 'private',
    }:
        return False
    # Conventional personal names, initials, a short organization name, or a
    # single account handle. Sentence punctuation is not an attribution.
    words = holder.split(' ')
    valid_word = lambda word: (word in {'Inc.', 'Ltd.'}
                              or bool(re.fullmatch(r'[A-Z]\.', word))
                              or bool(re.fullmatch(r'[^\W\d_][^\W\d_\x27’-]*', word)) and word[0].isupper())
    return bool(0 < len(words) <= 6 and all(valid_word(word) for word in words)
                or re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', holder))


def _load(result, resources, root, expected):
    if root is None and expected is None:
        return None
    if root is None or not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('source_config')
    root = Path(root)
    if not root.is_absolute() or root.resolve(strict=True) != root or not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('source_root')
    raw = _read(root, 'profile.json', 2 * 1024 * 1024)
    if _sha(raw) != expected:
        raise ValueError('source_profile_hash')
    document = strict_json(raw)
    if isinstance(document, dict) and document.get('schema_version') == 'openguard-auto-npm-cache/1':
        return _load_cache(result, resources, root, CacheProfile.model_validate(document))
    profile = Profile.model_validate(document)
    binding = result['binding']
    if (profile.data_scope, profile.scan_id, profile.facts_hash, profile.project_revision) != (
            result['data_scope'], binding['scan_id'], binding['facts_hash'], binding['project_revision']):
        raise ValueError('source_binding')
    result_rows = {r['subject']['resource_id']: r for r in result['resources']}
    if len(result_rows) != len(result['resources']) or len(profile.packages) != len(result_rows):
        raise ValueError('source_closure')
    output = {}
    for item in profile.packages:
        rid = item.subject.resource_id
        if rid in output or rid not in result_rows or rid not in resources:
            raise ValueError('source_resource')
        resource = resources[rid]
        if (item.subject.model_dump() != result_rows[rid]['subject'] or resource.version != item.subject.version
                or resource.name != item.name or resource.purl != item.purl
                or len(set(item.evidence_ids)) != len(item.evidence_ids)
                or sorted(item.evidence_ids) != sorted(resource.evidence_ids)):
            raise ValueError('source_resource_binding')
        output[rid] = _package_content(item, root)
    if set(output) != set(result_rows):
        raise ValueError('source_closure')
    return output


def _package_content(item, root):
    """The same complete capture validation is used by both explicit modes."""
    if item.error_code is not None and not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', item.error_code):
        raise ValueError('unsafe_error_code')
    if item.status != 'FETCHED':
        # Preserve a failed capture's already-observed bytes for audit, but
        # never consume partial evidence as a successful package review.
        for receipt, maximum in [(item.metadata, 1024 * 1024), (item.tarball, 8 * 1024 * 1024)]:
            if receipt is not None:
                _npm_url(receipt.url)
                _pinned_file(root, receipt, maximum)
        for member in item.members:
            _pinned_file(root, member, 1024 * 1024)
        return item, None, None, {}
    if item.metadata is None or item.tarball is None or item.error_code is not None:
        raise ValueError('source_receipt_missing')
    if not PACKAGE_NAME.fullmatch(item.name) or item.subject.version is None:
        raise ValueError('source_coordinate')
    metadata_path = _npm_url(item.metadata.url); _npm_url(item.tarball.url)
    if metadata_path not in {'/' + item.name + '/' + item.subject.version,
                             '/' + quote(item.name, safe='') + '/' + item.subject.version}:
        raise ValueError('source_version_url')
    meta_raw = _pinned_file(root, item.metadata, 1024 * 1024)
    tar_raw = _pinned_file(root, item.tarball, 8 * 1024 * 1024)
    meta = strict_json(meta_raw)
    if not isinstance(meta, dict) or (meta.get('name'), meta.get('version')) != (item.name, item.subject.version):
        raise ValueError('metadata_identity')
    dist = meta.get('dist')
    if not isinstance(dist, dict) or dist.get('tarball') != item.tarball.url:
        raise ValueError('dist_identity')
    integrity, shasum = dist.get('integrity'), dist.get('shasum')
    valid_sri = {'sha512-' + base64.b64encode(hashlib.sha512(tar_raw).digest()).decode(),
                 'sha1-' + base64.b64encode(hashlib.sha1(tar_raw).digest()).decode()}
    if integrity is not None and integrity not in valid_sri:
        raise ValueError('dist_integrity')
    if shasum is not None and shasum != hashlib.sha1(tar_raw).hexdigest():
        raise ValueError('dist_shasum')
    if integrity is None and shasum is None:
        raise ValueError('dist_digest_missing')
    found = _members(tar_raw)
    records = {m.member: m for m in item.members}
    if len(records) != len(item.members) or set(records) != set(found):
        raise ValueError('source_member_closure')
    for name, content in found.items():
        if _pinned_file(root, records[name], 1024 * 1024) != content:
            raise ValueError('source_member_mismatch')
    package = strict_json(found['package/package.json'])
    if not isinstance(package, dict) or (package.get('name'), package.get('version')) != (item.name, item.subject.version):
        raise ValueError('package_identity')
    if 'deprecated' in meta and not isinstance(meta['deprecated'], str):
        raise ValueError('deprecated_type')
    return item, meta, package, found


def _npm_purl(name, version, purl):
    return (isinstance(name, str) and PACKAGE_NAME.fullmatch(name) is not None
            and isinstance(version, str) and bool(version)
            and purl in {f'pkg:npm/{name}@{version}', f'pkg:npm/{quote(name, safe="/")}@{version}'})


def _load_cache(result, resources, root, cache):
    """Project separately verified capture bytes onto current exact coordinates.

    The pinned cache manifest is the explicit administrative opt-in. The original
    v1 profile remains byte-identical and is not relabelled as a current scan.
    No historical subject, evidence, usage, result, or user assertion is copied.
    Missing and mismatched coordinates remain unavailable. All captures,
    including unused ones, retain the normal archive/SRI/member checks.
    """
    raw = _pinned_file(root, cache.anchor, 2 * 1024 * 1024)
    profile = Profile.model_validate(strict_json(raw))
    if cache.data_scope != result['data_scope'] or profile.data_scope != cache.data_scope:
        raise ValueError('cache_scope')
    coordinates, original_ids = {}, set()
    for item in profile.packages:
        coordinate = (item.name, item.subject.version)
        if (coordinate in coordinates or item.subject.resource_id in original_ids
                or len(set(item.evidence_ids)) != len(item.evidence_ids)):
            raise ValueError('cache_ambiguous_capture')
        if item.status == 'FETCHED' and not _npm_purl(item.name, item.subject.version, item.purl):
            raise ValueError('cache_capture_coordinate')
        original_ids.add(item.subject.resource_id)
        coordinates[coordinate] = _package_content(item, root)
    result_rows = {r['subject']['resource_id']: r for r in result['resources']}
    if len(result_rows) != len(result['resources']) or set(result_rows) != set(resources):
        raise ValueError('cache_parent_closure')
    output = CachedSources()
    for rid, row in result_rows.items():
        resource = resources[rid]
        subject = Subject.model_validate(row['subject'])
        if (resource.id != rid or resource.version != subject.version
                or len(set(resource.evidence_ids)) != len(resource.evidence_ids)
                or not set(resource.evidence_ids) <= set(row['evidence_ids'])):
            raise ValueError('cache_current_binding')
        # Validate the current identity separately; the new package starts with
        # no cached bytes or historical IDs and only gains matching captures.
        current = Package(subject=subject, name=resource.name, purl=resource.purl,
                          evidence_ids=list(resource.evidence_ids), status='UNAVAILABLE',
                          error_code='EXACT_COORDINATE_NOT_AVAILABLE', metadata=None, tarball=None, members=[])
        output[rid] = (current, None, None, {})
        if resource.ecosystem != 'npm' or not _npm_purl(resource.name, resource.version, resource.purl):
            continue
        captured = coordinates.get((resource.name, resource.version))
        if captured is None or captured[0].status != 'FETCHED':
            continue
        source, meta, package, found = captured
        if resource.source_url is not None and resource.source_url != source.tarball.url:
            continue
        current = Package(subject=subject, name=resource.name, purl=resource.purl,
                          evidence_ids=list(resource.evidence_ids), status='FETCHED', error_code=None,
                          metadata=source.metadata, tarball=source.tarball, members=source.members)
        output[rid] = (current, meta, package, found)
    return output


def project(result: dict, resources: dict, *, root=None, profile_sha256=None, materials=(), declared_licenses=None):
    """Pure deterministic view of exact official package coordinates and text."""
    try:
        sources = _load(result, resources, root, profile_sha256)
        if declared_licenses is not None and set(declared_licenses) != {r['subject']['resource_id'] for r in result['resources']}:
            raise ValueError('declared_license_closure')
        rows, material_count = [], 0
        for current in sorted(result['resources'], key=lambda r: r['subject']['resource_id']):
            subject = current['subject']; rid = subject['resource_id']; resource = resources[rid]
            row = {'subject': dict(subject), 'name': resource.name, 'license_expression': None,
                   'state': 'UNAVAILABLE', 'priority': 'manual', 'artifact_binding': 'NOT_ESTABLISHED',
                   # The result closure also includes its linked license
                   # evidence. Profile binding remains Component-specific.
                   'conditions': [], 'reasons': [], 'evidence_ids': list(current['evidence_ids']),
                   'source_refs': [], 'members': [], 'maintenance_deprecated': False,
                   'applicability_review': 'NOT_SIGNED'}
            rows.append(row)
            if resource.ecosystem != 'npm':
                row.update(state='OUTSIDE_NPM', reasons=['该资源不属于本轮官方 npm 发行材料核验范围。'])
                continue
            if sources is None or sources[rid][0].status != 'FETCHED':
                row['reasons'] = ['该精确版本的官方发行材料未取得，保留证据缺口。']
                continue
            item, meta, package, found = sources[rid]
            row['source_refs'] = [{'kind': kind, 'url': r.url, 'sha256': r.sha256}
                                  for kind, r in [('metadata', item.metadata), ('tarball', item.tarball)]]
            legal = {name: raw for name, raw in found.items() if name != 'package/package.json'}
            row['members'] = [{'member': name, 'sha256': _sha(raw)} for name, raw in sorted(legal.items())]
            material_count += len(legal)
            declaration = meta.get('license')
            if isinstance(declaration, str) and re.fullmatch(r'[A-Za-z0-9.+() -]{1,100}', declaration):
                row['license_expression'] = declaration
            row.update(state='NONSTANDARD', reasons=['发行材料已绑定；条款尚未满足完整标准文本自动初评条件。'])
            row['maintenance_deprecated'] = bool(meta.get('deprecated', '').strip())
            purl = resource.purl
            if purl is not None and purl not in {f'pkg:npm/{resource.name}@{subject["version"]}',
                                               f'pkg:npm/{quote(resource.name, safe="/")}@{subject["version"]}'}:
                row['reasons'] = ['资源 PURL 与官方 npm 精确坐标不一致。']; continue
            if resource.source_url is not None and resource.source_url != item.tarball.url:
                row['reasons'] = ['项目解析出的发行地址与官方 npm 该版本发行包不一致。']; continue
            row['artifact_binding'] = 'RESOLVED_URL_MATCH' if resource.source_url else 'EXACT_COORDINATE_ONLY'
            if any('conflict' in gap.lower() for gap in current.get('gaps', [])):
                row['reasons'] = ['该对象存在尚未解决的证据冲突。']; continue
            declared = declared_licenses[rid] if declared_licenses is not None else None
            if declared not in (None, 'NOASSERTION', 'NONE', 'UNOBSERVED') and declared != declaration:
                row['reasons'] = ['已有对象许可声明与本轮官方发行材料不一致，保留冲突待核对。']; continue
            bound = [(m, raw) for m, raw in materials if m['subject'] == subject]
            if any(LEGAL_NAME.fullmatch(m['filename']) and _sha(raw) not in {_sha(v) for v in legal.values()}
                   for m, raw in bound):
                row['reasons'] = ['已保存材料与本轮发行原件不一致，须核对附加条件或冲突。']; continue
            if any(PurePosixPath(name).name.lower().startswith('notice') for name in legal):
                row['reasons'] = ['发行包包含附加 NOTICE，须先核对其独立条款和履行要求。']; continue
            texts = [classify_text(raw) for raw in legal.values()]
            root_texts = [classify_text(raw) for name, raw in legal.items() if len(PurePosixPath(name).parts) == 2]
            if (declaration not in ('MIT', 'ISC') or package.get('license') != declaration
                    or not root_texts or any(t is None for t in texts) or set(texts) != {declaration}):
                continue
            row['state'] = 'CONDITIONAL'
            row['priority'] = 'attention' if row['maintenance_deprecated'] else 'routine'
            row['conditions'] = (['在软件副本或实质部分中保留版权声明及完整 MIT 许可声明。']
                                 if declaration == 'MIT' else ['在所有副本中保留版权声明与 ISC 许可声明。'])
            row['conditions'].append('对外提供该精确版本时核对实际交付清单；本条不证明声明已随交付物保留。')
            row['reasons'] = ['官方精确发行包与完整标准 ' + declaration + ' 文本匹配，可按条款条件安排使用和交付。']
            if row['maintenance_deprecated']:
                row['reasons'].append('官方 npm 将此版本标记为 deprecated；建议安排维护替代评估，不据此认定存在漏洞。')
        priorities = Counter(r['priority'] for r in rows); states = Counter(r['state'] for r in rows)
        licenses = Counter(r['license_expression'] or 'UNOBSERVED' for r in rows)
        out = {'schema_version': VERSION, 'rule_version': RULE, 'result_id': result['result_id'],
               'result_sha256': result['result_sha256'], 'binding': dict(result['binding']), 'data_scope': result['data_scope'],
               'source_profile_sha256': profile_sha256, 'source_status': 'CHECKED' if sources is not None else 'NOT_CONFIGURED',
               'usage': dict(result['usage']), 'formal_effect': 'none', 'model_calls': 0,
               'applicability_review': 'NOT_SIGNED', 'resources': rows,
               'summary': {'total_resources': len(rows),
                           'priority_counts': {k: priorities[k] for k in ('routine', 'attention', 'manual')},
                           'state_counts': {k: states[k] for k in ('CONDITIONAL', 'NONSTANDARD', 'UNAVAILABLE', 'OUTSIDE_NPM')},
                           'source_packages': sum(bool(r['source_refs']) for r in rows), 'license_materials': material_count,
                           'license_groups': [{'license': k, 'count': v} for k, v in sorted(licenses.items())],
                           'maintenance_count': sum(r['maintenance_deprecated'] for r in rows)},
               'limitations': list(LIMITATIONS)}
        if isinstance(sources, CachedSources):
            out['limitations'].append('本次按当前资源的精确 npm 坐标复用历史获取回执和原始字节；未重新联网获取，不继承旧扫描的对象、用途声明或许可结论。')
        out['review_id'] = 'p2auto_' + digest(out)
        return out
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, ValidationError, tarfile.TarError) as exc:
        raise P2Error('p2_automatic_source_invalid', 503) from exc
