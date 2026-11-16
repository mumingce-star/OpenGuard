"""SYNTHETIC boundary demonstration, NOT cz's B01 business parser.

No network, database, files, license analysis or changes to Scan/Assessment.
Do not log or persist the argument or raw JSON. This is test/example code only.
"""
import hashlib


def consume(temporary):
    body = temporary.bounded_bytes()
    source = temporary.source
    assert len(body) == source.body_size
    assert hashlib.sha256(body).hexdigest() == source.body_sha256
    return {'synthetic': True, 'boundary_checked': True,
            'source_hash': source.body_sha256,
            'full_response_replay_available': False}
