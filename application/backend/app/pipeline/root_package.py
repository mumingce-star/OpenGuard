"""Observe the scanned root npm package itself, never inherit it to dependencies.

The existing dependency mapper intentionally maps dependency declarations only.
This pipeline adapter adds a separate application identity from a complete,
hash-bound root package.json and an optional explicit pending license declaration.
It does not read or execute package scripts, fetch npm, inspect installed modules,
or attest installation, delivery scope, source admission or license applicability.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
import uuid

from app.domain.models import Component, Evidence, HashValue, ProducerRef
from app.ingestion import ReadOnlyScanSession
from app.licenses import normalize_license
from app.pipeline.manifest_licenses import ManifestLicenseBinding, _bounded, _pairs
from app.scanners import JavascriptP0MappingResult
from app.scanners.javascript_manifest import _exact, _name

_NAMESPACE = uuid.UUID('781ec5cd-295c-4fcf-891c-13bbb606cffb')
_MAX_FILE = 2 * 1024 * 1024
_PRODUCER = ProducerRef(type='parser', name='openguard.root-package-manifest', version='1')


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
    if (type(text) is str and 1 <= len(text) <= 200
            and all(32 <= ord(char) <= 126 for char in text)):
        # Probe the existing normalizer before adding an accepted declaration
        # field. Unknown or unsupported text never opens the rule-stage gate.
        try:
            probe = normalize_license(text, evidence[:1])
        except ValueError:
            probe = None
        # This adapter accepts only one complete canonical identifier, not the
        # normalizer's broader compound/alias syntax. In particular, a malformed
        # operator sequence must not open the rule-stage gate merely because it
        # happens to leave a known token in normalized_ids.
        if (probe is not None and len(probe.normalized_ids) == 1
                and text == probe.expression == probe.normalized_ids[0]):
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
