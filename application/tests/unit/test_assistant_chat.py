"""Closed synthetic transports only: no real socket, HTTP service, or model."""
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant.service import AssistantService
from app.assistant.store import AssistantStore
from app.assistant.transport import ModelCoordinator
from app.api.assistant import router

class FakeProvider:
    def __init__(self, pause=False):
        self.calls=[]; self.entered=threading.Event(); self.release=threading.Event(); self.pause=pause
    def generate(self, messages, control, emit, *, schema=None):
        self.calls.append(messages); emit('你好，'); self.entered.set()
        if self.pause:
            while not self.release.wait(.01):
                control.check()
        control.check(); emit('这是**通用回答**。'); return {'done':True,'eval_count':8}

@pytest.fixture
def flow(tmp_path):
    tmp_path.chmod(0o700)
    store=AssistantStore(tmp_path/'assistant.db'); store.initialize()
    provider=FakeProvider(); svc=AssistantService(store,provider,ModelCoordinator(tmp_path/'model.lock'))
    app=FastAPI(); app.state.assistant_service=svc; app.include_router(router())
    with TestClient(app) as client: yield client,svc,provider,store

def conversation(c):
    r=c.post('/api/v1/assistant/conversations',json={'request_id':'create-request-01','context':None})
    assert r.status_code==201,r.text
    return r.json()['id']

def send(c,cid,key='message-request-01',question='解释一下Python列表推导式'): 
    return c.post(f'/api/v1/assistant/conversations/{cid}/messages',json={'request_id':key,'message':question})

def finish(c,cid,key='message-request-01'):
    r=c.get(f'/api/v1/assistant/conversations/{cid}/messages/{key}/events?after=0')
    assert r.status_code==200,r.text
    return [json.loads(x) for x in r.text.splitlines()]

def test_normal_question_stream_history_and_idempotency(flow):
    c,svc,p,store=flow; cid=conversation(c)
    r=send(c,cid); assert r.status_code==202,r.text
    events=finish(c,cid)
    assert [e['type'] for e in events]==['start','delta','delta','final']
    assert events[-1]['message']['status']=='completed'
    assert events[-1]['message']['citations']==[]
    assert '**通用回答**' in events[-1]['message']['text']
    assert send(c,cid).status_code==202 and len(p.calls)==1
    assert send(c,cid,question='different').status_code==409
    snap=c.get(f'/api/v1/assistant/conversations/{cid}').json()
    assert len(snap['items'])==2 and snap['limits']['total_call_limit'] is None
    assert snap['conversation']['title']=='解释一下Python列表推导式'
    assert c.get(f'/api/v1/assistant/conversations/{cid}/messages/message-request-01/events?after=2').text.count('"type"')==2
    assert len(p.calls)==1

def test_stop_preserves_partial_and_never_replays(flow):
    c,svc,p,store=flow; p.pause=True; cid=conversation(c)
    assert send(c,cid).status_code==202; assert p.entered.wait(1)
    stopped=c.post(f'/api/v1/assistant/conversations/{cid}/messages/message-request-01/stop',json={})
    assert stopped.status_code==200,stopped.text
    assert stopped.json()['message']['status']=='stopped'
    assert stopped.json()['message']['text']=='你好，'
    p.release.set(); events=finish(c,cid)
    assert events[-1]['type']=='stopped'
    assert send(c,cid).status_code==202 and len(p.calls)==1

def test_late_stop_does_not_rewrite_completed(flow):
    c,svc,p,store=flow; cid=conversation(c);send(c,cid);finish(c,cid)
    response=c.post(f'/api/v1/assistant/conversations/{cid}/messages/message-request-01/stop',json={})
    assert response.json()['message']['status']=='completed'

def test_wrong_context_and_input_rejected_before_model(flow):
    c,svc,p,store=flow; cid=conversation(c)
    assert send(c,cid,question=' ').status_code==422
    assert send(c,cid,question='x'*8001).status_code==422
    assert send(c,'chat_missing').status_code==404
    bad={'scan_id':'scn_fake','assessment_id':'asm_fake','assessment_version':1,'result_id':'r1','result_sha256':'f'*64}
    assert c.post('/api/v1/assistant/conversations',json={'request_id':'bad-project-01','context':bad}).status_code==503
    assert not p.calls

