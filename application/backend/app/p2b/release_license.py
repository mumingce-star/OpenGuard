"""Offline check of one issuer-bound npm tarball license relationship."""

from __future__ import annotations

import gzip
import hashlib
import io
import re
import tarfile
import zlib
from dataclasses import dataclass

from app.p2.contract import strict_json
from app.scanners.dependency_observations import relative_path
from .source_readback import SourcePin, consume_source_readback

_MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
_MAX_TAR_BYTES = 32 * 1024 * 1024
_MAX_MEMBERS = 4096
_MAX_LICENSE_BYTES = 64 * 1024
_HEX40 = re.compile(r"[a-f0-9]{40}\Z")
_HEX64 = re.compile(r"[a-f0-9]{64}\Z")


@dataclass(frozen=True)
class ReleaseLicenseObservation:
    pin: SourcePin
    commit: str
    blob: str
    repository_path: str
    archive_sha256: str
    member_path: str
    member_sha256: str


def verify_release_license(pin, relation_bytes, *, git_bytes, archive_bytes,
                           issuer_policies, read_authenticated):
    """Require A's authenticated relation and check independent byte identities.

    The relation describes a commit/tree member and release member of one
    object, version and scope. Equal bytes alone cannot establish that link.
    """
    if type(pin) is not SourcePin or pin.role != "release_license_binding":
        raise ValueError("release_relation_role_invalid")
    if type(archive_bytes) is not bytes or not 0 < len(archive_bytes) <= _MAX_ARCHIVE_BYTES:
        raise ValueError("release_archive_limit")
    if type(git_bytes) is not bytes or not 0 < len(git_bytes) <= _MAX_LICENSE_BYTES:
        raise ValueError("release_license_limit")
    consume_source_readback(pin, relation_bytes, issuer_policies=issuer_policies, read_authenticated=read_authenticated)
    relation = strict_json(relation_bytes.decode("utf-8"))
    required = {"commit", "blob", "repository_path", "archive_sha256", "member_path", "member_sha256", "member_type"}
    if type(relation) is not dict or set(relation) != required or relation["member_type"] != "regular_file":
        raise ValueError("release_relation_fields_invalid")
    for key, pattern in (("commit", _HEX40), ("blob", _HEX40), ("archive_sha256", _HEX64), ("member_sha256", _HEX64)):
        if type(relation[key]) is not str or not pattern.fullmatch(relation[key]):
            raise ValueError("release_relation_digest_invalid")
    repository_path = relative_path(relation["repository_path"])
    member_path = relative_path(relation["member_path"])
    if not member_path.startswith("package/"):
        raise ValueError("release_member_path_invalid")
    file_name = re.compile(r"(?:LICENSE|LICENCE)(?:\.(?:txt|md|rst))?\Z", re.I)
    if not all(file_name.fullmatch(path.rsplit("/", 1)[-1]) for path in (repository_path, member_path)):
        raise ValueError("release_member_not_license")
    blob = hashlib.sha1(f"blob {len(git_bytes)}\0".encode() + git_bytes, usedforsecurity=False).hexdigest()
    if blob != relation["blob"] or hashlib.sha256(git_bytes).hexdigest() != relation["member_sha256"]:
        raise ValueError("release_git_license_mismatch")
    if hashlib.sha256(archive_bytes).hexdigest() != relation["archive_sha256"]:
        raise ValueError("release_archive_mismatch")
    found = None
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive_bytes)) as gzip_reader:
            tar_bytes = gzip_reader.read(_MAX_TAR_BYTES + 1)
        if len(tar_bytes) > _MAX_TAR_BYTES:
            raise ValueError("release_archive_expansion_limit")
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
            for index, member in enumerate(archive):
                if index >= _MAX_MEMBERS:
                    raise ValueError("release_member_count_limit")
                if relative_path(member.name.rstrip("/") if member.isdir() else member.name) != member_path:
                    continue
                if found is not None:
                    raise ValueError("release_member_duplicate")
                if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or getattr(member, "sparse", None):
                    raise ValueError("release_member_type_invalid")
                if not 0 < member.size <= _MAX_LICENSE_BYTES:
                    raise ValueError("release_member_size_invalid")
                with archive.extractfile(member) as stream:
                    found = stream.read(_MAX_LICENSE_BYTES + 1)
    except (OSError, EOFError, tarfile.TarError, zlib.error) as exc:
        raise ValueError("release_archive_invalid") from exc
    if found is None:
        raise ValueError("release_member_missing")
    if hashlib.sha256(found).hexdigest() != relation["member_sha256"]:
        raise ValueError("release_member_hash_mismatch")
    return ReleaseLicenseObservation(pin, relation["commit"], blob, repository_path,
                                     relation["archive_sha256"], member_path, relation["member_sha256"])
