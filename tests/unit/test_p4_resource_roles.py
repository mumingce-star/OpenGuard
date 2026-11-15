from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json

import pytest

from app.domain.models import DetectionMethod, EvidenceKind, VerificationStatus
from app.ingestion.inventory import Inventory, InventoryEntry
from app.p2b._resource_roles import BoundRoleEvidence, assess_resource_roles
from app.scanners import (
    map_javascript_manifest_result, map_python_manifest_result,
    parse_javascript_manifests, parse_python_manifests,
)
from app.scanners.external_tools import map_syft_output


DIGEST = "0" * 64
NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)


class ScanInput:
    def __init__(self, files):
        self.files = {path: value.encode() for path, value in files.items()}
        self.inventory = Inventory(tuple(
            InventoryEntry(path, len(raw), hashlib.sha256(raw).hexdigest())
            for path, raw in self.files.items()
        ), DIGEST)

    def read_bytes(self, path, *, max_bytes):
        assert len(self.files[path]) <= max_bytes
        return self.files[path]


def roles(item):
    return {entry.role: entry for entry in item.roles}


@pytest.mark.parametrize("lock_version", [2, 3])
def test_existing_npm_mapping_preserves_manifest_and_lock_locations(lock_version):
    package = {"dependencies": {"@scope/lib": "^1.0.0"}}
    lock = {"lockfileVersion": lock_version, "packages": {
        "": package, "node_modules/@scope/lib": {"version": "1.0.0"},
    }}
    parsed = parse_javascript_manifests(ScanInput({
        "package.json": json.dumps(package), "package-lock.json": json.dumps(lock),
    }))
    mapped = map_javascript_manifest_result(parsed, root_digest=DIGEST, observed_at=NOW)
    (resource,) = assess_resource_roles(mapped.components, mapped.evidence, manifests=(mapped,))
    by_role = roles(resource)
    assert resource.resource_id == mapped.components[0].id and resource.version == "1.0.0"
    assert by_role["declared"].status == "observed"
    assert {(item.source, item.locator) for item in by_role["declared"].evidence} == {
        ("manifest", "package.json:/dependencies/@scope~1lib"),
        ("lock", "package-lock.json:/packages/node_modules~1@scope~1lib/version"),
    }
    assert by_role["delivered"].status == by_role["build"].status == "unknown"


def test_lock_root_conflict_keeps_location_and_does_not_taint_other_manifest():
    parsed = parse_javascript_manifests(ScanInput({
        "a/package.json": '{"dependencies":{"lib":"1.0.0"}}',
        "a/package-lock.json": '{"lockfileVersion":3,"packages":{"":{"dependencies":{"lib":"2.0.0"}}}}',
        "b/package.json": '{"dependencies":{"other":"1.0.0"}}',
    }))
    mapped = map_javascript_manifest_result(parsed, root_digest=DIGEST, observed_at=NOW)
    result = {entry.resource_id: roles(entry) for entry in
              assess_resource_roles(mapped.components, mapped.evidence, manifests=(mapped,))}
    by_name = {item.name: result[item.id] for item in mapped.components}
    assert by_name["lib"]["declared"].status == "unknown"
    (conflict,) = by_name["lib"]["declared"].conflicts
    assert conflict.code == "lock_root_mismatch"
    assert conflict.locator.startswith("a/package-lock.json")
    assert by_name["other"]["declared"].status == "observed"


def test_exact_npm_version_conflict_keeps_rejected_lock_field():
    parsed = parse_javascript_manifests(ScanInput({
        "package.json": '{"dependencies":{"@scope/lib":"1.0.0","other":"1.0.0"}}',
        "package-lock.json": '{"lockfileVersion":3,"packages":{"node_modules/@scope/lib":{"version":"2.0.0"}}}',
    }))
    mapped = map_javascript_manifest_result(parsed, root_digest=DIGEST, observed_at=NOW)
    result = {entry.resource_id: roles(entry) for entry in
              assess_resource_roles(mapped.components, mapped.evidence, manifests=(mapped,))}
    by_name = {item.name: result[item.id] for item in mapped.components}
    assert by_name["@scope/lib"]["declared"].status == "unknown"
    (conflict,) = by_name["@scope/lib"]["declared"].conflicts
    assert conflict.locator == "package-lock.json:/packages/node_modules~1@scope~1lib/version"
    assert by_name["other"]["declared"].status == "observed"


