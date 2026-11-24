"""Bounded Go declarations and checksum observations from sealed scan bytes."""

from __future__ import annotations

import base64
import hashlib
import io
import re
from urllib.parse import quote

from .dependency_observations import (
    MAX_BYTES,
    MAX_EDGES,
    MAX_NODES,
    DependencyObservations,
    Gap,
    Node,
    _result,
    relative_path,
)


_HOST = re.compile(r"[a-z0-9][a-z0-9.-]*")
_MODULE_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")
_RESERVED_SEGMENT = re.compile(r"(?:aux|com[1-9]|con|lpt[1-9]|nul|prn|.*~[0-9]+)", re.I)
_NUMBER = r"(?:0|[1-9][0-9]*)"
_VERSION = re.compile(
    rf"v{_NUMBER}\.{_NUMBER}\.{_NUMBER}"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+incompatible)?"
)
_BLOCK_OPEN = re.compile(r"([a-z][a-z0-9]*)[ \t]*\(")
_UNRESOLVED = {
    "replace": "go_replace_not_evaluated",
    "exclude": "go_exclude_not_evaluated",
    "retract": "go_retract_not_evaluated",
}
_METADATA_DIRECTIVES = {"go", "godebug", "ignore", "module", "tool", "toolchain"}


def valid_go_module(value: object) -> bool:
    """Validate the literal, case-sensitive module identity (not a resolved path)."""
    if type(value) is not str or not 0 < len(value) <= 200:
        return False
    host, *segments = value.split("/")
    if not _HOST.fullmatch(host) or "." not in host or any(not label for label in host.split(".")):
        return False
    return all(
        _MODULE_SEGMENT.fullmatch(segment)
        and not segment.startswith(".")
        and not segment.endswith(".")
        and not _RESERVED_SEGMENT.fullmatch(segment.partition(".")[0])
        for segment in segments
    )


def valid_go_version(value: object) -> bool:
    """Validate canonical Go version syntax without resolving pseudo revisions."""
    if type(value) is not str or not 0 < len(value) <= 200:
        return False
    match = _VERSION.fullmatch(value)
    if match is None:
        return False
    prerelease = match[1]
    return prerelease is None or all(
        not part.isdecimal() or part == "0" or not part.startswith("0")
        for part in prerelease.split(".")
    )


def _purl(module: str, version: str) -> str:
    return f"pkg:golang/{quote(module, safe='/')}@{quote(version, safe='')}"


def _text(raw: bytes, path: str) -> str:
    relative_path(path)
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("input_limit_exceeded")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_go_document") from exc
    if any((ord(char) < 32 and char not in "\n\r\t") or ord(char) == 127 for char in text):
        raise ValueError("invalid_go_document")
    return text


def _lines(text: str, *, allow_comments: bool):
    count = 0
    for number, line in enumerate(io.StringIO(text), 1):
        line = line.removesuffix("\n").removesuffix("\r")
        if "\r" in line:
            raise ValueError("invalid_go_document")
        if allow_comments:
            line = line.partition("//")[0]
        line = line.strip(" \t")
        if not line:
            continue
        count += 1
        if count > MAX_EDGES:
            raise ValueError("structure_limit_exceeded")
        yield number, line


def _literal(value: str) -> str:
    if len(value) >= 2 and value[0] in ('"', '`') and value[0] == value[-1]:
        return value[1:-1]
    return value


def parse_go_mod(raw: bytes, *, path: str = "go.mod") -> DependencyObservations:
    """Observe require directives. Replacement or exclusion is never evaluated."""
    nodes, gaps = [], []
    versions_by_module: dict[str, set[str]] = {}
    block = None
    for number, line in _lines(_text(raw, path), allow_comments=True):
        if line == ")":
            if block is None:
                raise ValueError("invalid_go_mod_block")
            block = None
            continue

        opening = _BLOCK_OPEN.fullmatch(line)
        if opening is not None:
            if block is not None:
                raise ValueError("invalid_go_mod_block")
            block = opening[1]
            if block in _UNRESOLVED:
                gaps.append(Gap(_UNRESOLVED[block], f"{path}:/{block}/{number}"))
            elif block not in _METADATA_DIRECTIVES and block != "require":
                gaps.append(Gap("go_directive_not_evaluated", f"{path}:/directives/{number}"))
            continue

        parts = re.split(r"[ \t]+", line)
        if block is None:
            directive, *fields = parts
            if directive in _UNRESOLVED:
                gaps.append(Gap(_UNRESOLVED[directive], f"{path}:/{directive}/{number}"))
            elif directive not in _METADATA_DIRECTIVES and directive != "require":
                gaps.append(Gap("go_directive_not_evaluated", f"{path}:/directives/{number}"))
        else:
            directive, fields = block, parts
        if directive != "require":
            continue

        loc = f"{path}:/require/{number}"
        if len(fields) != 2:
            gaps.append(Gap("go_require_invalid", loc))
            continue
        module, version = map(_literal, fields)
        if not valid_go_module(module) or not valid_go_version(version):
            gaps.append(Gap("go_require_invalid", loc))
            continue
        seen = versions_by_module.setdefault(module, set())
        if version in seen:
            gaps.append(Gap("duplicate_dependency_entry", loc))
            continue
        if seen:
            gaps.append(Gap("go_require_version_ambiguous", loc))
        seen.add(version)
        if len(nodes) >= MAX_NODES:
            raise ValueError("graph_limit_exceeded")
        nodes.append(Node(f"go-mod:{number}", module, version, _purl(module, version), loc, "manifest",
                          excerpt=fields[1]))
    if block is not None:
        raise ValueError("invalid_go_mod_block")
    return _result("go-mod/1", path, hashlib.sha256(raw).hexdigest(), nodes, [], gaps)


def _valid_checksum(value: str) -> bool:
    if len(value) != 47 or not value.startswith("h1:"):
        return False
    encoded = value[3:]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError:
        return False
    return len(decoded) == 32 and base64.b64encode(decoded).decode("ascii") == encoded


def parse_go_sum(raw: bytes, *, path: str = "go.sum") -> DependencyObservations:
    """Observe checksummed module versions without trusting or resolving them."""
    nodes: dict[tuple[str, str], tuple[Node, str]] = {}
    contradictory: set[tuple[str, str]] = set()
    gaps = []
    for number, line in _lines(_text(raw, path), allow_comments=False):
        loc = f"{path}:/checksums/{number}"
        fields = re.split(r"[ \t]+", line)
        if len(fields) != 3:
            gaps.append(Gap("go_sum_entry_invalid", loc))
            continue
        module, field, checksum = fields
        version = field.removesuffix("/go.mod")
        if not valid_go_module(module) or not valid_go_version(version) or not _valid_checksum(checksum):
            gaps.append(Gap("go_sum_entry_invalid", loc))
            continue
        if field != version:
            continue  # A go.mod digest is not the module archive's digest.

        key = (module, version)
        if key in contradictory:
            continue
        previous = nodes.get(key)
        if previous is not None:
            if previous[1] != checksum:
                gaps.append(Gap("go_sum_hash_conflict", loc))
                contradictory.add(key)
                del nodes[key]
            continue
        if len(nodes) + len(contradictory) >= MAX_NODES:
            raise ValueError("graph_limit_exceeded")
        nodes[key] = (Node(f"go-sum:{number}", module, version, _purl(module, version), loc, "lock"), checksum)
    return _result("go-sum/1", path, hashlib.sha256(raw).hexdigest(),
                   [node for node, _ in nodes.values()], [], gaps)
