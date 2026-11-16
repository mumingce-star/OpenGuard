"""Verify packaged bytes without importing product code or contacting a service."""
from pathlib import Path, PurePosixPath
import hashlib, json, sys

ROOT = Path(__file__).resolve().parent
manifest = json.loads((ROOT / 'FILE_HASHES.json').read_text(encoding='utf-8'))
failures = []
for relative, expected in manifest['files'].items():
    key = PurePosixPath(relative)
    if key.is_absolute() or '..' in key.parts:
        failures.append({'path': relative, 'reason': 'unsafe_manifest_path'})
        continue
    path = ROOT.joinpath(*key.parts)
    if path.is_symlink() or not path.is_file():
        failures.append({'path': relative, 'reason': 'missing_or_symlink'})
        continue
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if path.stat().st_size != expected['bytes'] or digest != expected['sha256']:
        failures.append({'path': relative, 'reason': 'byte_identity_mismatch'})
print(json.dumps({'checked_files': len(manifest['files']), 'failures': failures,
                  'ok': not failures, 'network_requests': 0}, ensure_ascii=False, indent=2))
raise SystemExit(1 if failures else 0)
