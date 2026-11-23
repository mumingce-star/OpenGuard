"""Observe scanned npm and Python root packages apart from their dependencies.

The existing dependency mapper intentionally maps dependency declarations only.
This pipeline adapter adds a separate application identity from a complete,
hash-bound root manifest and an optional explicit pending license declaration.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
import tomllib
import uuid

from packaging.utils import canonicalize_name
from packaging.version import Version

from app.domain.models import Component, Evidence, HashValue, ProducerRef
from app.ingestion import ReadOnlyScanSession
from app.licenses import normalize_license
from app.pipeline.manifest_licenses import ManifestLicenseBinding, _bounded, _pairs
from app.scanners import JavascriptP0MappingResult, PythonP0MappingResult
from app.scanners.javascript_manifest import _exact, _name

_NAMESPACE = uuid.UUID('781ec5cd-295c-4fcf-891c-13bbb606cffb')
_MAX_FILE = 2 * 1024 * 1024
_PRODUCER = ProducerRef(type='parser', name='openguard.root-package-manifest', version='1')


def _single_standard_license(text, identity_evidence):
    if (type(text) is not str or not 1 <= len(text) <= 200
            or any(not 32 <= ord(char) <= 126 for char in text)):
        return False
    try:
        probe = normalize_license(text, identity_evidence)
    except ValueError:
        return False
    # The shared normalizer also handles aliases and compound expressions. Root
    # declarations only admit one complete canonical identifier.
    return len(probe.normalized_ids) == 1 and text == probe.expression == probe.normalized_ids[0]


def collect_root_package(session: ReadOnlyScanSession, mapping: JavascriptP0MappingResult | None,
                         observed_at: datetime, *, total_read_budget: int):
    """Return enriched mapping plus zero/one license binding; fail closed on input.

    All bytes come from the existing lifecycle-bound descriptor capability. The
    conservative shared-read check reserves the original parser reads and lock
    enrichment before this extra root-manifest read can consume their budget.
    """
    if mapping is None:
        return mapping, ()
    inventory = {e.relative_path: e for e in session.inventory.entries}
    entry = inventory.get('package.json')
    if entry is None or not 0 < entry.size_bytes <= _MAX_FILE:
        return mapping, ()
    reserve = sum(e.size_bytes for e in inventory.values()) + sum(
        e.size_bytes for p, e in inventory.items() if p.rsplit('/', 1)[-1] == 'package-lock.json')
    if reserve + entry.size_bytes > total_read_budget:
        return mapping, ()
    try:
        raw = session.read_bytes('package.json', max_bytes=_MAX_FILE)
        if (type(raw) is not bytes or len(raw) != entry.size_bytes
                or hashlib.sha256(raw).hexdigest() != entry.sha256):
            return mapping, ()
        package = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        _bounded(package)
        if type(package) is not dict or not _name(package.get('name')):
            return mapping, ()
        version = _exact(package.get('version'))
        if version is None:
            return mapping, ()
    except (ValueError, UnicodeError, OSError, RecursionError):
        return mapping, ()

    def identity(prefix, fields):
        return prefix + str(uuid.uuid5(_NAMESPACE, json.dumps(
            [session.inventory.root_digest, 'package.json', entry.sha256, *fields],
            ensure_ascii=False, sort_keys=True, separators=(',', ':'))))

    evidence = []
    def field(name, value):
        item = Evidence(id=identity('evd_', [name, value]), kind='manifest_field',
            locator='package.json:/' + name, excerpt=json.dumps(value, ensure_ascii=False),
            content_hash=HashValue(algorithm='sha256', value=entry.sha256),
            detected_by='manifest_parser', producer=_PRODUCER, observed_at=observed_at,
            verification_status='pending')
        evidence.append(item)
        return item

    name = package['name']
    field('name', name)
    field('version', package['version'])
    root_id = identity('cmp_', [name, version, 'root-application'])
    bindings = ()
    text = package.get('license')
    if _single_standard_license(text, evidence[:1]):
        license_evidence = field('license', text)
        expression = normalize_license(text, [license_evidence])
        bindings = (ManifestLicenseBinding(root_id, expression, license_evidence),)
    purl_name = name.replace('@', '%40', 1) if name.startswith('@') else name
    root = Component(id=root_id, name=name, version=version, ecosystem='npm',
        component_type='application', purl=f'pkg:npm/{purl_name}@{version}',
        license_expression_id=None, evidence_ids=sorted(e.id for e in evidence),
        detected_by=['manifest_parser'], confidence=1.0)
    return replace(mapping, components=tuple(sorted([*mapping.components, root], key=lambda c: c.id)),
                   evidence=tuple(sorted([*mapping.evidence, *evidence], key=lambda e: e.id))), bindings


def collect_python_root_package(session: ReadOnlyScanSession, python_mapping: PythonP0MappingResult | None,
                                observed_at: datetime, *, total_read_budget: int):
    """Map one sealed static PyPI root within the caller's reserved read budget."""
    if python_mapping is None:
        return python_mapping, ()
    path = 'pyproject.toml'
    entry = next((item for item in session.inventory.entries if item.relative_path == path), None)
    if entry is None or not 0 < entry.size_bytes <= min(_MAX_FILE, total_read_budget, session.remaining_read_bytes):
        return python_mapping, ()
    try:
        raw = session.read_bytes(path, max_bytes=_MAX_FILE)
        if (type(raw) is not bytes or len(raw) != entry.size_bytes
                or hashlib.sha256(raw).hexdigest() != entry.sha256):
            return python_mapping, ()
        document = tomllib.loads(raw.decode('utf-8'))
        _bounded(document)
        if 'project' in document:
            # A PEP 621 table controls the root even if its identity is invalid.
            # Falling back in that case could attach a different owner's metadata.
            package = document['project']
            if type(package) is not dict:
                return python_mapping, ()
            dynamic = package.get('dynamic', [])
            if (type(dynamic) is not list or any(type(field) is not str or not field for field in dynamic)
                    or len(set(dynamic)) != len(dynamic) or {'name', 'version'} & set(dynamic)):
                return python_mapping, ()
            table = '/project'
            declaration = package.get('license') if 'license' not in dynamic else None
        else:
            tool = document.get('tool', {})
            package = tool.get('poetry') if type(tool) is dict else None
            if type(package) is not dict:
                return python_mapping, ()
            table = '/tool/poetry'
            declaration = package.get('license')
        name = package.get('name')
        raw_version = package.get('version')
        if (type(name) is not str or not 1 <= len(name) <= 200
                or type(raw_version) is not str or not 1 <= len(raw_version) <= 200
                or raw_version.strip() != raw_version):
            return python_mapping, ()
        canonical_name = canonicalize_name(name, validate=True)
        version = str(Version(raw_version))
        if len(version) > 200:
            return python_mapping, ()
    except (ValueError, OSError, RecursionError):
        return python_mapping, ()

    def identity(prefix, fields):
        return prefix + str(uuid.uuid5(_NAMESPACE, json.dumps(
            [session.inventory.root_digest, path, entry.sha256, table, *fields],
            ensure_ascii=False, sort_keys=True, separators=(',', ':'))))

    evidence = []

    def field(name, value):
        item = Evidence(id=identity('evd_', [name, value]), kind='manifest_field',
            locator=f'{path}:{table}/{name}', excerpt=json.dumps(value, ensure_ascii=False),
            content_hash=HashValue(algorithm='sha256', value=entry.sha256),
            detected_by='manifest_parser', producer=_PRODUCER, observed_at=observed_at,
            verification_status='pending')
        evidence.append(item)
        return item

    field('name', name)
    field('version', raw_version)
    root_id = identity('cmp_', [name, version, 'root-application'])
    license_field = 'license'
    if table == '/project' and type(declaration) is dict and set(declaration) == {'text'}:
        declaration = declaration['text']
        license_field = 'license/text'
    bindings = ()
    if _single_standard_license(declaration, evidence[:1]):
        license_evidence = field(license_field, declaration)
        expression = normalize_license(declaration, [license_evidence])
        bindings = (ManifestLicenseBinding(root_id, expression, license_evidence),)
    root = Component(id=root_id, name=name, version=version, ecosystem='pypi',
        component_type='application', purl=f'pkg:pypi/{canonical_name}@{version}',
        license_expression_id=None, evidence_ids=sorted(e.id for e in evidence),
        detected_by=['manifest_parser'], confidence=1.0)
    return replace(python_mapping, components=tuple(sorted([*python_mapping.components, root], key=lambda c: c.id)),
                   evidence=tuple(sorted([*python_mapping.evidence, *evidence], key=lambda e: e.id))), bindings
