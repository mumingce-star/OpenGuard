"""TASK-only generation ceiling; all Ollama calls are closed synthetic transport."""
import fcntl
import json
import os

import pytest

from app.ai.p2_analysis import BoundQwen, BudgetError
from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION, OllamaProvider, _MODEL_SLOT

PAYLOAD = {'materials': [{'material_id': 'SYNTHETIC_TEST_ONLY', 'quote_candidates': ['Synthetic test-only text, not a real license.']}], 'changes': []}


@pytest.fixture(autouse=True)
def deny_real_model(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Real Ollama transport forbidden in this offline suite')
    monkeypatch.setattr(OllamaProvider, '_request_json', denied)


def budget(tmp_path, count):
    tmp_path.chmod(0o700)
    path = tmp_path / 'SYNTHETIC_ONLY_BUDGET.json'
    path.write_text(json.dumps({'version': 1, 'max_generations': 10, 'intents': [{'number': i + 1, 'state': 'SYNTHETIC_TEST_ONLY'} for i in range(count)]}))
    path.chmod(0o600)
    return path


def provider(path, *, ceiling=8, timeout=False):
    model = BoundQwen(path, max_generations=10, intent_ceiling=ceiling)
    calls = []
    def transport(route, **kwargs):
        calls.append(route)
        if route == '/api/version': return {'version': OLLAMA_VERSION}
        if route == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        assert route == '/api/generate'
        if timeout: raise TimeoutError('SYNTHETIC_TEST_ONLY')
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': '{}'}
    model.transport._request_json = transport
    return model, calls


def test_ceiling_strict_integer_range_and_default(tmp_path):
    for invalid in (True, False, 0, -1, 11, 8.0, '8', '', [], {}):
        with pytest.raises(ValueError, match='invalid explicit generation intent ceiling'):
            BoundQwen(tmp_path / 'unused.json', max_generations=10, intent_ceiling=invalid)
    assert BoundQwen(tmp_path / 'unused.json', max_generations=10).intent_ceiling == 10
    assert BoundQwen(tmp_path / 'unused.json', max_generations=10, intent_ceiling=None).intent_ceiling == 10
    assert BoundQwen(tmp_path / 'unused.json', max_generations=10, intent_ceiling=1).intent_ceiling == 1
    assert not (tmp_path / 'unused.json').exists()


def test_shared_existing_five_allows_only_three_new_intents(tmp_path):
    path = budget(tmp_path, 5)
    a, ac = provider(path); b, bc = provider(path)
    for model in (a, b, a): assert model.generate(PAYLOAD) == '{}'
    before = path.read_bytes()
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'): b.generate(PAYLOAD)
    assert path.read_bytes() == before
    ledger = json.loads(before)
    assert ledger['max_generations'] == 10 and len(ledger['intents']) == 8
    assert set(ledger) == {'version', 'max_generations', 'intents'}
    assert ac.count('/api/generate') + bc.count('/api/generate') == 3
    assert b.model_calls == 0


def test_at_ceiling_refuses_before_transport_or_ledger_append(tmp_path):
    path = budget(tmp_path, 8); before = path.read_bytes()
    model, calls = provider(path)
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'): model.generate(PAYLOAD)
    assert calls == [] and model.model_calls == 0 and path.read_bytes() == before
    assert not (tmp_path / 'p2-ai-model-audit').exists()


def test_failed_generation_still_consumes_last_authorized_intent(tmp_path):
    path = budget(tmp_path, 7); model, calls = provider(path, timeout=True)
    with pytest.raises(TimeoutError, match='SYNTHETIC_TEST_ONLY'): model.generate(PAYLOAD)
    assert len(json.loads(path.read_text())['intents']) == 8 and model.model_calls == 1
    before, prior_calls = path.read_bytes(), list(calls)
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'): model.generate(PAYLOAD)
    assert path.read_bytes() == before and calls == prior_calls and calls.count('/api/generate') == 1


def test_global_slot_and_same_ledger_flock_still_precede_intent(tmp_path):
    path = budget(tmp_path, 5); before = path.read_bytes(); model, calls = provider(path)
    assert _MODEL_SLOT.acquire(blocking=False)
    try:
        with pytest.raises(BudgetError, match='p2_ai_busy'): model.generate(PAYLOAD)
    finally: _MODEL_SLOT.release()
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BudgetError, match='p2_ai_busy'): model.generate(PAYLOAD)
        assert calls == [] and path.read_bytes() == before
    finally: os.close(fd)
    assert model.generate(PAYLOAD) == '{}'
    assert len(json.loads(path.read_text())['intents']) == 6


def test_default_factory_forwards_optional_ceiling_without_changing_global_budget(tmp_path, monkeypatch):
    from app.api.main import create_default_app
    tmp_path.chmod(0o700)
    for key, value in {'OPENGUARD_DATA_DIR': str(tmp_path), 'OPENGUARD_ENABLE_ASSESSMENTS': '1',
                       'OPENGUARD_ENABLE_P2': '1', 'OPENGUARD_P2_READONLY': '0', 'OPENGUARD_P2_DATA_SCOPE': 'TEST_ONLY',
                       'OPENGUARD_ENABLE_AI': '0', 'OPENGUARD_ENABLE_PUBLIC_GIT': '0', 'OPENGUARD_ENABLE_DURABLE_ZIP': '0',
                       'OPENGUARD_ENABLE_PROFILE_METADATA': '0', 'OPENGUARD_ENABLE_EXTERNAL_SCANNERS': '0',
                       'OPENGUARD_ENABLE_P2_AI': '1', 'OPENGUARD_P2_AI_MAX_GENERATIONS': '10',
                       'OPENGUARD_P2_AI_BUDGET_PATH': str(tmp_path / 'unused.json'),
                       'OPENGUARD_P2_AI_INTENT_CEILING': '8'}.items(): monkeypatch.setenv(key, value)
    p = create_default_app().state.p2_service.ai_analysis.provider
    assert p.max_generations == 10 and p.intent_ceiling == 8
    monkeypatch.delenv('OPENGUARD_P2_AI_INTENT_CEILING')
    assert create_default_app().state.p2_service.ai_analysis.provider.intent_ceiling == 10
    monkeypatch.setenv('OPENGUARD_P2_AI_INTENT_CEILING', 'true')
    with pytest.raises(ValueError): create_default_app()
    assert not (tmp_path / 'unused.json').exists()
