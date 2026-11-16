"""Frozen actual public-demo output negatives; all execution is offline TEST_ONLY."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from app.ai import p2_analysis as model_module
from app.ai.p2_analysis import material_quote_candidates
from app.p2.ai_analysis import validate_output
from app.p2.contract import canonical, digest, P2Error
from test_official_sources import flow, ready, adopt_body

FIXTURES = Path(__file__).parents[1] / 'fixtures/official-semantic-regression'


def captured(name='usage-v2-preview.json'):
    record = json.loads((FIXTURES / name).read_text())
    preview, candidate = record['analysis']['preview'], record['candidate']
    payload = {'usage': preview['usage'], 'changes': [{k: v for k, v in r.items() if k != 'explanation'} for r in preview['changes']],
               'materials': [{'material_id': candidate['candidate_id'], 'text': candidate['license_text'],
                              'quote_candidates': material_quote_candidates(candidate['license_text'])}]}
    output = {'clauses': [{'material_id': c['source_candidate_id'], 'quote': c['quote'], 'category': c['category']} for c in preview['clauses']],
              'actions': [{'text': a['text'], 'source_material_ids': a['source_candidate_ids']} for a in preview['actions']],
              'change_explanations': [{'index': i, 'text': r['explanation']} for i, r in enumerate(preview['changes'])]}
    return payload, output


@pytest.mark.parametrize('name,reason', [('usage-v2-preview.json', 'usage value conflict'), ('automatic-preview.json', 'disclaimer scope inference')])
def test_exact_captured_output_is_rejected(name, reason):
    payload, output = captured(name)
    with pytest.raises(ValueError, match=reason):
        validate_output(json.dumps(output), payload)


@pytest.mark.parametrize('field,value', [('commercial', 'true'), ('modified', 'false'), ('distributed', 'false'),
    ('network_service', 'false'), ('training', 'true'), ('redistributed_assets', 'true'), ('source_disclosure', 'null')])
def test_all_seven_explicit_wrong_usage_assignments_rejected(field, value):
    payload, output = captured()
    output['actions'] = [{'text': f'核对当前usage.{field}={value}的用途设定，记录实际文件范围。', 'source_material_ids': [payload['materials'][0]['material_id']]}]
    with pytest.raises(ValueError, match='usage value conflict'):
        validate_output(json.dumps(output), payload)


def test_actual_correct_actions_and_programmed_transition_are_retained():
    payload, output = captured()
    output['actions'].pop(2)  # Only the conflicting actual row; all other captured text unchanged.
    clauses, actions, changes = validate_output(json.dumps(output), payload)
    assert len(actions) == 3 and actions[-1]['text'] == output['actions'][-1]['text']
    assert changes[0]['before'] is False and changes[0]['after'] is True


@pytest.mark.parametrize('text', ['请确认usage.distributed从true变false是否对应当前实际范围，记录文件清单。',
                                 '核对usage.training从false变true后的模型训练记录。'])
def test_wrong_or_unrecorded_historical_transition_rejected(text):
    payload, output = captured()
    output['actions'] = [{'text': text, 'source_material_ids': [payload['materials'][0]['material_id']]}]
    with pytest.raises(ValueError, match='usage transition conflict'):
        validate_output(json.dumps(output), payload)


def test_null_usage_cannot_be_written_as_false():
    payload, output = captured(); payload['usage']['commercial'] = None
    output['actions'] = [{'text': '核对当前commercial=false的用途设定，记录文件集合。', 'source_material_ids': [payload['materials'][0]['material_id']]}]
    with pytest.raises(ValueError, match='usage value conflict'):
        validate_output(json.dumps(output), payload)


def test_change_explanation_cannot_override_current_usage():
    payload, output = captured(); output['actions'].pop(2)
    output['change_explanations'][0]['text'] = '当前distributed=false，因此应按不分发用途核对文件集合。'
    with pytest.raises(ValueError, match='usage value conflict'):
        validate_output(json.dumps(output), payload)


def test_prompt_contains_only_applicable_guidance_and_no_irrelevant_false_branch():
    payload, _ = captured()
    prompt = model_module.prompt_for(payload)
    assert 'distributed=false' not in prompt and '当前不分发' not in prompt
    assert '免责' in prompt and '不能' in prompt and '通俗中文' in prompt
    payload['usage']['distributed'] = False
    prompt_false = model_module.prompt_for(payload)
    assert '当前不分发' in prompt_false
    assert prompt_false != prompt


def test_old_preview_read_rejects_semantics_without_mutating_immutable_or_regenerating(flow):
    svc, run, a, result, fetcher, model, _, _ = flow
    out = ready(flow); old = out['analysis']['preview']; value = deepcopy(old)
    value['actions'][0]['text'] = '核对当前distributed=true的用途设定，记录实际交付范围。'
    value.pop('preview_id'); value.pop('preview_sha256'); sha = digest(value)
    value.update(preview_id='p2preview_' + sha, preview_sha256=sha); raw = canonical(value)
    with svc.store.connection(write=True) as db:
        db.execute('INSERT INTO official_previews VALUES(?,?,?)', (value['preview_id'], raw, hashlib.sha256(raw).hexdigest()))
        job = svc.store.job(db, 'analysis', result['result_id']); job['preview_id'] = value['preview_id']
        svc.store.put_job(db, 'analysis', result['result_id'], job)
    before = svc.store.path.read_bytes(); calls = model.calls
    for _ in range(2):
        projection = svc.status(run.id, a.id, 1, result['result_id'])
        assert projection['analysis']['state'] == 'failed'
        assert projection['analysis']['error_code'] == 'p2_ai_saved_output_rejected'
        assert projection['analysis']['preview'] is None
        assert projection['analysis']['preview_id'] == value['preview_id']
        assert projection['analysis']['preview_sha256'] == sha
        assert projection['candidate'] == out['candidate']
    assert svc.store.path.read_bytes() == before and model.calls == calls and fetcher.calls == 1
    assert svc.p2.read(run.id, a.id, result['result_id'], 1) == result


def test_old_saved_material_analysis_read_rejects_semantics_and_preserves_bytes(flow):
    svc, run, a, old, fetcher, model, _, _ = flow
    out = ready(flow)
    result = svc.adopt(run.id, a.id, adopt_body(old, out['candidate']['candidate_id']))['result']
    assert svc.wait_idle()
    status = svc.status(run.id, a.id, 1, result['result_id'])
    value = svc.ai.read(run.id, a.id, status['analysis']['analysis_id'], result['result_id'], 1)
    value['actions'][0]['text'] = '核对当前distributed=true的用途设定，记录实际交付范围。'
    value.pop('analysis_id'); value.pop('analysis_sha256'); sha = digest(value)
    value.update(analysis_id='p2ai_' + sha, analysis_sha256=sha); raw = canonical(value)
    with svc.ai.store.connection(write=True) as db:
        db.execute('INSERT INTO ai_objects VALUES(?,?,?,?,?,?)', (value['analysis_id'], run.id, a.id, result['result_id'], raw, hashlib.sha256(raw).hexdigest()))
    with svc.store.connection(write=True) as db:
        job = svc.store.job(db, 'analysis', result['result_id']); job['analysis_id'] = value['analysis_id']
        svc.store.put_job(db, 'analysis', result['result_id'], job)
    before = svc.ai.store.path.read_bytes(); official_before = svc.store.path.read_bytes(); calls = model.calls
    with pytest.raises(P2Error, match='p2_ai_saved_output_rejected'):
        svc.ai.read(run.id, a.id, value['analysis_id'], result['result_id'], 1)
    projected = svc.status(run.id, a.id, 1, result['result_id'])
    assert projected['analysis']['state'] == 'failed' and projected['analysis']['error_code'] == 'p2_ai_saved_output_rejected'
    assert projected['analysis']['analysis_id'] == value['analysis_id']
    assert svc.ai.store.path.read_bytes() == before and svc.store.path.read_bytes() == official_before and model.calls == calls
