from pathlib import Path, PurePosixPath
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from hashlib import sha256
from zipfile import ZipFile
from datetime import datetime, timezone
import base64, io, json, re, secrets, sys, time

ROOT=Path(__file__).resolve().parents[1]
BASE=sys.argv[1].rstrip('/')
from urllib.parse import urlsplit
u=urlsplit(BASE)
assert u.scheme=='http' and u.hostname=='127.0.0.1' and u.port and not u.path and not u.username and not u.password, 'Local test URL required'
OUT=Path(sys.argv[2]).resolve()
assert OUT.is_relative_to(ROOT/'runtime/self-tests'), 'Isolated evidence path required'
OUT.mkdir(mode=0o700,exist_ok=False)
ledger=[];checks=[]
def utc():return datetime.now(timezone.utc).isoformat()
def save():
 (OUT/'INDEX.json').write_text(json.dumps({'started_utc':START,'requests':ledger,'checks':checks,'public_http':0,'model_generations':0},ensure_ascii=False,indent=2)+'\n')
START=utc()
class Client:
 def __init__(self):
  self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(CookieJar()));self.csrf=None
 def call(self,method,path,body=None,expect=(200,),raw_body=None,content_type=None):
  raw=None if body is None else json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
  headers={'Origin':BASE,'Accept':'application/json'}
  if raw_body is not None:raw=raw_body
  if raw is not None:headers['Content-Type']=content_type or 'application/json';headers['x-csrf-token']=self.csrf or ''
  started=utc();request=Request(BASE+path,data=raw,headers=headers,method=method)
  try:r=self.opener.open(request,timeout=60)
  except HTTPError as e:r=e
  status=r.code;data=r.read();ctype=r.headers.get('Content-Type','')
  sensitive='/auth/' in path
  n=len(ledger)+1;entry={'n':n,'utc':started,'method':method,'path':path,'status':status,'response_bytes':len(data),'response_sha256':sha256(data).hexdigest(),'auth_values_omitted':sensitive}
  if not sensitive:
   suffix='.zip' if 'zip' in ctype else '.json' if 'json' in ctype else '.html' if 'html' in ctype else '.bin'
   filename=f'{n:03d}_response'+suffix;(OUT/filename).write_bytes(data);entry['response_file']=filename
   if raw is not None:
    f=f'{n:03d}_request.json';(OUT/f).write_bytes(raw);entry.update({'request_file':f,'request_sha256':sha256(raw).hexdigest()})
  ledger.append(entry);save()
  assert status in expect, f'{method} {path}: {status}: {data[:1200]!r}'
  value=json.loads(data) if 'json' in ctype else data
  if sensitive and isinstance(value,dict) and 'csrf_token' in value:self.csrf=value['csrf_token']
  return value,data,dict(r.headers)
 def get(self,path,expect=(200,)):return self.call('GET',path,expect=expect)
 def post(self,path,body,expect=(200,201,202)):return self.call('POST',path,body,expect)
def check(name,condition,**details):
 assert condition,name
 checks.append({'name':name,'status':'PASS',**details});save();print('PASS '+name,flush=True)
def poll(fn,done,seconds=60):
 end=time.monotonic()+seconds
 while True:
  x=fn()
  if done(x):return x
  assert time.monotonic()<end, f'poll timeout: {x}'
  time.sleep(.25)

