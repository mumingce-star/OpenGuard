"""Cargo observations from test bytes, with no Cargo invocation."""

import hashlib

import pytest

from app.scanners import cargo_dependencies as cargo


MANIFEST = b'''
[package]
name = "Demo_Root"
version = "2.1.0-alpha.1+revision.7"
license = "MIT"

[dependencies]
serde = "=1.2.3"
renamed = { package = "Real-Crate", version = "=1.2.3-pre.2" }
plain = "1.0"
caret = "^1.2.3"
tilde = "~1.2"
wildcard = "*"
bounded = ">=1.0, <2.0"
metadata = "=1.2.3+build.7"
inherited = { workspace = true }
local = { path = "../local", version = "=1.2.3" }
remote = { git = "https://example.invalid/source", version = "=1.2.3" }
registry = { registry = "custom", version = "=1.2.3" }

[dev-dependencies.subtable]
package = "dev-real"
version = "=2.1.0"

[build-dependencies]
build = "=0.0.0"
'''


def test_cargo_manifest_preserves_exact_and_range_observation_locations():
    result = cargo.parse_cargo_toml(MANIFEST)
    assert result.source_sha256 == hashlib.sha256(MANIFEST).hexdigest()
    assert result.format == "cargo-toml/1"
    assert result.root is not None
    assert result.root.name == "Demo_Root"
    assert result.root.version == "2.1.0-alpha.1+revision.7"
    assert result.root.purl == "pkg:cargo/Demo_Root@2.1.0-alpha.1%2Brevision.7"
    assert result.root.fields == (("/package/name", "Demo_Root"),
                                  ("/package/version", "2.1.0-alpha.1+revision.7"))
    assert result.root.license == ("/package/license", "MIT")
    nodes = {item.name: item for item in result.nodes}
    assert (nodes["serde"].version, nodes["serde"].purl, nodes["serde"].excerpt) == (
        "1.2.3", "pkg:cargo/serde@1.2.3", "=1.2.3",
    )
    assert nodes["serde"].locator == "Cargo.toml:/dependencies/serde"
    assert nodes["Real-Crate"].locator == "Cargo.toml:/dependencies/renamed/version"
    assert nodes["Real-Crate"].purl == "pkg:cargo/Real-Crate@1.2.3-pre.2"
    assert nodes["dev-real"].locator == "Cargo.toml:/dev-dependencies/subtable/version"
    assert nodes["build"].locator == "Cargo.toml:/build-dependencies/build"
    assert nodes["build"].version == "0.0.0"
    for name, selector in (("plain", "1.0"), ("caret", "^1.2.3"), ("tilde", "~1.2"),
                           ("wildcard", "*"), ("bounded", ">=1.0, <2.0"), ("metadata", "=1.2.3+build.7")):
        assert (nodes[name].version, nodes[name].purl, nodes[name].excerpt) == (None, None, selector)
    for name in ("inherited", "local", "remote", "registry"):
        assert nodes[name].version is None and nodes[name].purl is None
    assert nodes["inherited"].locator == "Cargo.toml:/dependencies/inherited"
    assert {gap.code for gap in result.gaps} == {
        "cargo_workspace_dependency_not_evaluated", "cargo_path_dependency_not_evaluated",
        "cargo_git_dependency_not_evaluated", "cargo_registry_dependency_not_evaluated",
    }
    assert result.status == "partial" and result.edges == ()


def test_nested_manifest_cannot_establish_root():
    result = cargo.parse_cargo_toml(MANIFEST, path="workspace/member/Cargo.toml")
    assert result.root is None
    assert all(node.locator.startswith("workspace/member/Cargo.toml:/") for node in result.nodes)


@pytest.mark.parametrize("version", ['{ workspace = true }', '"01.2.3"', '"1.2"', '"1.2.3-pre.01"', "7", '""'])
def test_dynamic_or_invalid_root_still_preserves_dependencies(version):
    raw = f'[package]\nname = "root"\nversion = {version}\n[dependencies]\nstandalone = "=3.2.1"\n'.encode()
    result = cargo.parse_cargo_toml(raw)
    assert result.root is None
    assert result.nodes[0].purl == "pkg:cargo/standalone@3.2.1"
    assert result.gaps[0].code == "cargo_root_identity_unresolved"


