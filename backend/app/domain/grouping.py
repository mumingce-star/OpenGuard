"""Pure versioned grouping projection shared by AI planning, API and reports.

Only common structured conditions enter the plan. Member facts stay in ScanRun;
no representative excerpt is passed off as evidence for another member.
"""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from typing import Any
from app.domain.models import ScanRun, RiskFinding

GROUPING_VERSION = 'openguard.grouping/v1'
LEVELS = ('critical', 'high', 'medium', 'low', 'info')
_CATEGORIES = {
 'license-evidence-gate': ('license-evidence', '许可证据待核验'),
}

def canonical(value: Any) -> str:
 return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def _context(run: ScanRun, finding: RiskFinding, resources: dict, licenses: dict, evidence: dict, obligations: dict) -> dict:
 resource = resources[finding.resource_id]
 lic = licenses.get(resource.license_expression_id)
 refs = [evidence[i] for i in finding.evidence_ids]
 paths = ' '.join(e.locator for e in refs)
 if 'examples/' in paths: scope = '示例'
 elif any(s in paths for s in ('uv.lock', 'poetry.lock', 'package-lock', 'yarn.lock')): scope = '锁文件'
 elif 'build-system' in paths: scope = '构建'
 elif 'dependency-groups' in paths or 'optional-dependencies' in paths: scope = '依赖组'
 elif any(e.kind.value == 'tool_output' for e in refs): scope = '工具'
 else: scope = '声明'
 license_refs = [evidence[i] for i in (lic.evidence_ids if lic else [])]
 # These are observations about evidence, never a claim about actual deployment.
 usage = '实际使用与分发情境未知；只确认上述证据出现的位置'
 coverage = sorted({(e.stage.value, e.code, e.message) for e in run.errors
                    if e.stage.value not in ('ai_assist', 'report')})
 obligation_conditions = []
 for oid in finding.obligation_ids:
  o = obligations[oid]
  obligation_conditions.append({k:o.model_dump(mode='json')[k] for k in
   ('action','trigger','description','rule_id','rule_version','verification_status')})
 return {'grouping_version':GROUPING_VERSION, 'rule_id':finding.rule_id,
  'rule_version':finding.rule_version, 'trigger':finding.trigger,
  'outcome':finding.outcome.value, 'severity':finding.severity.value,
  'resource_kind':finding.resource_kind,
  'resource_type':str(getattr(resource,'asset_type',getattr(resource,'ecosystem','unknown'))),
  'license_expression':lic.expression if lic else None,
  'license_status':lic.verification_status.value if lic else 'unknown',
  'license_evidence_kinds':sorted({e.kind.value for e in license_refs}),
  'license_evidence_statuses':sorted({e.verification_status.value for e in license_refs}),
  'license_text_observed':any(e.kind.value == 'license_text' and bool(e.excerpt) for e in license_refs),
  'evidence_kinds':sorted({e.kind.value for e in refs}),
  'evidence_statuses':sorted({e.verification_status.value for e in refs}),
  'evidence_present':bool(refs), 'scope':scope,
  'version_basis':'版本记录存在（具体版本逐项查看）' if resource.version else '未记录固定版本（逐项核对声明约束）',
  'usage':usage, 'obligations':sorted(obligation_conditions,key=canonical), 'coverage':coverage}

def _category(context: dict) -> tuple[str,str]:
 if context['rule_id'] in _CATEGORIES: return _CATEGORIES[context['rule_id']]
 # Only explicit existing rule IDs; never infer severity or authorization from titles.
 rule=context['rule_id']
 if rule.startswith('license-obligation-'): return ('license-obligations','许可义务待核对')
 return ('other-rules','其他规则发现')

def build_grouping(run: ScanRun, finding_ids: set[str] | None = None) -> dict:
 resources={r.id:r for r in [*run.components,*run.ai_assets]}
 licenses={r.id:r for r in run.licenses}; evidence={r.id:r for r in run.evidence}
 obligations={r.id:r for r in run.obligations}; remediations={r.id:r for r in run.remediations}
 groups={}
 for f in sorted(run.findings,key=lambda x:x.id):
  if finding_ids is not None and f.id not in finding_ids: continue
  ctx=_context(run,f,resources,licenses,evidence,obligations)
  gid='G'+hashlib.sha256(canonical(ctx).encode()).hexdigest()[:16]
  if gid not in groups:
   cid,cname=_category(ctx)
   lic=ctx['license_expression']
   license_label='许可待核验' if not lic or lic in ('NOASSERTION','NONE') else lic
   groups[gid]={'id':gid,'category_id':cid,'category_name':cname,
    'title':f"{ctx['scope']} · {license_label} · {ctx['resource_type']}",
    'summary':f"依据{ctx['scope']}中的{ctx['resource_type']}记录归组；{ctx['version_basis']}。{ctx['usage']}。",
    'context':ctx,'finding_ids':[],'resource_ids':[],
    'severity_counts':{level:0 for level in LEVELS},
    'advice':{'kind':'rule','summary':'规则说明：请按逐项证据核对适用许可，当前分组不代表许可核验通过。','steps':[]}}
  group=groups[gid];group['finding_ids'].append(f.id);group['resource_ids'].append(f.resource_id)
  group['severity_counts'][f.severity.value]+=1
 for group in groups.values():
  group['resource_ids']=sorted(set(group['resource_ids']))
  fs=[f for f in run.findings if f.id in set(group['finding_ids'])]
  rs=[remediations.get(f.remediation_id) for f in fs]
  marker=f"【组级AI建议 {group['id']}】"
  if all(r and r.summary.startswith(marker) for r in rs):
   shared={(r.summary,tuple(r.steps)) for r in rs}
   if len(shared)==1:
    r=rs[0];group['advice']={'kind':'group_ai','summary':r.summary[len(marker):],'steps':r.steps}
  elif any(rs):
   group['advice']={'kind':'historical','summary':'历史成员建议并未按本情境组共同生成，请在原始详情核对；当前仅重新组织展示。','steps':[]}
  elif run.provenance.ai_enabled:
   group['advice']={'kind':'unavailable','summary':'本组没有可用的组级AI建议；保留规则说明和原始证据。','steps':[]}
 ordered=sorted(groups.values(),key=lambda g:(min(LEVELS.index(k) for k,v in g['severity_counts'].items() if v),g['category_id'],g['id']))
 return {'version':GROUPING_VERSION,'finding_count':sum(len(g['finding_ids']) for g in ordered),
  'resource_count':len({r for g in ordered for r in g['resource_ids']}),'groups':ordered}