client=Client()
health,_,_=client.get('/healthz');check('health_and_test_only',health['status']=='ok' and health['data_scope']=='TEST_ONLY')
_,html,_=client.get('/login');html=html.decode();assets=re.findall(r'(?:src|href)="(/assets/[^\"]+)"',html)
check('prebuilt_entry_has_assets',len(assets)>=2)
for asset in assets:client.get(asset)
session,_,_=client.get('/api/v1/auth/session');check('fresh_unauthed_session',session['user'] is None)
username='packcheck_'+secrets.token_hex(4);password='Pack'+secrets.token_hex(7)
auth,_,_=client.post('/api/v1/auth/register',{'username':username,'password':password},expect=(201,));check('registration',auth['user']['username']==username)
client.post('/api/v1/auth/logout',{},expect=(200,))
auth,_,_=client.post('/api/v1/auth/login',{'username':username,'password':password},expect=(200,));check('login_after_logout',auth['user']['username']==username)
client.get('/api/v1/scans')
usage={'preset':'personal','commercial':False,'modified':False,'distributed':False,'network_service':False,'training':False,'redistributed_assets':False,'source_disclosure':None}
archive=(ROOT/'samples/is-number-7.0.0-derived.zip').read_bytes()
check('input_zip_identity',len(archive)==4172 and sha256(archive).hexdigest()=='a70563664327b7dc5ad8ee99136c508534e2cef3aeb690beb13b13ed710bca06')
boundary='OpenGuardPackage'+secrets.token_hex(8)
parts=[]
for key,value in [('source_type','zip'),('idempotency_key','package_scan_'+secrets.token_hex(8)),('usage',json.dumps(usage))]:
 parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode())
parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="is-number-7.0.0-derived.zip"\r\nContent-Type: application/zip\r\n\r\n').encode()+archive+f'\r\n--{boundary}--\r\n'.encode())
accepted,_,_=client.call('POST','/api/v1/scans',expect=(202,),raw_body=b''.join(parts),content_type='multipart/form-data; boundary='+boundary)
sid=accepted['scan_id'];sp='/api/v1/scans/'+sid
runstatus=poll(lambda:client.get(sp)[0],lambda x:x.get('status') in ('completed','failed','partial'),90)
check('new_fixed_snapshot_scan_completes',runstatus['status']=='completed',scan_id=sid)
progress,_,_=client.get(sp+'/progress-events')
resources,_,_=client.get(sp+'/resources');report,_,_=client.get(sp+'/report?format=json&download=true')
print('RESOURCE SHAPE',str(resources)[:700],flush=True)
print('REPORT KEYS',list(report),flush=True)
alist=poll(lambda:client.get(sp+'/assessments')[0],lambda x:bool(x.get('items')),30)
a1=alist['items'][0];aid1=a1['id'];a1,_,_=client.get(sp+'/assessments/'+aid1)
check('initial_assessment_v1',a1['version']==1 and a1['scan_id']==sid)
def pfx(aid):return sp+'/assessments/'+aid+'/p2'
def create_result(a):
 prefix=pfx(a['id']);binding,_,_=client.get(prefix+'/binding');client.get(prefix+'/results?assessment_version='+str(a['version']))
 receipt,_,_=client.post(prefix+'/results',{'binding':binding,'expected_revision':0,'parent_result_id':None,'idempotency_key':'package_result_'+secrets.token_hex(8)},expect=(201,))
 result=receipt['result'];url=prefix+'/results/'+result['result_id']+'?assessment_version='+str(a['version'])
 fixed,raw,_=client.get(url);summary,sraw,_=client.get(prefix+'/results/'+result['result_id']+'/summary?assessment_version='+str(a['version']))
 check('result_and_summary_'+a['id'],fixed==result and summary['result_id']==result['result_id'] and summary['result_revision']==1 and summary['result_sha256']==result['result_sha256'] and summary['binding']==binding)
 return binding,result,raw,sraw
