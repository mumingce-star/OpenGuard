"""新修订必须保持冻结 v3 契约，并以外部 manifest pin 拒绝篡改。"""
import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from app.detectors.license_notice_facts_v3_adapter import (
    V3FactsAdapterError, canonical_v3_facts_sha256, consume_v3_facts,
)


BASE = Path('tests/fixtures/notice-license-facts-v3')
REVISION = BASE / 'revisions/source-binding-r2'


def package():
    return json.loads((REVISION / 'facts.json').read_bytes())


def pin():
    manifest = json.loads((REVISION / 'manifest.json').read_bytes())
    return next(item['canonical_package_sha256'] for item in manifest['artifacts'] if item['path'] == 'facts.json')


def test_corrected_package_passes_frozen_schema_and_read_only_adapter():
    facts = package()
    schema = json.loads((BASE / 'schema.json').read_bytes())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(facts)
    assert canonical_v3_facts_sha256(facts) == pin()
    view = consume_v3_facts(facts, expected_package_sha256=pin())
    assert len(view.facts) == 31
    assert all(item.authorization_status == 'pending' and item.license_expression_id is None for item in view.facts)
    assert facts['facts'] == json.loads((BASE / 'facts.json').read_bytes())['facts']


@pytest.mark.parametrize('field,value', [
    ('source_file_sha256', '0' * 64), ('selected_content_sha256', '0' * 64),
    ('source_revision', '0' * 40),
])
def test_corrected_package_cannot_self_repin_tampered_evidence(field, value):
    modified = copy.deepcopy(package())
    item = next(item for item in modified['evidence'] if item['evidence_id'] == 'evidence.dependency.npm.react')
    item[field] = value
    with pytest.raises(V3FactsAdapterError):
        consume_v3_facts(modified, expected_package_sha256=pin())


def test_legacy_package_bytes_remain_the_retained_parent():
    amendment = json.loads((REVISION / 'amendment.json').read_bytes())
    actual = hashlib.sha256((BASE / 'facts.json').read_bytes()).hexdigest()
    assert actual == amendment['parent']['file_sha256'] == '4f2a8304ad457dffdc7e4ba276e3602bf93b4f83b1e7e177bbcb84f4a8d841f7'
    assert amendment['independent_review'] is None and amendment['human_approval'] is None
