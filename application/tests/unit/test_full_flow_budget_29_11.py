"""Owner-approved 6 HTTP + 3 Qwen continuation; synthetic transport only."""
from copy import deepcopy
import json
import socket
from types import SimpleNamespace

import pytest

from app.ingestion import official_http_server as api
from app.ai.p2_analysis import BoundQwen, BudgetError
from app.ai.ollama import OllamaProvider, OLLAMA_VERSION, MODEL_NAME, MANIFEST_DIGEST
from test_official_http_server import Driver
from test_official_http_budget_24 import ledger


@pytest.fixture(autouse=True)
def no_external_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Real network or model forbidden in offline budget tests')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    monkeypatch.setattr(OllamaProvider, '_request_json', forbidden)


def test_http_29_inherits_23_exactly_and_allows_only_one_six_request_plan(tmp_path):
    driver = Driver()
    client = api.FixedOfficialFetcher(tmp_path, max_task_http=29, _wire_factory=driver.factory)
    before = ledger(23, 29)
    client.budget_path.write_text(json.dumps(before))
    result = client.fetch('SYNTHETIC_TEST_ONLY_full_flow')
    assert result['status'] == 'succeeded'
    assert result['http_intents'] == result['http_dispatched'] == result['http_responses'] == 6
    after = json.loads(client.budget_path.read_text())
    assert after['requests'][:23] == before['requests']
    assert len(after['requests']) == result['task_http_intents'] == 29
    assert [row['number'] for row in after['requests'][23:]] == list(range(24, 30))
    refused = client.fetch('SYNTHETIC_TEST_ONLY_second')
    assert refused['error_code'] == 'official_source_http_budget_exhausted'
    assert refused['http_intents'] == 0 and len(driver.requests) == 6


@pytest.mark.parametrize('limit', [28, 30, 29.0, '29', True])
def test_only_exact_new_http_limit_allowed(tmp_path, limit):
    with pytest.raises(ValueError, match='official_source_http_limit_invalid'):
        api.FixedOfficialFetcher(tmp_path / 'unused', max_task_http=limit)
    assert not (tmp_path / 'unused').exists()


def test_runtime_accepts_29_11_without_expanding_arbitrary_limits(tmp_path, monkeypatch):
    from app.api.official_runtime import configure_official_sources
    import app.p2.official_sources as module
    seen = []
    for key, value in {
        'OPENGUARD_OFFICIAL_SOURCE_AUTO': '1', 'OPENGUARD_P2_AI_MAX_GENERATIONS': '11',
        'OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH': str(tmp_path / 'unused.json'),
        'OPENGUARD_OFFICIAL_HTTP_MAX_TASK': '29', 'OPENGUARD_OFFICIAL_JOBS_ENABLED': '1',
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(module, 'OfficialSourceService',
                        lambda p2, root, fetcher, ai, **kw: seen.append((fetcher, kw)) or SimpleNamespace())
    p2 = SimpleNamespace(readonly=False, data_scope='TEST_ONLY', ai_analysis=object())
    assessments = SimpleNamespace(assessment_saved_observer=None)
    configure_official_sources(p2, assessments, None, tmp_path)
    assert seen[0][0].max_task_http == 29 and seen[0][1]['jobs_enabled'] is True
    for invalid in ('9', '12', '11.0', '011', ''):
        monkeypatch.setenv('OPENGUARD_P2_AI_MAX_GENERATIONS', invalid)
        with pytest.raises(RuntimeError, match='bounded local AI'):
            configure_official_sources(p2, assessments, None, tmp_path)
    assert len(seen) == 1 and not (tmp_path / 'unused.json').exists()


def test_qwen_11_preserves_eight_and_allows_three_failed_attempts_only(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / 'SYNTHETIC_TEST_ONLY_qwen.json'
    original = {'version': 1, 'max_generations': 11,
                'intents': [{'number': i + 1, 'state': 'SYNTHETIC_HISTORY_ONLY'} for i in range(8)]}
    path.write_text(json.dumps(original)); path.chmod(0o600)
    model = BoundQwen(path, max_generations=11, intent_ceiling=11)
    calls = []
    def transport(route, **kwargs):
        calls.append(route)
        if route == '/api/version': return {'version': OLLAMA_VERSION}
        if route == '/api/tags': return {'models': [{'name': MODEL_NAME, 'digest': MANIFEST_DIGEST}]}
        assert route == '/api/generate'
        raise TimeoutError('SYNTHETIC_FAILURE_COUNTED')
    model.transport._request_json = transport
    payload = {'materials': [{'material_id': 'SYNTHETIC_TEST_ONLY',
                              'quote_candidates': ['This is a synthetic test-only quote.']}], 'changes': []}
    for _ in range(3):
        with pytest.raises(TimeoutError, match='SYNTHETIC_FAILURE_COUNTED'):
            model.generate(payload)
    before_refusal = path.read_bytes()
    with pytest.raises(BudgetError, match='p2_ai_budget_exhausted'):
        model.generate(payload)
    after = json.loads(path.read_text())
    assert after['intents'][:8] == original['intents'] and len(after['intents']) == 11
    assert path.read_bytes() == before_refusal and calls.count('/api/generate') == 3
