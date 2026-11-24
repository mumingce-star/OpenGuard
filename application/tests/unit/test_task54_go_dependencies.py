"""Offline Go parser contracts over synthetic, in-memory fixture bytes."""

import base64
import hashlib

import pytest

from app.scanners import go_dependencies as parser


def checksum(value):
    return "h1:" + base64.b64encode(bytes([value]) * 32).decode("ascii")


def test_go_mod_require_forms_preserve_literal_identity_and_never_make_a_root():
    raw = (
        b"module example.test/root\r\n"
        b"go 1.24\r\n"
        b"require example.test/Org/One v1.2.3 // indirect\r\n"
        b"require (\r\n"
        b'  "example.test/Org/Two" "v0.0.0-20240416150000-abcdef123456"\r\n'
        b"  example.test/three v3.1.0+incompatible\r\n"
        b")\r\n"
        b"replace example.test/Org/One => ../one\r\n"
        b"exclude (\r\n"
        b"  example.test/Org/One v1.2.2\r\n"
        b")\r\n"
        b"retract v1.0.0 // old release\r\n"
    )
    result = parser.parse_go_mod(raw, path="sub/go.mod")
    assert result.format == "go-mod/1"
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert [(node.name, node.version, node.locator) for node in result.nodes] == [
        ("example.test/Org/One", "v1.2.3", "sub/go.mod:/require/3"),
        ("example.test/Org/Two", "v0.0.0-20240416150000-abcdef123456", "sub/go.mod:/require/5"),
        ("example.test/three", "v3.1.0+incompatible", "sub/go.mod:/require/6"),
    ]
    assert [node.purl for node in result.nodes] == [
        "pkg:golang/example.test/Org/One@v1.2.3",
        "pkg:golang/example.test/Org/Two@v0.0.0-20240416150000-abcdef123456",
        "pkg:golang/example.test/three@v3.1.0%2Bincompatible",
    ]
    assert result.nodes[1].excerpt == '"v0.0.0-20240416150000-abcdef123456"'
    assert {(gap.code, gap.locator) for gap in result.gaps} == {
        ("go_replace_not_evaluated", "sub/go.mod:/replace/8"),
        ("go_exclude_not_evaluated", "sub/go.mod:/exclude/9"),
        ("go_retract_not_evaluated", "sub/go.mod:/retract/12"),
    }
    assert not result.edges


def test_go_mod_reports_invalid_and_duplicate_declarations_without_guessing():
    result = parser.parse_go_mod(b"""require(
example.test/Good v1.0.0
example.test/Good v1.0.0
example.test/Good v2.0.0+incompatible
example.test/Bad v03.0.0
../escape v1.0.0
)
tool (
require example.test/not-a-dependency v1.2.0
)
""")
    assert [(node.name, node.version) for node in result.nodes] == [
        ("example.test/Good", "v1.0.0"),
        ("example.test/Good", "v2.0.0+incompatible"),
    ]
    assert {(gap.code, gap.locator) for gap in result.gaps} == {
        ("duplicate_dependency_entry", "go.mod:/require/3"),
        ("go_require_version_ambiguous", "go.mod:/require/4"),
        ("go_require_invalid", "go.mod:/require/5"),
        ("go_require_invalid", "go.mod:/require/6"),
    }


def test_go_sum_observes_archive_rows_only_and_retains_historical_versions():
    raw = (
        f"example.test/X v1.2.0/go.mod {checksum(1)}\n"
        f"example.test/X v1.2.0 {checksum(2)}\n"
        f"example.test/X v1.2.1 {checksum(3)}\n"
        f"example.test/X v1.2.1/go.mod {checksum(4)}\n"
        f"example.test/X v1.2.1 {checksum(3)}\n"
        "example.test/X v4.0.0+incompatible h1:not-a-sha256\n"
        f"example.test/Y bogus {checksum(5)}\n"
    ).encode("ascii")
    result = parser.parse_go_sum(raw, path="sub/go.sum")
    assert result.format == "go-sum/1"
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert [(node.name, node.version, node.locator) for node in result.nodes] == [
        ("example.test/X", "v1.2.0", "sub/go.sum:/checksums/2"),
        ("example.test/X", "v1.2.1", "sub/go.sum:/checksums/3"),
    ]
    assert {(gap.code, gap.locator) for gap in result.gaps} == {
        ("go_sum_entry_invalid", "sub/go.sum:/checksums/6"),
        ("go_sum_entry_invalid", "sub/go.sum:/checksums/7"),
    }
    assert not result.edges


def test_go_sum_rejects_contradictory_checksummed_identity_and_bad_padding_bits():
    noncanonical = checksum(0)[:-2] + "B="
    raw = (
        f"example.test/X v1.0.0 {checksum(0)}\n"
        f"example.test/X v1.0.0 {checksum(1)}\n"
        f"example.test/X v1.0.0 {checksum(0)}\n"
        f"example.test/Y v1.0.0 {noncanonical}\n"
        f"example.test/Z v1.0.0 {checksum(2)}\n"
    ).encode("ascii")
    result = parser.parse_go_sum(raw)
    assert [node.name for node in result.nodes] == ["example.test/Z"]
    assert {(gap.code, gap.locator) for gap in result.gaps} == {
        ("go_sum_hash_conflict", "go.sum:/checksums/2"),
        ("go_sum_entry_invalid", "go.sum:/checksums/4"),
    }


@pytest.mark.parametrize("name", [
    "../outside", "example.test//x", "example.test/a/../b", "example.test/a\\b",
    "example.test/a%2Fb", "example.test/a\x1fb", "example.test/a@v1", "example.test/.hidden",
])
def test_go_module_rejects_unsafe_identity(name):
    assert not parser.valid_go_module(name)


@pytest.mark.parametrize("version", ["1.2.3", "v1.2", "v01.2.3", "v1.2.3-01", "v1.2.3+unresolved"])
def test_go_version_rejects_noncanonical_or_unresolved_values(version):
    assert not parser.valid_go_version(version)


@pytest.mark.parametrize("raw", [b"require (\n", b")\n", b"require(\nrequire(\n)\n)\n"])
def test_malformed_require_block_fails_closed(raw):
    with pytest.raises(ValueError, match="invalid_go_mod_block"):
        parser.parse_go_mod(raw)


def test_go_parsers_reject_invalid_text_and_unsafe_locator():
    for parse in (parser.parse_go_mod, parser.parse_go_sum):
        with pytest.raises(ValueError, match="invalid_go_document"):
            parse(b"\x00")
        with pytest.raises(ValueError, match="invalid_go_document"):
            parse(b"\xff")
        with pytest.raises(ValueError, match="unsafe_source_path"):
            parse(b"", path="../outside")


def test_go_parser_enforces_input_node_and_record_budgets(monkeypatch):
    with monkeypatch.context() as check:
        check.setattr(parser, "MAX_BYTES", 3)
        with pytest.raises(ValueError, match="input_limit_exceeded"):
            parser.parse_go_mod(b"go 1.24\n")
    with monkeypatch.context() as check:
        check.setattr(parser, "MAX_NODES", 1)
        with pytest.raises(ValueError, match="graph_limit_exceeded"):
            parser.parse_go_mod(b"require example.test/x v1.0.0\nrequire example.test/y v1.0.0\n")
    with monkeypatch.context() as check:
        check.setattr(parser, "MAX_EDGES", 1)
        with pytest.raises(ValueError, match="structure_limit_exceeded"):
            parser.parse_go_sum(b"bad\nbad\n")
