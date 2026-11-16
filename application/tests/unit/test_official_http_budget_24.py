"""TEST_ONLY budget extension; synthetic sockets, inherited usage never reset."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from app.ingestion import official_http_server as api
from test_official_http_server import Driver, offline


def ledger(count, limit):
    return {'version': api.VERSION_ID, 'max_task_http': limit, 'max_job_http': 6,
            'requests': [{'number': i + 1, 'job_key': 'historical-namespace:old',
                          'job_id': 'old', 'state': 'HISTORICAL_TEST_ONLY',
                          'dispatch_attempt_utc': '2026-10-23T00:00:00Z',
                          'first_sendall_completed_utc': None, 'http_status': 200}
                         for i in range(count)], 'jobs': {}}


def seed(client, count, limit):
    value = ledger(count, limit)
    client.budget_path.write_text(json.dumps(value))
    return deepcopy(value)


def test_explicit_24_inherits_17_and_allows_exact_six_without_reset(tmp_path):
    driver = Driver(); client = api.FixedOfficialFetcher(tmp_path, max_task_http=24, _wire_factory=driver.factory)
    before = seed(client, 17, 24)
    receipt = client.fetch('one-new-job')
    assert receipt['status'] == 'succeeded' and receipt['max_task_http'] == 24
    assert receipt['http_intents'] == receipt['http_dispatched'] == receipt['http_responses'] == 6
    assert receipt['task_http_intents'] == 23
    after = json.loads(client.budget_path.read_text())
    assert after['requests'][:17] == before['requests'] and len(after['requests']) == 23
    assert [r['number'] for r in receipt['requests']] == list(range(18, 24))
    assert client.fetch('one-new-job') == receipt and len(driver.requests) == 6
    refused = client.fetch('no-second-job')
    assert refused['error_code'] == 'official_source_http_budget_exhausted'
    assert refused['max_task_http'] == 24 and refused['task_http_intents'] == 23 and refused['http_intents'] == 0
    assert len(driver.requests) == 6


def test_intent_cannot_be_twenty_fifth_even_without_plan_guard(tmp_path):
    client = api.FixedOfficialFetcher(tmp_path, max_task_http=24)
    client._ledger = ledger(24, 24)
    job = {'job_id': 'twenty-fifth', 'job_key': client.namespace + ':twenty-fifth', 'request_numbers': []}
    before = deepcopy(client._ledger)
    with pytest.raises(ValueError, match='official_source_http_budget_exhausted'):
        client._intent(job, api.GIT_HOST, api.GIT_PATH, 'GET', None, None)
    assert client._ledger == before and job['request_numbers'] == []
    assert not client.budget_path.exists()


def test_default_18_still_refuses_inherited_17_before_first_http(tmp_path):
    driver = Driver(); client = api.FixedOfficialFetcher(tmp_path, _wire_factory=driver.factory)
    before = seed(client, 17, 18)
    receipt = client.fetch('one-new-job')
    assert receipt['error_code'] == 'official_source_http_budget_exhausted'
    assert receipt['max_task_http'] == 18 and receipt['task_http_intents'] == 17
    assert receipt['http_intents'] == 0 and driver.requests == []
    assert json.loads(client.budget_path.read_text())['requests'] == before['requests']


@pytest.mark.parametrize('value', [True, False, 18.0, 24.0, '24', None, 0, 17, 19, 25])
def test_invalid_constructor_limit_rejected_without_file_writes(tmp_path, value):
    root = tmp_path / 'new'
    with pytest.raises(ValueError, match='official_source_http_limit_invalid'):
        api.FixedOfficialFetcher(root, max_task_http=value)
    assert not root.exists()


@pytest.mark.parametrize('configured,saved', [(18, 24), (24, 18), (24, True), (24, 24.0)])
def test_wrong_ledger_limit_rejected_without_rewrite_or_network(tmp_path, configured, saved):
    driver = Driver(); client = api.FixedOfficialFetcher(tmp_path, max_task_http=configured, _wire_factory=driver.factory)
    seed(client, 17, saved); before = client.budget_path.read_bytes()
    with pytest.raises(ValueError, match='official_source_budget_invalid'):
        client.fetch('mismatched')
    assert client.budget_path.read_bytes() == before and driver.requests == []
    with api._SERIAL:
        with pytest.raises(ValueError, match='official_source_budget_invalid'):
            client.fetch('busy-mismatched')
    assert client.budget_path.read_bytes() == before


def test_busy_24_reports_actual_instance_budget_and_consumption(tmp_path):
    client = api.FixedOfficialFetcher(tmp_path, max_task_http=24)
    seed(client, 17, 24); before = client.budget_path.read_bytes()
    with api._SERIAL:
        out = client.fetch('busy')
    assert out['error_code'] == 'official_source_busy' and out['max_task_http'] == 24
    assert out['task_http_intents'] == 17 and out['http_intents'] == 0
    assert client.budget_path.read_bytes() == before


@pytest.mark.parametrize('value,expected', [(None, 18), ('18', 18), ('24', 24)])
def test_runtime_passes_only_explicit_budget_setting(tmp_path, monkeypatch, value, expected):
    from app.api.official_runtime import configure_official_sources
    import app.p2.official_sources as source_module
    seen = []
    monkeypatch.setenv('OPENGUARD_OFFICIAL_SOURCE_AUTO', '1')
    monkeypatch.setenv('OPENGUARD_P2_AI_MAX_GENERATIONS', '10')
    monkeypatch.setenv('OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH', str(tmp_path / 'budget.json'))
    if value is None: monkeypatch.delenv('OPENGUARD_OFFICIAL_HTTP_MAX_TASK', raising=False)
    else: monkeypatch.setenv('OPENGUARD_OFFICIAL_HTTP_MAX_TASK', value)
    monkeypatch.setattr(source_module, 'OfficialSourceService', lambda p2, root, fetcher, ai, **kw: seen.append(fetcher) or SimpleNamespace())
    p2 = SimpleNamespace(readonly=False, data_scope='TEST_ONLY', ai_analysis=object())
    configure_official_sources(p2, SimpleNamespace(assessment_saved_observer=None), None, tmp_path)
    assert len(seen) == 1 and seen[0].max_task_http == expected
    assert not (tmp_path / 'budget.json').exists()


@pytest.mark.parametrize('value', ['true', '24.0', ' 24', '024', '25', ''])
def test_invalid_runtime_limit_fails_before_constructing_fetcher(tmp_path, monkeypatch, value):
    from app.api.official_runtime import configure_official_sources
    monkeypatch.setenv('OPENGUARD_OFFICIAL_SOURCE_AUTO', '1')
    monkeypatch.setenv('OPENGUARD_P2_AI_MAX_GENERATIONS', '10')
    monkeypatch.setenv('OPENGUARD_OFFICIAL_HTTP_BUDGET_PATH', str(tmp_path / 'budget.json'))
    monkeypatch.setenv('OPENGUARD_OFFICIAL_HTTP_MAX_TASK', value)
    monkeypatch.setattr(api, 'FixedOfficialFetcher', lambda *a, **kw: pytest.fail('fetcher constructed for invalid limit'))
    p2 = SimpleNamespace(readonly=False, data_scope='TEST_ONLY', ai_analysis=object())
    with pytest.raises(RuntimeError, match='invalid official HTTP task limit'):
        configure_official_sources(p2, SimpleNamespace(assessment_saved_observer=None), None, tmp_path)
