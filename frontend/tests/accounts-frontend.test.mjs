import test from 'node:test';
import assert from 'node:assert/strict';
import { runtime } from './runtime.mjs';

const OWNER='openguard:account-cache-owner:v1';
const archive=(id,key)=>'openguard:account-cache:v1:'+encodeURIComponent(id)+':'+key;
const session=(id='user_TEST_ONLY_A',token='test_only_csrf_token_A_1234567890')=>({user:id?{id,username:'TEST_ONLY'}:null,csrf_token:token});
function store(initial={}) {
  const map=new Map(Object.entries(initial));
  return {map,get length(){return map.size;},key(i){return [...map.keys()][i]??null;},getItem(key){return map.get(key)??null;},setItem(key,value){map.set(key,String(value));},removeItem(key){map.delete(key);}};
}
function setup(env={VITE_ACCOUNT_AUTH:'1'},local={},tab={}) {
  const r=runtime(env),redirects=[];
  r.shared.Headers=Headers;r.shared.sessionStorage=store(tab);r.shared.localStorage=store(local);
  r.shared.window.location={pathname:'/app/history',search:'?mode=api',replace:url=>redirects.push(url)};
  r.shared.window.addEventListener=()=>{};r.shared.window.removeEventListener=()=>{};
  return {r,auth:r.load('services/auth.ts'),redirects};
}
test('account session GET is deduplicated and credentials never enter storage',async()=>{
  const {r,auth}=setup(),calls=[];
  r.setFetch(async(url,init)=>{calls.push({url,init});return Response.json(session());});
  const [a,b]=await Promise.all([auth.readAccountSession(),auth.readAccountSession()]);
  assert.equal(a.user.id,b.user.id);assert.equal(calls.length,1);
  assert.equal(calls[0].url,'/api/v1/auth/session');assert.equal(calls[0].init.credentials,'same-origin');
  for(const storage of [r.shared.sessionStorage,r.shared.localStorage])for(const [key,value]of storage.map){assert.doesNotMatch(key,/password|csrf/i);assert.doesNotMatch(value,/csrf_token_A/);}
});
test('register uses anonymous CSRF then business POST uses rotated in-memory CSRF',async()=>{
  const {r,auth}=setup(),calls=[];
  r.setFetch(async(url,init)=>{calls.push({url,init});return Response.json(url.endsWith('/session')?session(null):session());});
  const password='  TEST_ONLY secret password  ';
  await auth.submitAccount('register','test_account',password);
  const sent=calls[1];assert.equal(sent.init.method,'POST');assert.equal(JSON.parse(sent.init.body).password,password);
  assert.equal(sent.init.headers['X-CSRF-Token'],session(null).csrf_token);
  const init=auth.accountRequestOptions({method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  assert.equal(init.headers.get('X-CSRF-Token'),session().csrf_token);assert.equal(init.credentials,'same-origin');
  assert.equal(init.headers.get('Content-Type'),'application/json');
});
test('unauthenticated business writes stop before network and legacy flag-off keeps exact options',()=>{
  const {auth}=setup();assert.throws(()=>auth.accountRequestOptions({method:'POST'}),e=>e.status===401);
  const legacy=setup({VITE_ACCOUNT_AUTH:'0'}).auth,options={method:'POST',headers:{'Content-Type':'application/json'}};
  assert.equal(legacy.accountRequestOptions(options),options);
});
test('the real scan service applies account CSRF and sends exactly one explicit POST',async()=>{
  const {r,auth}=setup(),calls=[];
  r.setFetch(async(url,init)=>{calls.push({url,init});return Response.json(url.endsWith('/auth/session')?session():{scan_id:'TEST_ONLY_SCAN',status:'queued',status_url:'/api/v1/scans/TEST_ONLY_SCAN'});});
  await auth.readAccountSession();const scans=r.load('services/scans.ts');
  const created=await scans.createApiScan({kind:'github',url:'https://github.com/http-party/http-server'},'TEST_ONLY_REQUEST');
  assert.equal(created.id,'TEST_ONLY_SCAN');assert.equal(calls.length,2);assert.equal(calls[1].url,'/api/v1/scans');
  assert.equal(calls[1].init.headers.get('X-CSRF-Token'),session().csrf_token);assert.equal(calls[1].init.credentials,'same-origin');
  assert.throws(()=>scans.createDemo(),/仅保存真实扫描/);await assert.rejects(scans.getScan('TEST_ONLY_SCAN','mock'),/不读取合成演示/);
});
test('failed logout preserves authenticated state, successful logout revokes new business POST',async()=>{
  const {r,auth}=setup();let fail=true;
  r.setFetch(async(url)=>url.endsWith('/session')?Response.json(session()):fail?Response.json({error:{code:'temporary',message:'TEST_ONLY retry'}},{status:503}):Response.json(session(null)));
  await auth.readAccountSession();await assert.rejects(auth.submitAccount('logout'),e=>e.status===503);
  assert.doesNotThrow(()=>auth.accountRequestOptions({method:'POST'}));fail=false;
  await auth.submitAccount('logout');assert.throws(()=>auth.accountRequestOptions({method:'POST'}),e=>e.status===401);
});
test('401 navigates to safe login once per response without replaying original POST',async()=>{
  const {r,auth,redirects}=setup();let calls=0;
  r.setFetch(async()=>{calls++;return Response.json(session());});await auth.readAccountSession();
  auth.handleAccountResponse(401);assert.equal(calls,1);assert.equal(redirects.length,1);assert.match(redirects[0],/^\/login\?next=/);
  assert.throws(()=>auth.accountRequestOptions({method:'POST'}));
});
test('return URLs remain same-origin app routes and account mode is forced to api',()=>{
  const {auth}=setup();
  for(const value of ['https://evil.invalid/','//evil.invalid','/app/../../login','/app/\\evil','/login',null])assert.equal(auth.safeAccountNext(value),'/app/new-scan?mode=api');
  assert.equal(auth.safeAccountNext('/app/scans/TEST_ONLY/assessment?mode=mock&p2_result=old'),'/app/scans/TEST_ONLY/assessment?mode=api&p2_result=old');
});
test('different tab and shared-store owners cannot relabel account B references as account A',async()=>{
  const reference='openguard.report-references.v1:TEST_ONLY_B',pending='openguard:project-usage:1:TEST_ONLY_A:a1';
  const {r,auth}=setup({VITE_ACCOUNT_AUTH:'1'},{[OWNER]:'user_TEST_ONLY_B',[reference]:'saved_B',unrelated:'keep'},
    {[OWNER]:'user_TEST_ONLY_A',[pending]:'original_request_A'});
  r.setFetch(async()=>Response.json(session('user_TEST_ONLY_B')));await auth.readAccountSession();
  assert.equal(r.shared.localStorage.getItem(reference),'saved_B');
  assert.equal(r.shared.localStorage.getItem(archive('user_TEST_ONLY_A',reference)),null);
  assert.equal(r.shared.sessionStorage.getItem(pending),null);
  assert.equal(r.shared.sessionStorage.getItem(archive('user_TEST_ONLY_A',pending)),'original_request_A');
  assert.equal(r.shared.localStorage.getItem('unrelated'),'keep');
});
test('logout archives only known account caches and login restores exact pending request identity',async()=>{
  const pending='openguard:project-usage:1:TEST_ONLY_A:a1',body='{"requestId":"TEST_ONLY_ORIGINAL","assessmentAttempted":true}';
  const {r,auth}=setup({VITE_ACCOUNT_AUTH:'1'},{unrelated:'kept'},{[OWNER]:'user_TEST_ONLY_A',[pending]:body});
  r.setFetch(async url=>Response.json(url.endsWith('/logout')?session(null):session()));
  await auth.readAccountSession();await auth.submitAccount('logout');
  assert.equal(r.shared.sessionStorage.getItem(pending),null);assert.equal(r.shared.sessionStorage.getItem(archive('user_TEST_ONLY_A',pending)),body);
  await auth.submitAccount('login','test_account','TEST_ONLY_LONG_PASSWORD');
  assert.equal(r.shared.sessionStorage.getItem(pending),body);assert.equal(r.shared.localStorage.getItem('unrelated'),'kept');
});
test('malformed session and CSRF are refused rather than granting a user',async()=>{
  const {r,auth}=setup();r.setFetch(async()=>Response.json({...session(),csrf_token:'short'}));
  await assert.rejects(auth.readAccountSession(),/会话响应不完整/);assert.throws(()=>auth.accountRequestOptions({method:'POST'}));
});
