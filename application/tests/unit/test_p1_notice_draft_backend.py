"""Fixed v2 package consumption through real NoticeDraft service and SQLite."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.assessment.store import AssessmentStore
from app.persistence import SQLiteScanRunRegistry
from app.p1.models import P1NoticeDraft
from app.p1.notice_draft import NoticeDraftService, NoticeDraftServiceError, resource_ids, evidence_refs
from app.p1.notice_facts import NoticeFactsInput, canonical, digest, validate_input
from app.p1.notice_draft_store import NoticeDraftStore, content_hash
from test_p1_history_api import seed
from test_p1_diff_api import assessment as make_assessment
from test_p1_contract_schema import validator

FACTS = json.loads(Path('tests/fixtures/notice-license-facts-v2/facts.json').read_text())


class FixtureReader:
    def __init__(self):
        self.package = copy.deepcopy(FACTS)
        self.sha = digest(self.package)
        self.calls = 0

    def read(self, scan_id, facts_hash):
        self.calls += 1
        return NoticeFactsInput(scan_id, facts_hash, self.package, self.sha)


@pytest.fixture
def notice_env(tmp_path):
    tmp_path.chmod(0o700)
    env = SimpleNamespace(path=tmp_path)
    env.registry = SQLiteScanRunRegistry(tmp_path/'scans.db')
    env.store = AssessmentStore(tmp_path/'assessment.db', min_free_bytes=0)
    env.store.initialize()
    env.run = seed(env, 701, 'completed', revision='notice-fixture')
    env.assessment = make_assessment(env, env.run)
    env.notice_store = NoticeDraftStore(tmp_path/'notice_draft.db', min_free_bytes=0)
    env.notice_store.initialize()
    env.reader = FixtureReader()
    env.service = NoticeDraftService(env.registry, env.store, env.notice_store, facts_reader=env.reader)
    yield env
    env.registry.close()


def create(env, key='notice-test'):
    return env.service.create(env.run.id, env.assessment.id, idempotency_key=key)


def hashes(env):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in env.path.glob('*.db')}


def test_fixture_acceptance_schema_and_authority(notice_env):
    env = notice_env
    before = hashes(env)
    draft = create(env).model_dump(mode='json')
    validator('NoticeDraft').validate(draft)
    assert len(draft['entries']) == 8
    assert sum(e['text'] is not None for e in draft['entries']) == 2
    assert all(not e['license_expression_ids'] and not e['obligation_refs'] for e in draft['entries'])
    assert all(not e['evidence_refs'] and not e['resource_ids'] for e in draft['entries'])
    assert 'authorization_pending' in draft['coverage_gaps']
    assert 'source_evidence_not_mapped_to_scan_namespace' in draft['coverage_gaps']
    assert digest(env.reader.package) == env.reader.sha == digest(FACTS)
    assert content_hash(draft) == draft['content_hash']
    assert all(hashes(env)[p] == h for p, h in before.items() if p != 'notice_draft.db')


def test_idempotency_dedup_restart_and_fixed_get(notice_env, monkeypatch):
    env = notice_env
    first = create(env)
    assert create(env) == first
    assert create(env, 'another-key') == first
    env.notice_store = NoticeDraftStore(env.path/'notice_draft.db', min_free_bytes=0)
    env.notice_store.initialize()
    env.service = NoticeDraftService(None, None, env.notice_store)
    before = hashes(env)
    for _ in range(5):
        assert env.service.get(env.run.id, env.assessment.id, first.draft_id) == first
    assert hashes(env) == before
    assert env.service.get('wrong-scan', env.assessment.id, first.draft_id) is None
    assert env.service.get(env.run.id, 'wrong-assessment', first.draft_id) is None


def test_same_key_changed_fixed_package_conflicts(notice_env):
    create(notice_env)
    notice_env.reader.package['producer']['version'] = '2.0.1'
    notice_env.reader.sha = digest(notice_env.reader.package)
    with pytest.raises(NoticeDraftServiceError) as error:
        create(notice_env)
    assert error.value.code == 'conflict'


@pytest.mark.parametrize('status,code', [('queued','not_ready'), ('running','not_ready'), ('failed','not_comparable'), ('cancelled','not_comparable')])
def test_status_gate(notice_env, status, code):
    env = notice_env
    run = seed(env, 702, status)
    before = hashes(env)
    with pytest.raises(NoticeDraftServiceError) as error:
        env.service.create(run.id, env.assessment.id, idempotency_key='status')
    assert error.value.code == code
    assert env.reader.calls == 0 and hashes(env) == before


def test_partial_accepted(notice_env):
    env = notice_env
    env.run = seed(env, 703, 'partial')
    env.assessment = make_assessment(env, env.run)
    assert create(env).binding.scan_ref.status == 'partial'


@pytest.mark.parametrize('field,value', [('scan_id','other'), ('id','other'), ('formal',False), ('facts_hash','0'*64)])
def test_fixed_assessment_binding(notice_env, monkeypatch, field, value):
    env = notice_env
    bad = env.assessment.model_copy(update={field:value})
    monkeypatch.setattr(env.store, 'get', lambda *a: bad)
    with pytest.raises(NoticeDraftServiceError) as error:
        create(env)
    assert error.value.code == 'conflict' and env.reader.calls == 0


@pytest.mark.parametrize('case', ['hash','version','policy','extra','duplicate_evidence','dangling','row','timestamp','source_hash','container','duplicate_fact','duplicate_row','binding','selected_value','pointer'])
def test_package_fail_closed(notice_env, case):
    env = notice_env
    p = env.reader.package
    if case == 'version': p['schema_version'] = 'openguard.notice-license-facts/3'
    elif case == 'policy': p['policies']['authorization_default'] = 'allowed'
    elif case == 'extra': p['facts'][0]['authorized'] = True
    elif case == 'duplicate_evidence': p['evidence'].append(copy.deepcopy(p['evidence'][0]))
    elif case == 'dangling': p['facts'][0]['relationships']['license']['evidence_ids'] = ['ev.unknown']
    elif case == 'row': p['report_v2_rows'][0]['gap_codes'] = []
    elif case == 'timestamp': p['generated_at'] = 'badZ'
    elif case == 'source_hash': p['source_package']['commit_blob_sha256'] = '0'*64
    elif case == 'container': p['evidence'][1]['container_sha256'] = '0'*64
    elif case == 'selected_value': p['facts'][5]['license_observations'][0]['raw_value'] = 'changed'
    elif case == 'pointer': p['evidence'][7]['selected_json_pointer'] = '/wrong'
    elif case == 'duplicate_fact': p['facts'].append(copy.deepcopy(p['facts'][0]))
    elif case == 'duplicate_row': p['report_v2_rows'].append(copy.deepcopy(p['report_v2_rows'][0]))
    elif case == 'binding': env.reader.read = lambda *a: NoticeFactsInput('wrong', '0'*64, p, digest(p))
    else: p['evidence'][0]['excerpt'] = 'tampered'
    if case != 'hash': env.reader.sha = digest(p)
    before = hashes(env)
    with pytest.raises(NoticeDraftServiceError) as error:
        create(env)
    assert error.value.reason == 'notice_facts_invalid'
    assert hashes(env) == before


def test_hash_includes_id_and_time_and_excludes_only_itself(notice_env):
    draft = create(notice_env).model_dump(mode='json')
    h = content_hash(draft)
    draft['content_hash'] = '0'*64
    assert content_hash(draft) == h
    for key in ('draft_id', 'created_at'):
        changed = copy.deepcopy(draft)
        changed[key] += 'x'
        assert content_hash(changed) != h
    with pytest.raises(ValueError):
        P1NoticeDraft.model_validate({**draft, 'extra': True})


def test_resource_exact_unique_and_ambiguous_mapping(notice_env):
    env = notice_env
    fact = validate_input(env.reader.read(env.run.id, env.assessment.facts_hash), env.run.id, env.assessment.facts_hash).facts[1]
    s = fact.subject
    resource = SimpleNamespace(id='cmp_exact', purl=s.canonical_id, version=s.version, source_url=s.source_url)
    run = SimpleNamespace(components=[resource], ai_assets=[])
    assert resource_ids(fact, run) == (['cmp_exact'], None)
    run.components.append(SimpleNamespace(**{**vars(resource), 'id':'cmp_second'}))
    assert resource_ids(fact, run) == ([], 'resource_ambiguous')
    run.components = [SimpleNamespace(**{**vars(resource), 'version':'other'})]
    assert resource_ids(fact, run) == ([], 'resource_not_mapped')


def test_evidence_does_not_match_id_or_excerpt_alone(notice_env):
    env = notice_env
    package = validate_input(env.reader.read(env.run.id, env.assessment.facts_hash), env.run.id, env.assessment.facts_hash)
    source = package.evidence[0].model_copy(update={'source_url':'https://github.com/Owner/Repo/blob/rev/LICENSE', 'source_revision':'rev'})
    ev = SimpleNamespace(id='evd_exact', kind='file', locator='LICENSE', excerpt=source.excerpt,
                         content_hash=SimpleNamespace(algorithm='sha256', value=source.selected_content_sha256), detected_by='manifest')
    run = SimpleNamespace(id='scn_fixed', project=SimpleNamespace(revision='rev',source='https://github.com/Owner/Repo'), evidence=[ev])
    assert evidence_refs(source, run) == [dict(namespace='scan',scan_id='scn_fixed',evidence_id='evd_exact')]
    run.project.revision = 'wrong'
    assert evidence_refs(source, run) == []
    run.project.revision = 'rev'
    run.evidence.append(ev)
    assert evidence_refs(source, run) == []