def test_history_pagination_and_rate_not_lifetime_budget(flow):
    c,svc,p,store=flow; cid=conversation(c)
    for i in range(10):
        key=f'message-rate-{i:02}'; assert send(c,cid,key).status_code==202; finish(c,cid,key)
    assert send(c,cid,'message-rate-11').status_code==429
    assert len(p.calls)==10
    a=c.get(f'/api/v1/assistant/conversations/{cid}?limit=3').json()
    assert len(a['items'])==3 and a['has_more'] is True
    b=c.get(f'/api/v1/assistant/conversations/{cid}?limit=3&cursor='+a['cursor']).json()
    assert len(b['items'])==3 and not set(x['id'] for x in a['items'])&set(x['id'] for x in b['items'])

def test_second_store_cannot_read_first_account(flow,tmp_path):
    c,svc,p,store=flow; cid=conversation(c)
    other=tmp_path/'other';other.mkdir(mode=0o700)
    s=AssistantStore(other/'assistant.db');s.initialize()
    from app.assistant.store import AssistantError
    with pytest.raises(AssistantError) as e:s.conversation(cid)
    assert e.value.status==404

class FakeSocket:
    def __init__(self):self.shutdown_event=threading.Event()
    def shutdown(self,how):self.shutdown_event.set()
class FakeResponse:
    def __init__(self,raw,*,status=200,headers=None,block_socket=None):
        import io
        self.data=io.BytesIO(raw);self.status=status;self.headers=headers or {};self.block_socket=block_socket;self.closed=False
    def read(self,n):return self.data.read(n)
    def readline(self,n):
        if self.block_socket:
            assert self.block_socket.shutdown_event.wait(3),'cancel did not shutdown response-owned socket'
            raise OSError('synthetic shutdown')
        return self.data.readline(n)
    def getheader(self,key):return self.headers.get(key)
    def close(self):self.closed=True
class FakeConnection:
    calls=[];frames=[];instances=[];identity_bad=False;status=200;block=False
    def __init__(self,*args,**kwargs):self.sock=FakeSocket();self.original_socket=self.sock;self.path=None;self.closed=False;type(self).instances.append(self)
    def request(self,method,path,body=None,headers=None):
        self.path=path;type(self).calls.append((method,path,json.loads(body) if body else None))
    def getresponse(self):
        from app.ai.ollama import MODEL_NAME,MANIFEST_DIGEST,OLLAMA_VERSION
        if self.path=='/api/version':raw=json.dumps({'version':'wrong' if self.identity_bad else OLLAMA_VERSION}).encode()
        elif self.path=='/api/tags':raw=json.dumps({'models':[{'name':MODEL_NAME,'digest':MANIFEST_DIGEST}]}).encode()
        else:
            raw=b''.join(json.dumps(x,ensure_ascii=False).encode()+b'\n' for x in self.frames)
        response=FakeResponse(raw,status=self.status if self.path=='/api/chat' else 200,
                              block_socket=self.original_socket if self.block and self.path=='/api/chat' else None)
        self.sock=None # actual HTTPConnection does this for response.will_close.
        return response
    def close(self):self.closed=True

@pytest.fixture
def wire():
    from app.assistant.transport import StreamingQwen
    from app.ai.ollama import MODEL_NAME
    FakeConnection.calls=[];FakeConnection.instances=[];FakeConnection.identity_bad=False;FakeConnection.status=200;FakeConnection.block=False
    FakeConnection.frames=[{'model':MODEL_NAME,'message':{'role':'assistant','content':'中文🙂'},'done':False},
                           {'model':MODEL_NAME,'message':{'role':'assistant','content':'完成'},'done':True,'done_reason':'stop'}]
    return StreamingQwen(connection_factory=FakeConnection)