def test_license_file_does_not_produce_a_license_declaration():
    raw = b'[package]\nname = "root"\nversion = "1.2.3"\nlicense-file = "LICENSE"\n'
    result = cargo.parse_cargo_toml(raw)
    assert result.root is not None and result.root.license is None


LOCK = b'''
version = 4

[[package]]
name = "root"
version = "1.0.0"
dependencies = [
  "Some-Crate",
  "Some-Crate 2.0.0",
  "shared 1.0.0",
  "shared 1.0.0 (git+https://example.invalid/shared#1234)",
  "missing",
  "invalid-not-a-version bad",
]

[[package]]
name = "Some-Crate"
version = "1.0.0"
source = "registry+https://example.invalid/index"

[[package]]
name = "Some-Crate"
version = "2.0.0"
source = "registry+https://example.invalid/index"

[[package]]
name = "shared"
version = "1.0.0"
source = "registry+https://example.invalid/index"

[[package]]
name = "shared"
version = "1.0.0"
source = "git+https://example.invalid/shared#1234"
'''


@pytest.mark.parametrize("version", [3, 4])
def test_cargo_lock_edges_bind_only_to_an_unambiguous_saved_instance(version):
    raw = LOCK.replace(b"version = 4", f"version = {version}".encode(), 1)
    result = cargo.parse_cargo_lock(raw, path="dev/Cargo.lock")
    assert result.format == f"cargo-lock/{version}"
    assert result.root is None
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.nodes[2].purl == "pkg:cargo/Some-Crate@2.0.0"
    assert result.nodes[2].locator == "dev/Cargo.lock:/package/2/version"
    assert [(e.child, e.locator) for e in result.edges] == [
        ("cargo-lock:2", "dev/Cargo.lock:/package/0/dependencies/1"),
        ("cargo-lock:4", "dev/Cargo.lock:/package/0/dependencies/3"),
    ]
    assert [node.source_kind for node in result.nodes] == ["workspace", "registry", "registry", "registry", "git"]
    assert {gap.code for gap in result.gaps} == {
        "dependency_ambiguous", "dependency_unresolved", "dependency_invalid",
    }


@pytest.mark.parametrize("version", [b"1", b"2", b"5", b"true", b'"4"'])
def test_cargo_lock_rejects_unknown_or_untyped_versions(version):
    with pytest.raises(ValueError, match="unsupported_cargo_lock_version"):
        cargo.parse_cargo_lock(b"version = " + version + b"\n")


def test_unusable_lock_source_does_not_emit_a_package_observation():
    raw = b'''version = 3
[[package]]
name = "demo"
version = "3.4.5"
source = "registry+ftp://example.invalid/index"
'''
    result = cargo.parse_cargo_lock(raw)
    assert result.nodes == ()
    assert [(gap.code, gap.locator) for gap in result.gaps] == [("source_invalid", "Cargo.lock:/package/0/source")]


def test_limits_apply_to_attempted_cargo_nodes_and_references(monkeypatch):
    monkeypatch.setattr(cargo, "MAX_NODES", 2)
    with pytest.raises(ValueError, match="graph_limit_exceeded"):
        cargo.parse_cargo_toml(MANIFEST)
    with pytest.raises(ValueError, match="invalid_cargo_packages"):
        cargo.parse_cargo_lock(LOCK)
    monkeypatch.setattr(cargo, "MAX_NODES", 100)
    monkeypatch.setattr(cargo, "MAX_EDGES", 2)
    with pytest.raises(ValueError, match="graph_limit_exceeded"):
        cargo.parse_cargo_lock(LOCK)


@pytest.mark.parametrize("selector,expected", [
    ("=0.0.0", "0.0.0"), ("= 1.2.3-alpha.2", "1.2.3-alpha.2"), ("=1.2.3-alpha.02", None),
    ("=1.2.3+local.2", None), ("=1.2", None), ("1.2.3", None), (">=1.0.0", None),
])
def test_exact_cargo_version_requires_literal_equality_without_build_metadata(selector, expected):
    assert cargo.exact_cargo_dependency_version(selector) == expected
