"""NoticeDraft authority and persistence tamper boundary."""
import copy
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.p1.notice_draft_store import NoticeDraftStoreError, content_hash
from app.p1.notice_facts import canonical
from test_p1_notice_draft_backend import notice_env, create, hashes


@pytest.mark.parametrize('case', ['content_hash','formal','provenance','evidence_scan','license','entry_extra','time','compact_time','bool_revision','duplicate_id'])
def test_payload_rehashed_tamper_rejected(notice_env, case):
    env = notice_env
    value = create(env).model_dump(mode='json')
    if case == 'content_hash': value['entries'][0]['text'] = 'tampered'
    elif case == 'formal': value['binding']['assessment_ref']['formal'] = False
    elif case == 'provenance': value['provenance']['source_refs'][0]['scan_id'] = 'other'
    elif case == 'evidence_scan': value['entries'][0]['evidence_refs'] = [dict(namespace='scan',scan_id='other',evidence_id='evd_fake')]
    elif case == 'license': value['entries'][0]['license_expression_ids'] = ['inferred']
    elif case == 'entry_extra': value['entries'][0]['authorized'] = True
    elif case == 'time': value['created_at'] = value['provenance']['generated_at'] = 'badZ'
    elif case == 'compact_time': value['created_at'] = value['provenance']['generated_at'] = '20260922T142000Z'
    elif case == 'bool_revision': value['binding']['scan_ref']['registry_revision'] = True
    else: value['entries'].append(copy.deepcopy(value['entries'][0]))
    if case != 'content_hash': value['content_hash'] = content_hash(value)
    raw = canonical(value)
    with sqlite3.connect(env.notice_store.path) as db:
        db.execute('UPDATE notice_drafts SET payload=?,payload_hash=?', (raw,hashlib.sha256(raw).hexdigest()))
    with pytest.raises(NoticeDraftStoreError): env.notice_store.get(env.run.id, env.assessment.id, value['draft_id'])


def test_concurrent_fixed_key_is_one_immutable_draft(notice_env):
    env = notice_env
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: create(env).draft_id, range(8)))
    assert len(set(results)) == 1
    with sqlite3.connect(env.notice_store.path) as db:
        assert db.execute('SELECT count(*) FROM notice_drafts').fetchone() == (1,)
        assert db.execute('SELECT count(*) FROM notice_requests').fetchone() == (1,)


def test_capacity_is_fail_closed(notice_env):
    env = notice_env
    env.notice_store.max_record_bytes = 1
    before = hashes(env)
    with pytest.raises(Exception) as error: create(env)
    assert error.value.reason == 'storage_capacity_exceeded'
    assert hashes(env) == before