def test_real_transport_ndjson_roles_and_exact_identity(wire):
    from app.assistant.transport import Cancellation
    chunks=[];metrics=wire.generate([{'role':'user','content':'你好'}],Cancellation(),chunks.append)
    assert chunks==['中文🙂','完成'] and metrics['done'] is True
    assert [x[1] for x in FakeConnection.calls]==['/api/version','/api/tags','/api/chat']
    assert FakeConnection.calls[-1][2]['stream'] is True
    assert 'format' not in FakeConnection.calls[-1][2]
    assert all(x.closed for x in FakeConnection.instances)

@pytest.mark.parametrize('kind',['identity','frame','truncated','http','tool','oversize'])
def test_real_transport_failure_has_no_retry_or_fallback(wire,kind):
    from app.assistant.transport import Cancellation
    from app.assistant.store import AssistantError
    if kind=='identity':FakeConnection.identity_bad=True
    if kind=='frame':FakeConnection.frames[-1]['model']='wrong'
    if kind=='truncated':FakeConnection.frames=FakeConnection.frames[:1]
    if kind=='http':FakeConnection.status=302
    if kind=='tool':FakeConnection.frames[0]['message']['tool_calls']=[{'function':'forbidden'}]
    if kind=='oversize':FakeConnection.frames[0]['message']['content']='x'*24001
    with pytest.raises(AssistantError):wire.generate([{'role':'user','content':'test'}],Cancellation(),lambda text:None)
    assert sum(x[1]=='/api/chat' for x in FakeConnection.calls)==(0 if kind=='identity' else 1)

def test_cancel_closes_detached_response_socket_and_releases_worker(wire,tmp_path):
    from app.assistant.transport import Cancellation
    FakeConnection.block=True;control=Cancellation();errors=[]
    thread=threading.Thread(target=lambda:_capture(wire,control,errors));thread.start()
    deadline=time.monotonic()+1
    while not any(c.path=='/api/chat' and c.sock is None for c in FakeConnection.instances) and time.monotonic()<deadline:time.sleep(.001)
    control.request('stopped');thread.join(1)
    assert not thread.is_alive() and errors
    assert FakeConnection.instances[-1].original_socket.shutdown_event.is_set()

def _capture(wire,control,errors):
    try:wire.generate([{'role':'user','content':'test'}],control,lambda text:None)
    except Exception as exc:errors.append(exc)

def test_global_slot_rejects_concurrent_account_without_call(flow):
    c,svc,p,store=flow;p.pause=True;cid=conversation(c)
    assert send(c,cid).status_code==202 and p.entered.wait(1)
    second=c.post('/api/v1/assistant/conversations',json={'request_id':'another-chat-01','context':None}).json()['id']
    assert send(c,second,'other-message-01').status_code==409
    c.post(f'/api/v1/assistant/conversations/{cid}/messages/message-request-01/stop',json={});p.release.set()

from test_p2_contract import setup as project_setup, create as create_result, material_body

class StrictFake:
    def __init__(self):self.calls=[];self.bad=False
    def generate(self,messages,control,emit,*,schema=None):
        payload=json.loads(messages[-1]['content']);self.calls.append(payload)
        value={'result_id':payload['scope']['result_id'],'result_sha256':payload['scope']['result_sha256'],
               'usage_echo':payload['usage'],
               'answer':'当前材料与具体交付文件的适用范围仍需核验，请先记录本组件的文件清单，再核对版权和许可声明保留位置；其他依赖需要分别补齐对应依据。',
               'citations':[{'basis_id':payload['evidence'][0]['basis_id'],'quote':payload['evidence'][0]['quote']}]}
        if self.bad:value['usage_echo']['distributed']=not payload['usage']['distributed']
        raw=json.dumps(value,ensure_ascii=False);emit(raw[:20]);emit(raw[20:]);return {'done':True}

