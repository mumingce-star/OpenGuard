"""Offline P1 contract/example checks only; no runtime implementation or I/O services."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
NAMES = {
    'ScanHistoryItem': 'scan-history-item',
    'ScanDiffView': 'scan-diff-view',
    'ResourceGraphView': 'resource-graph-view',
    'ResourceProfile': 'resource-profile',
    'RemediationTask': 'remediation-task',
    'NoticeDraft': 'notice-draft',
    'ReportV2Snapshot': 'report-v2-snapshot',
}
SCHEMAS = {p.stem: json.loads(p.read_text()) for p in (ROOT / 'schemas/p1').glob('*.schema.json')}
REGISTRY = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in SCHEMAS.values())
EXAMPLES = json.loads((ROOT / 'docs/p1/object-examples.json').read_text())['objects']


def validator(name):
    return Draft202012Validator(SCHEMAS[NAMES[name] + '.schema'], registry=REGISTRY, format_checker=FormatChecker())


@pytest.mark.parametrize('name', NAMES)
def test_schema_and_fixed_example(name):
    schema = SCHEMAS[NAMES[name] + '.schema']
    Draft202012Validator.check_schema(schema)
    assert schema['$id'] == f'urn:openguard:p1:{NAMES[name]}:1.0'
    validator(name).validate(EXAMPLES[name])


def test_common_schema_is_valid():
    Draft202012Validator.check_schema(SCHEMAS['common.schema'])


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('field,value', [('unexpected', True), ('schema_version', '0.1-draft')])
def test_closed_objects_and_version(name, field, value):
    value_copy = deepcopy(EXAMPLES[name])
    value_copy[field] = value
    assert list(validator(name).iter_errors(value_copy))


@pytest.mark.parametrize('field', ['version', 'assessment_id', 'scan_id'])
def test_task_requires_assessment_binding(field):
    value = deepcopy(EXAMPLES['RemediationTask'])
    del value['assessment_ref'][field]
    assert list(validator('RemediationTask').iter_errors(value))


@pytest.mark.parametrize('status', ['done', 'dismissed'])
@pytest.mark.parametrize('note', [None, '', '  \t\n'])
def test_done_dismissed_require_nonblank_note(status, note):
    value = deepcopy(EXAMPLES['RemediationTask'])
    value['status'] = status
    if note is None:
        del value['note']
    else:
        value['note'] = note
    assert list(validator('RemediationTask').iter_errors(value))


@pytest.mark.parametrize('field,value', [('cursor', 'abc'), ('limit', 100), ('next_cursor', None)])
def test_graph_rejects_pagination(field, value):
    graph = deepcopy(EXAMPLES['ResourceGraphView'])
    graph[field] = value
    assert list(validator('ResourceGraphView').iter_errors(graph))


def test_metadata_rejects_raw_payload():
    value = deepcopy(EXAMPLES['ResourceProfile'])
    value['metadata_observations'][0]['raw_payload'] = {'name': 'copied-response'}
    assert list(validator('ResourceProfile').iter_errors(value))


def test_nested_unknown_property_rejected():
    value = deepcopy(EXAMPLES['ResourceProfile'])
    value['metadata_observations'][0]['fields'][0]['authorization'] = 'allowed'
    assert list(validator('ResourceProfile').iter_errors(value))


@pytest.mark.parametrize('status', ['todo', 'in_progress', 'done', 'dismissed'])
def test_task_status_positive_cases(status):
    value = deepcopy(EXAMPLES['RemediationTask'])
    value['status'] = status
    value['note'] = '人工备注，不是授权证据' if status in ('done', 'dismissed') else ''
    validator('RemediationTask').validate(value)


def test_graph_rejects_invented_edge_and_formal_authority():
    for mutation in ('formal', 'edge'):
        value = deepcopy(EXAMPLES['ResourceGraphView'])
        if mutation == 'formal':
            value['formal'] = True
        else:
            value['edges'][0]['type'] = 'ROOT_LICENSE_AUTHORIZES_ALL'
        assert list(validator('ResourceGraphView').iter_errors(value))


def test_fixed_sample_relationships_and_bindings():
    history = EXAMPLES['ScanHistoryItem']
    assert history['finding_count'] == sum(history['summary']['finding_counts'].values())
    graph = EXAMPLES['ResourceGraphView']
    node_ids = {n['id'] for n in graph['nodes']}
    assert len(node_ids) == len(graph['nodes']) == graph['coverage']['node_count']
    assert len(graph['edges']) == graph['coverage']['edge_count']
    assert all(e['source'] in node_ids and e['target'] in node_ids for e in graph['edges'])
    task = EXAMPLES['RemediationTask']
    assert task['scan_id'] == task['assessment_ref']['scan_id']
    for name in ('NoticeDraft', 'ReportV2Snapshot'):
        binding = EXAMPLES[name]['binding']
        assert binding['scan_ref']['scan_id'] == binding['assessment_ref']['scan_id']
        assert binding['scan_ref']['facts_hash'] == binding['assessment_ref']['facts_hash']
        assert binding['task_refs'] == [{'task_id': task['task_id'], 'version': task['version']}]
    notice = EXAMPLES['NoticeDraft']
    assert EXAMPLES['ReportV2Snapshot']['binding']['notice_refs'] == [{'draft_id': notice['draft_id'], 'content_hash': notice['content_hash']}]
    assert EXAMPLES['ResourceProfile']['authorization_fact'] is None
    assert EXAMPLES['ResourceProfile']['metadata_observations'][0]['full_response_replay_available'] is False
    change = EXAMPLES['ScanDiffView']['resources'][0]
    assert change['before']['resource_identity_key'] == change['after']['resource_identity_key']
    assert change['before']['resource_instance_key'] != change['after']['resource_instance_key']
    assert change['kind'] == 'changed' and change['removal_confirmed'] is None
