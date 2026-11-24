"""Strict coordinates for the three offline ecosystem adapters."""

import json
import re
from urllib.parse import quote, unquote

MULTI_ECOSYSTEMS = frozenset({"golang", "cargo", "maven"})
MANIFEST_PRODUCER = "openguard.dependency-observations.manifest"
LOCK_PRODUCER = "openguard.dependency-observations.lock"
MANIFEST_FILENAMES = {"golang": "go.mod", "cargo": "Cargo.toml", "maven": "pom.xml"}
LOCK_FILENAMES = {"golang": "go.sum", "cargo": "Cargo.lock", "maven": "gradle.lockfile"}
MANIFEST_FORMATS = frozenset({"go-mod", "cargo-toml", "maven-pom"})
LOCK_FORMATS = frozenset({"go-sum", "cargo-lock", "gradle-lock"})

def valid_name(ecosystem, name):
    if ecosystem == "golang":
        from .go_dependencies import valid_go_module
        return valid_go_module(name)
    if ecosystem == "cargo":
        from .cargo_dependencies import valid_cargo_name
        return valid_cargo_name(name)
    if ecosystem == "maven" and isinstance(name, str):
        from .maven_dependencies import valid_maven_artifact, valid_maven_group
        group, separator, artifact = name.partition(":")
        return bool(separator and valid_maven_group(group) and valid_maven_artifact(artifact))
    return False


def valid_version(ecosystem, version):
    if ecosystem == "golang":
        from .go_dependencies import valid_go_version
        return valid_go_version(version)
    if ecosystem == "cargo":
        from .cargo_dependencies import valid_cargo_version
        return valid_cargo_version(version)
    if ecosystem == "maven":
        from .maven_dependencies import valid_maven_version
        return valid_maven_version(version)
    return False


def coordinate_key(ecosystem, name):
    separator = ":" if ecosystem == "maven" else "/"
    path = "/".join(quote(part, safe="") for part in name.split(separator))
    return f"pkg:{ecosystem}/{path}"


def exact_purl(value):
    """Return (type, logical name, version) for a validated new-type PURL."""
    if type(value) is not str or len(value) > 2048 or re.search(r"%(?![0-9A-Fa-f]{2})", value):
        return None
    match = re.fullmatch(r"pkg:(golang|cargo|maven)/([^@?#\s]+)@([^@/?#\s]+)", value, flags=re.ASCII)
    if match is None:
        return None
    ecosystem, path, raw_version = match.groups()
    try:
        parts = [unquote(part, errors="strict") for part in path.split("/")]
        version = unquote(raw_version, errors="strict")
    except UnicodeDecodeError:
        return None
    if any(part in {"", ".", ".."} or any(token in part for token in ("/", ":", "@", "?", "#", "%", "\\")) for part in parts):
        return None
    if (ecosystem == "cargo" and len(parts) != 1) or (ecosystem == "maven" and len(parts) != 2):
        return None
    name = (":" if ecosystem == "maven" else "/").join(parts)
    if valid_name(ecosystem, name) and valid_version(ecosystem, version):
        return ecosystem, name, version
    return None


def sbom_name(ecosystem, name, group):
    if group is not None and type(group) is not str:
        return None
    if not group:
        return name
    if ecosystem == "golang":
        return f"{group}/{name}"
    if ecosystem == "maven":
        if ":" in name:
            return name if name.partition(":")[0] == group else None
        return f"{group}:{name}"
    return None


def observation_version(ecosystem, version, filename, source, excerpt):
    if not valid_version(ecosystem, version):
        return None
    if source == "lock":
        if filename != LOCK_FILENAMES[ecosystem]:
            return None
        # Cargo equality requirements compare the version without build metadata.
        return version.partition("+")[0] if ecosystem == "cargo" else version
    if source != "manifest" or filename != MANIFEST_FILENAMES[ecosystem]:
        return None
    if ecosystem == "cargo":
        from .cargo_dependencies import exact_cargo_dependency_version
        try:
            selector = json.loads(excerpt or "")
        except ValueError:
            return None
        if exact_cargo_dependency_version(selector) != version:
            return None
    return version
