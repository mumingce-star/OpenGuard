"""Group plans share common semantics; raw facts and individual references remain."""
import json
from dataclasses import replace
import pytest
from app.ai.group_plan import clear_group_cache
from app.ai.provider import apply_ai_remediations
from app.domain.grouping import build_grouping
from app.domain.models import ScanRun
from test_a5_ai_provider import _run, FakeProvider

class GroupProvider(FakeProvider):
 group_plan_mode=True
 def generate(self,payload,timeout_seconds):
  p=json.loads(payload); self.calls.append((p,timeout_seconds))
  scope=p['context']['scope']
  return json.dumps({'group_id':p['group_id'],'summary':f'本组需要核对{scope}记录与适用许可之间的关系。',
   'steps':['依据逐项证据核对资源版本和声明位置。','查阅对应版本官方来源的许可原文并记录位置。','结合实际使用和分发条件逐条比对许可义务。'],
   'limitations':'实际用途及授权仍需人工核验，不能据此判定合规。'},ensure_ascii=False)

@pytest.fixture(autouse=True)
def cache_boundary():
 clear_group_cache();yield;clear_group_cache()

def test_group_cache_and_member_binding_without_per_member_calls():
 run=_run(two_findings=True);p=GroupProvider()
 result=apply_ai_remediations(run,p)
 assert result.status=='generated' and len(p.calls)==1
 assert len(result.run.remediations)==2
 groups=build_grouping(result.run)['groups']
 assert len(groups)==1 and groups[0]['advice']['kind']=='group_ai'
 assert set(groups[0]['finding_ids'])=={f.id for f in run.findings}
 assert len(groups[0]['resource_ids'])==1
 for r in result.run.remediations:
  finding=next(f for f in run.findings if f.id==r.finding_id)
  assert r.evidence_ids==finding.evidence_ids
 apply_ai_remediations(run,p)
 assert len(p.calls)==1
 assert all(k not in json.dumps(p.calls[0][0]) for k in [run.id,run.findings[0].id,run.components[0].name])
 for field in ('components','licenses','evidence','obligations','summary','status'):
  assert getattr(run,field)==getattr(result.run,field)

def test_changed_license_rule_trigger_scope_and_model_invalidate_plan():
 run=_run();p=GroupProvider();apply_ai_remediations(run,p)
 f=run.findings[0]
 for update in ({'rule_version':'0.9.9'},{'trigger':'Different verified distribution condition'}):
  new=run.model_copy(update={'findings':[f.model_copy(update=update)]})
  apply_ai_remediations(new,p)
 assert len(p.calls)==3
 p.producer=p.producer.model_copy(update={'version':'changed'})
 apply_ai_remediations(run,p);assert len(p.calls)==4

def test_group_split_preserves_severity_and_filtered_members():
 run=_run(two_findings=True)
 fs=list(run.findings);fs[1]=fs[1].model_copy(update={'rule_version':'different'})
 run=run.model_copy(update={'findings':fs})
 g=build_grouping(run);assert len(g['groups'])==2 and g['finding_count']==2 and g['resource_count']==1
 filtered=build_grouping(run,{fs[0].id});assert filtered['finding_count']==1
 assert [i for x in filtered['groups'] for i in x['finding_ids']]==[fs[0].id]