b1,r1,r1raw,s1raw=create_result(a1)
usage2={**usage,'preset':'closed_source','commercial':True,'modified':True,'distributed':True,'network_service':False,'source_disclosure':False}
req='package_usage_'+secrets.token_hex(8)
client.post(sp+'/assessments',{'request_id':req,'usage':usage2},expect=(202,))
job=poll(lambda:client.get(sp+'/assessments/jobs/'+req)[0],lambda x:x['status']!='pending',60)
check('usage_save_job_succeeded',job['status']=='succeeded')
a2,_,_=client.get(sp+'/assessments/'+job['assessment_id']);check('usage_creates_assessment_v2',a2['version']==2 and a2['usage']['commercial'] is True and a2['usage']['source_disclosure'] is False and a2['usage_hash']!=a1['usage_hash'])
b2,r2before,r2before_raw,s2before_raw=create_result(a2)
rows=r2before['resources'];run=report.get('scan_run',report.get('run',report))
components=run['components'];target=[x for x in components if x['name']=='is-number' and x['version']=='7.0.0']
check('exact_scanned_resource_found',len(target)==1)
component=target[0];rid=component['id'];row=next(x for x in rows if x['subject']['resource_id']==rid)
check('same_scan_evidence_relation',bool(row['evidence_ids']) and set(row['evidence_ids']).issubset(set(a2['evidence_ids'])))
claims_before,_,_=client.get(pfx(a2['id'])+'/results/'+r2before['result_id']+'/material-claims?assessment_version=2')
root_before=[x for x in claims_before['advice'] if x['subject']==row['subject']]
check('v3_root_initial_unknown',len(root_before)==3 and all(x['state']=='UNKNOWN' for x in root_before))
license_raw=(ROOT/'samples/is-number-LICENSE.txt').read_bytes()
body={'binding':b2,'expected_revision':1,'parent_result_id':r2before['result_id'],'idempotency_key':'package_material_'+secrets.token_hex(8),'subject':row['subject'],'evidence_ids':row['evidence_ids'],'filename':'LICENSE','content_base64':base64.b64encode(license_raw).decode(),'source_sha256':sha256(license_raw).hexdigest(),'source_description':'is-number 7.0.0 release LICENSE from the packaged fixed npm source record. TEST_ONLY SYNTHETIC_USAGE; not publisher certification or legal sign-off.','completeness':'FULL_TEXT_CLAIMED'}
receipt,_,_=client.post(pfx(a2['id'])+'/materials',body,expect=(201,));material=receipt['material'];r2=receipt['result']
check('material_201_pending_unverified',material['verification_state']=='pending' and material['source_level']=='user_supplied_unverified' and material['source_sha256']==sha256(license_raw).hexdigest())
check('material_result_r1_to_r2',r2['revision']==2 and r2['previous_result_id']==r2before['result_id'] and r2['binding']==b2 and r2['model_calls']==0)
check('target_only_recomputed_peers_reused',r2['recomputed_resource_ids']==[rid] and len(r2['reused_resource_ids'])==len(rows)-1 and all(x==next(y for y in r2['resources'] if y['subject']==x['subject']) for x in rows if x['subject']['resource_id']!=rid))
claims_after,_,_=client.get(pfx(a2['id'])+'/results/'+r2['result_id']+'/material-claims?assessment_version=2')
root_after=[x for x in claims_after['advice'] if x['subject']==row['subject']]
check('v3_root_conditional_support',claims_after['schema_version']=='openguard-material-claims/3' and len(root_after)==3 and all(x['state']=='SUPPORT' for x in root_after))
claims_old,_,_=client.get(pfx(a2['id'])+'/results/'+r2before['result_id']+'/material-claims?assessment_version=2')
check('old_material_claims_immutable',claims_old==claims_before)
repeat,_,_=client.post(pfx(a2['id'])+'/materials',body,expect=(201,));check('same_key_same_body_idempotent',repeat==receipt)
client.post(pfx(a2['id'])+'/materials',{**body,'source_description':body['source_description']+' changed'},expect=(409,));check('same_key_different_body_conflict',True)
client.post(pfx(a2['id'])+'/materials',{**body,'idempotency_key':'package_cas_'+secrets.token_hex(8)},expect=(409,));check('stale_cas_conflict',True)
client.post(pfx(a2['id'])+'/materials',{**body,'expected_revision':2,'parent_result_id':r2['result_id'],'idempotency_key':'package_bad_hash_'+secrets.token_hex(8),'source_sha256':'0'*64},expect=(422,));check('wrong_hash_rejected',True)
newfixed,newraw,_=client.get(pfx(a2['id'])+'/results/'+r2['result_id']+'?assessment_version=2')
newsum,_,_=client.get(pfx(a2['id'])+'/results/'+r2['result_id']+'/summary?assessment_version=2')
client.get(pfx(a2['id'])+'/materials/'+material['material_id']+'?assessment_version=2')
client.get(pfx(a2['id'])+'/results/'+r2['result_id']+'/automatic-review?assessment_version=2')
check('new_summary_bound_to_r2',newsum['result_id']==r2['result_id'] and newsum['result_revision']==2 and newsum['result_sha256']==r2['result_sha256'] and newsum['binding']==b2 and newsum['material_ids']==r2['material_ids'])
for a,result,raw0,sraw0 in [(a1,r1,r1raw,s1raw),(a2,r2before,r2before_raw,s2before_raw)]:
 _,raw,_=client.get(pfx(a['id'])+'/results/'+result['result_id']+'?assessment_version='+str(a['version']))
 _,sraw,_=client.get(pfx(a['id'])+'/results/'+result['result_id']+'/summary?assessment_version='+str(a['version']))
 check('old_result_summary_immutable_'+a['id'],raw==raw0 and sraw==sraw0)