def test_python_conflicting_pins_only_affect_the_line_bound_resource():
    parsed = parse_python_manifests(ScanInput({"requirements.txt": "pillow==11.0\npillow==12.0\nwheel==0.45\n"}))
    mapped = map_python_manifest_result(parsed, root_digest=DIGEST, observed_at=NOW)
    result = {entry.resource_id: roles(entry) for entry in
              assess_resource_roles(mapped.components, mapped.evidence, manifests=(mapped,))}
    by_name = {item.name: result[item.id] for item in mapped.components}
    assert by_name["pillow"]["declared"].status == "unknown"
    assert by_name["pillow"]["declared"].conflicts[0].locator == "requirements.txt"
    assert by_name["wheel"]["declared"].status == "observed"


@pytest.fixture
def python_inputs():
    parsed = parse_python_manifests(ScanInput({
        "pyproject.toml": '[project]\ndependencies=["Pillow==11.0"]\n[build-system]\nrequires=["wheel==0.45"]',
    }))
    mapped = map_python_manifest_result(parsed, root_digest=DIGEST, observed_at=NOW)
    raw = b"import PIL.Image\nfrom PIL import Image\nfrom .PIL import local\nimport other\n"
    source = mapped.evidence[0].model_copy(update={
        "id": "evd_325ef801-2d9f-4ac0-847a-510bc8057a32",
        "kind": EvidenceKind.FILE, "locator": "src/main.py", "excerpt": None,
        "content_hash": mapped.evidence[0].content_hash.model_copy(update={"value": hashlib.sha256(raw).hexdigest()}),
        "detected_by": DetectionMethod.AST,
    })
    return mapped, {item.name: item for item in mapped.components}, source, raw


def test_python_build_role_and_explicit_import_association(python_inputs):
    mapped, by_name, source, raw = python_inputs
    result = {entry.resource_id: roles(entry) for entry in assess_resource_roles(
        mapped.components, (*mapped.evidence, source),
        import_sources=((source, raw, {"PIL": by_name["pillow"]}),),
    )}
    imported = result[by_name["pillow"].id]["imported"]
    assert imported.status == "observed"
    assert [(item.locator, item.start_line) for item in imported.evidence] == [
        ("src/main.py", 1), ("src/main.py", 2),
    ]
    build = result[by_name["wheel"].id]["build"]
    assert build.status == "inferred"
    assert build.evidence[0].locator == "pyproject.toml:build-system.requires[0]"
    assert result[by_name["wheel"].id]["imported"].status == "unknown"


def test_syft_inventory_does_not_establish_delivery():
    mapped = map_syft_output({"artifacts": [{
        "name": "lib", "version": "1.0.0", "purl": "pkg:npm/lib@1.0.0",
        "locations": [{"path": "package-lock.json"}],
    }]}, root_digest=DIGEST, observed_at=NOW, tool_version="1.51.0")
    (item,) = assess_resource_roles(mapped.components, mapped.evidence)
    assert roles(item)["declared"].status == "inferred"
    assert roles(item)["declared"].evidence[0].source == "sbom"
    assert roles(item)["delivered"].status == "unknown"


def test_reviewed_build_and_delivery_with_conflicting_delivery(python_inputs):
    mapped, by_name, source, _ = python_inputs
    target = by_name["wheel"]
    delivery = source.model_copy(update={"locator": "release/inventory.json"})
    absent = delivery.model_copy(update={
        "id": "evd_200efe98-9ace-40f5-8ed9-a056c39755b5", "locator": "review/exclusions.json",
    })
    found = BoundRoleEvidence(target.id, target.version, "delivery", delivery.id)
    build = BoundRoleEvidence(target.id, target.version, "build", delivery.id)
    absent_fact = replace(found, evidence_id=absent.id, present=False)
    evidence = (*mapped.evidence, delivery, absent)
    for facts, expected in (((found, build), "observed"), ((found, absent_fact, build), "unknown")):
        result = assess_resource_roles(mapped.components, evidence, facts=facts)
        status = roles(next(item for item in result if item.resource_id == target.id))
        assert status["build"].status == "observed"
        assert status["delivered"].status == expected
        assert bool(status["delivered"].conflicts) == (expected == "unknown")


@pytest.mark.parametrize("invalid", ["version", "unverified", "hash"])
def test_bad_role_inputs_are_rejected(python_inputs, invalid):
    mapped, by_name, source, raw = python_inputs
    target = by_name["pillow"]
    fact = BoundRoleEvidence(target.id, target.version, "delivery", source.id)
    if invalid == "version":
        fact = replace(fact, version="9.9")
    elif invalid == "unverified":
        source = source.model_copy(update={"verification_status": VerificationStatus.PENDING})
    if invalid == "hash":
        with pytest.raises(ValueError, match="invalid_import_source"):
            assess_resource_roles(mapped.components, (*mapped.evidence, source),
                                  import_sources=((source, raw + b"# tampered", {"PIL": target}),))
    else:
        with pytest.raises(ValueError, match="unresolved_role_fact"):
            assess_resource_roles(mapped.components, (*mapped.evidence, source), facts=(fact,))
