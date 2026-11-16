"""Synthetic transport tests; never contact or load a real model."""
import json
import time
from types import SimpleNamespace

import pytest
import app.ai.p2_analysis as module
from app.ai.ollama import MODEL_NAME, MANIFEST_DIGEST, OLLAMA_VERSION, OllamaTransportError
from app.ai.p2_analysis import BoundQwen, BudgetError

PAYLOAD = {'materials': [{'material_id': 'SYNTHETIC', 'quote_candidates': ['Synthetic test-only quoted material.']}], 'changes': []}


def setup_model(tmp_path, monkeypatch, **kwargs):
    tmp_path.chmod(0o700)
    clock = [1000.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(time=lambda: clock[0], strftime=time.strftime, gmtime=time.gmtime))
    model = BoundQwen(tmp_path / 'continuous.json', continuous=True, **kwargs)
    calls = []
    def transport(path, **options):
        calls.append(path)
        if path == '/api/version': return {'version': OLLAMA_VERSION}
        if path == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        return {'model': MODEL_NAME, 'done': True, 'done_reason': 'stop', 'response': '{}'}
    model.transport._request_json = transport
    return model, clock, calls


def test_more_than_twenty_calls_keep_every_intent_and_survive_restart(tmp_path, monkeypatch):
    model, clock, calls = setup_model(tmp_path, monkeypatch)
    for _ in range(25):
        assert model.generate(PAYLOAD) == '{}'
        clock[0] += 7
    ledger = json.loads(model.path.read_text())
    assert ledger['count'] == 25 and len(ledger['recent']) <= 10
    records = sorted((tmp_path / 'p2-ai-model-audit').glob('continuous-*-intent.json'))
    assert len(records) == 25
    assert [json.loads(p.read_text())['number'] for p in records] == list(range(1, 26))
    restarted = BoundQwen(model.path, continuous=True)
    restarted.transport._request_json = model.transport._request_json
    assert restarted.generate(PAYLOAD) == '{}'
    assert json.loads(model.path.read_text())['count'] == 26
    assert calls.count('/api/generate') == 26


def test_rate_limit_stops_before_transport_and_recovers_after_window(tmp_path, monkeypatch):
    model, clock, calls = setup_model(tmp_path, monkeypatch)
    for _ in range(10): model.generate(PAYLOAD)
    before = model.path.read_bytes(); count = len(calls)
    with pytest.raises(BudgetError, match='p2_ai_rate_limited'): model.generate(PAYLOAD)
    assert len(calls) == count and model.path.read_bytes() == before
    clock[0] += 61
    assert model.generate(PAYLOAD) == '{}'
    assert json.loads(model.path.read_text())['count'] == 11


def test_old_ledger_is_rejected_without_reset_or_generation(tmp_path, monkeypatch):
    model, _, calls = setup_model(tmp_path, monkeypatch)
    raw = json.dumps({'version': 1, 'max_generations': 20, 'intents': [{'number': 1}]}).encode()
    model.path.write_bytes(raw); model.path.chmod(0o600)
    with pytest.raises(BudgetError, match='p2_ai_budget_invalid'): model.generate(PAYLOAD)
    assert model.path.read_bytes() == raw and calls == []


def test_timeout_preserves_intent_and_does_not_retry(tmp_path, monkeypatch):
    model, _, calls = setup_model(tmp_path, monkeypatch)
    real = model.transport._request_json
    def timeout(path, **kwargs):
        if path == '/api/generate':
            calls.append(path)
            raise TimeoutError('SYNTHETIC')
        return real(path, **kwargs)
    model.transport._request_json = timeout
    with pytest.raises(TimeoutError): model.generate(PAYLOAD)
    assert calls.count('/api/generate') == 1
    assert json.loads(model.path.read_text())['count'] == 1
    assert len(list((tmp_path / 'p2-ai-model-audit').glob('*-intent.json'))) == 1


def test_wrong_model_identity_stops_before_intent(tmp_path, monkeypatch):
    model, _, calls = setup_model(tmp_path, monkeypatch)
    model.transport._request_json = lambda path, **kwargs: {'version': 'wrong'} if path == '/api/version' else {'models': []}
    with pytest.raises(OllamaTransportError): model.generate(PAYLOAD)
    assert model.path.read_bytes() == b''
    assert not (tmp_path / 'p2-ai-model-audit').exists()


def test_continuous_never_bypasses_explicit_intent_ceiling(tmp_path):
    with pytest.raises(ValueError): BoundQwen(tmp_path / 'unused', continuous=True, intent_ceiling=1)
    assert not (tmp_path / 'unused').exists()


def test_audit_collision_prevents_generation(tmp_path, monkeypatch):
    model, _, calls = setup_model(tmp_path, monkeypatch)
    model.generate(PAYLOAD)
    # Simulate a rolled-back counter; retained evidence must never be overwritten.
    record = next((tmp_path / 'p2-ai-model-audit').glob('*-intent.json'))
    original = record.read_bytes()
    model.path.write_text(json.dumps({'version': 2, 'mode': 'continuous', 'count': 0, 'recent': []}))
    with pytest.raises(FileExistsError): model.generate(PAYLOAD)
    assert calls.count('/api/generate') == 1 and record.read_bytes() == original


def test_explicit_factory_modes_and_invalid_scope(tmp_path, monkeypatch):
    from app.api.main import create_default_app
    tmp_path.chmod(0o700)
    for key, value in {'OPENGUARD_DATA_DIR': str(tmp_path), 'OPENGUARD_ENABLE_ASSESSMENTS': '1',
                       'OPENGUARD_ENABLE_P2': '1', 'OPENGUARD_P2_READONLY': '0', 'OPENGUARD_P2_DATA_SCOPE': 'TEST_ONLY',
                       'OPENGUARD_ENABLE_AI': '0', 'OPENGUARD_ENABLE_P2_AI': '1',
                       'OPENGUARD_P2_AI_BUDGET_PATH': str(tmp_path / 'usage.json'),
                       'OPENGUARD_P2_AI_USAGE_MODE': 'continuous',
                       'OPENGUARD_P2_AI_INPUT_SCOPE': 'bound_materials'}.items():
        monkeypatch.setenv(key, value)
    service = create_default_app().state.p2_service.ai_analysis
    assert service.provider.continuous is True and service.public_sample_only is False
    assert not service.provider.path.exists()  # Configuration never starts inference.
    monkeypatch.delenv('OPENGUARD_P2_AI_USAGE_MODE')
    monkeypatch.delenv('OPENGUARD_P2_AI_INPUT_SCOPE')
    old = create_default_app().state.p2_service.ai_analysis
    assert old.provider.continuous is False and old.public_sample_only is True
    monkeypatch.setenv('OPENGUARD_P2_AI_INPUT_SCOPE', 'anything')
    with pytest.raises(RuntimeError, match='invalid P2 AI input scope'): create_default_app()