client.get(pfx(a2['id'])+'/results/'+r2['result_id']+'?assessment_version=1',expect=(409,422,404));check('cross_version_read_rejected',True)
snapshot,_,_=client.post(sp+'/assessments/'+a2['id']+'/report-v2',{'idempotency_key':'package_report_'+secrets.token_hex(8),'task_refs':[],'notice_refs':[],'algorithm_refs':[]},expect=(200,201))
check('report_archive_created',bool(snapshot.get('snapshot_id')))
for fmt in ('html','json'):client.get(sp+'/assessments/'+a2['id']+'/report-v2/'+snapshot['snapshot_id']+'?format='+fmt)
_,zraw,zheaders=client.get(pfx(a2['id'])+'/results/'+r2['result_id']+'/evaluation-package?assessment_version=2&report_snapshot_id='+snapshot['snapshot_id'])
with ZipFile(io.BytesIO(zraw)) as z:
 check('complete_export_crc_path_safety',z.testzip() is None and len(set(z.namelist()))==len(z.namelist()) and all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts for n in z.namelist()),members=z.namelist(),sha256=sha256(zraw).hexdigest())
 manifest=json.loads(z.read('VERSION_BINDING.json'))
 exported_result=json.loads(z.read('02_P2/Result.json')); exported_summary=json.loads(z.read('02_P2/Summary.json'))
 check('export_manifest_fixed_result',manifest['result_id']==r2['result_id'] and manifest['result_revision']==r2['revision'] and manifest['binding']==r2['binding'] and exported_result==r2 and exported_summary['result_sha256']==r2['result_sha256'])
 hashes=json.loads(z.read('FILE_HASHES.json'))
 check('all_export_members_hashes_verified',all(len(z.read(n))==v['byte_count'] and sha256(z.read(n)).hexdigest()==v['sha256'] for n,v in hashes.items()))
other=Client();other.get('/api/v1/auth/session');username='isolation_'+secrets.token_hex(4);password='Other'+secrets.token_hex(6)
other.post('/api/v1/auth/register',{'username':username,'password':password},expect=(201,))
other.get(sp,expect=(403,404));check('account_scan_isolation',True)
history,_,_=other.get('/api/v1/assistant/conversations')
check('new_account_empty_chat_history',history['items']==[])
conversation,_,_=other.post('/api/v1/assistant/conversations',{'request_id':'package_chat_'+secrets.token_hex(8),'context':None},expect=(201,))
check('chat_conversation_created_without_generation',bool(conversation['id']) and conversation['context'] is None)
other.post('/api/v1/auth/logout',{},expect=(200,));other.post('/api/v1/auth/login',{'username':username,'password':password},expect=(200,))
detail,_,_=other.get('/api/v1/assistant/conversations/'+conversation['id'])
check('chat_history_persists_after_relogin',detail['conversation']==conversation and detail['items']==[])
save();print(json.dumps({'status':'PASS','checks':len(checks),'requests':len(ledger),'scan_id':sid,'assessment_versions':[1,2],'result_revision':r2['revision'],'model_generations':0,'public_http':0},ensure_ascii=False))