@pytest.mark.parametrize('wrong',[False,True])
def test_project_context_reuses_actual_strict_validation(project_setup,wrong):
    client,app,base,body,root=project_setup
    first=create_result(project_setup)
    store=AssistantStore(root/'assistant.db');store.initialize();provider=StrictFake();provider.bad=wrong
    svc=AssistantService(store,provider,ModelCoordinator(root/'assistant.lock'),app.state.p2_service.project_chat)
    app.state.assistant_service=svc
    ref={'scan_id':first['binding']['scan_id'],'assessment_id':first['binding']['assessment_id'],
         'assessment_version':first['binding']['assessment_version'],'result_id':first['result_id'],'result_sha256':first['result_sha256']}
    r=client.post('/api/v1/assistant/conversations',json={'request_id':'project-create-01','context':ref})
    assert r.status_code==201,r.text
    cid=r.json()['id'];assert send(client,cid,question='现在需要核对什么？').status_code==202
    events=finish(client,cid)
    assert all(e['type']!='delta' for e in events),'project output exposed before validation'
    if wrong:
        assert events[-1]['type']=='error' and events[-1]['message']['text']==''
        assert events[-1]['message']['error_code']=='assistant_project_output_rejected'
    else:
        assert events[-1]['type']=='final',events
        assert events[-1]['message']['citations'][0]['label']
        detail=client.get(f'/api/v1/assistant/conversations/{cid}').json()
        assert detail['project_context']['scope']['result_sha256']==ref['result_sha256']
        assert detail['conversation']['context']==ref
        assert send(client,cid,'project-second-01','再解释一下').status_code==202
        assert finish(client,cid,'project-second-01')[-1]['type']=='final'
        assert provider.calls[-1]['history'][0].get('answer_excerpt')
    wrong_ref={**ref,'result_sha256':'f'*64}
    assert client.post('/api/v1/assistant/conversations',json={'request_id':'project-conflict-01','context':wrong_ref}).status_code==409

def test_actual_gateway_auth_csrf_and_account_isolation(tmp_path):
    from app.local_accounts import LocalAccountGateway
    origin='http://127.0.0.1:48671';shared=tmp_path/'shared';shared.mkdir(mode=0o700)
    def factory(root):
        s=AssistantStore(root/'assistant.db');s.initialize()
        app=FastAPI();app.state.assistant_service=AssistantService(s,FakeProvider(),ModelCoordinator(shared/'model.lock'));app.include_router(router());return app
    async def frontend(scope,receive,send):
        from starlette.responses import Response
        await Response('SYNTHETIC_TEST_ONLY')(scope,receive,send)
    gateway=LocalAccountGateway(root=tmp_path/'accounts',origins=(origin,),cookie_name='og_session_abcdef012345',app_factory=factory,frontend=frontend)
    with TestClient(gateway,base_url=origin) as c:
        assert c.get('/api/v1/assistant/conversations').status_code==401
        anon=c.get('/api/v1/auth/session').json()
        registered=c.post('/api/v1/auth/register',json={'username':'synthetic_chat_a','password':'SyntheticTest2026!'},headers={'Origin':origin,'X-CSRF-Token':anon['csrf_token']})
        assert registered.status_code==201
        auth=registered.json();headers={'Origin':origin,'X-CSRF-Token':auth['csrf_token']}
        assert c.post('/api/v1/assistant/conversations',json={'request_id':'account-create-01','context':None},headers={'Origin':origin}).status_code==403
        created=c.post('/api/v1/assistant/conversations',json={'request_id':'account-create-01','context':None},headers=headers)
        assert created.status_code==201,created.text
        cid=created.json()['id']
        assert c.post(f'/api/v1/assistant/conversations/{cid}/messages/invalid/stop',json={},headers=headers).status_code==403
        assert c.post('/api/v1/assistant/admin',json={},headers=headers).status_code==403
        assert c.post('/api/v1/auth/logout',json={},headers=headers).status_code==200
        anon=c.get('/api/v1/auth/session').json()
        other=c.post('/api/v1/auth/register',json={'username':'synthetic_chat_b','password':'SyntheticTest2026!'},headers={'Origin':origin,'X-CSRF-Token':anon['csrf_token']})
        assert other.status_code==201
        assert c.get(f'/api/v1/assistant/conversations/{cid}').status_code==404
        assert c.get('/api/v1/assistant/conversations').json()['items']==[]
