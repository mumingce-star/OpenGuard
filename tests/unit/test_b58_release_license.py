import hashlib
import io
import json
import tarfile

import pytest

from app.p2b.release_license import verify_release_license
from app.p2b.source_readback import IssuerReadback, SourcePin

LICENSE = b"synthetic license bytes"
MEMBER = "package/LICENSE.txt"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def archive(entries):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, value, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            if kind == tarfile.SYMTYPE:
                item.linkname = "elsewhere"
            item.size = len(value)
            tar.addfile(item, io.BytesIO(value))
    return buf.getvalue()


def verify(raw, *, relation_changes=None, current_status="accepted", git_bytes=LICENSE):
    identity = {"receipt_id": "release-1", "receipt_version": 2, "scan_id": "scan-1", "resource_id": "npm:demo",
                "resource_version": "1.0.0", "scope_id": "release", "role": "release_license_binding"}
    relation = json.dumps({"commit": "1" * 40, "blob": hashlib.sha1(f"blob {len(LICENSE)}\0".encode() + LICENSE).hexdigest(),
                           "repository_path": "LICENSE.txt", "archive_sha256": sha(raw), "member_path": MEMBER,
                           "member_sha256": sha(LICENSE), "member_type": "regular_file", **(relation_changes or {})}).encode()
    record = json.dumps({**identity, "issuer": "test", "policy": "test", "policy_version": "1", "status": "accepted",
                         "observed_at": "2026-11-16T00:00:00Z", "content_bytes": len(relation), "content_sha256": sha(relation)}).encode()
    return verify_release_license(SourcePin(**identity, receipt_sha256=sha(record)), relation,
                                  git_bytes=git_bytes, archive_bytes=raw, issuer_policies=frozenset({("test", "test", "1")}),
                                  read_authenticated=lambda *_: IssuerReadback(record, current_status))


def test_release_relation_checks_archive_bytes_member_blob_and_fixed_pin():
    raw = archive([(MEMBER, LICENSE, tarfile.REGTYPE)])
    result = verify(raw)
    assert result.archive_sha256 == sha(raw) and result.member_sha256 == sha(LICENSE)
    with pytest.raises(ValueError, match="not_currently_accepted"):
        verify(raw, current_status="revoked")
    with pytest.raises(ValueError, match="git_license_mismatch"):
        verify(raw, git_bytes=b"other")
    with pytest.raises(ValueError, match="archive_mismatch"):
        verify(raw, relation_changes={"archive_sha256": "0" * 64})
    with pytest.raises(ValueError, match="relation_digest"):
        verify(raw, relation_changes={"commit": "v1.0.0"})


@pytest.mark.parametrize("entries,error", [
    ([(MEMBER, b"another text", tarfile.REGTYPE)], "member_hash_mismatch"),
    ([(MEMBER, b"", tarfile.SYMTYPE)], "member_type_invalid"),
    ([("package/OTHER", LICENSE, tarfile.REGTYPE)], "member_missing"),
    ([(MEMBER, LICENSE, tarfile.REGTYPE)] * 2, "member_duplicate"),
    ([("../escape", LICENSE, tarfile.REGTYPE)], "unsafe_source_path"),
])
def test_member_negatives(entries, error):
    with pytest.raises(ValueError, match=error):
        verify(archive(entries))
