import type { Scan } from '../types/domain';
import { sameBinding, type Binding, type Result } from './p2';
import type { PreliminaryAdvice } from './preliminaryAdvice';

// Editorial exhibition copy for this exact saved result. This is not a model response,
// an inference cache or a fallback when an API fails. Other identities receive no draft.
export const exhibitionBinding: Binding = Object.freeze({
 scan_id:'scn_c93dba2a-e272-4a8a-90d3-e3244aa99901',
 assessment_id:'asm_8cc7a59a-36c9-5df2-b8f3-45ba171f8799',assessment_version:1,registry_revision:13,
 project_revision:'0d3b7bb5b6e8a59fd450ae2dca65870009cfcd8b',
 facts_hash:'bc7514c3ea2738e59cb3dc2559e04d4f75c2fabe523b6f2c99498b15ccce9ec6',
 usage_hash:'da62ee784bef22e0a10a98135229bf82c211adba27ddcdef11f54bac7ab061ae',
 rule_version:'assessment-1.0-facts2:2026.09.2:103461f4d3a1d09482b6deeb0cf76b8f689243a0935ce8b3d604c908edb782c3',
 assessment_sha256:'f87ec6928e5cdccf44e196ec24c89dff25548bc798cef9205588c04ad53c4a50',
});
export const exhibitionIdentity = Object.freeze({
 result_id:'p2res_fd12a726d5ccb7b548f866c601584e97b2f79ceb2318029b1ad3e1e6913139d1',
 result_sha256:'85ae01baf4a52daa4132195f657a935e5d5db63734ec18cc26eed5d5c3747aea',
 recommendation_id:'p2pre_b001365ff0a71afc5e51e54d1df2b48cab79543d2740d0d665951d52b77d96a5',
 source_profile_sha256:'ea025bc1f1868c6ddd0fae01281dbd386a7e24f0968c694cd3cd7e10d0eeebb1',
 resource_id:'cmp_46dfbf17-96fb-5180-b199-63cf8661ec6b',
 material_id:'p2mat_69b701b60aded2f0663a893a376ed6981e74877beda181b6c08c29928a21bd98',
 material_sha256:'48da2f39e100d4085767e94966b43f4fa95ff6a0698fba57ed460914e35f94a0',
});
export const assessmentDraft = Object.freeze({
 id:'openguard-exhibition-assessment/http-server-r3-v1',
 provenance:'EDITORIAL_PREGENERATED' as const,
 label:'预生成评估展示稿', modelNotice:'本次未调用 Qwen3',
 title:'按实际交付范围推进，先完成关键材料与声明核对',
 lead:'项目已形成可追溯的资源与证据清单。当前适合先明确最终交付内容，再分批完成许可核对；已取得条款支持的资源可按列明条件纳入方案，尚未覆盖的依赖继续补证。',
 uses:[
  {title:'商业使用',verdict:'已列明资源有条件适用',text:'chalk 4.1.2 的完整 MIT 文本支持商业集成方案，条件是保留版权与许可声明，并确认实际采用版本。该结论不推广到其他依赖。'},
  {title:'向他人分发 / 交付',verdict:'先锁定清单，再核对声明',text:'chalk 已纳入本次声明的交付范围。建议随交付物保留其完整声明；其他依赖和工作流引用先确认是否随产品交付，再补对应版本材料。'},
 ],
 actions:[
  {title:'明确交付范围',text:'区分最终产物、开发依赖和工作流引用，回答两个项目级问题。'},
  {title:'补齐精确版本材料',text:'优先处理实际交付资源，逐项关联完整 LICENSE / NOTICE。'},
  {title:'复核声明并导出',text:'核对适用范围与履行情况，保留新旧版本及来源，导出可追溯报告。'},
 ],
 riskNote:'当前扫描记录为 57 条许可依据待核验提示，严重、高、中、低风险均为 0；这只描述已保存的规则发现，不代表全项目已获许可。',
 boundary:'本稿基于固定 TEST_ONLY 扫描、用途和已保存材料整理。1 个资源有条件初评、56 个尚未覆盖；人工适用性和履行签认仍待完成，正式评估不变。',
});

export function matchingAssessmentDraft(scan:Scan,result:Result,advice:PreliminaryAdvice|null){
 const f=exhibitionIdentity;
 if(!advice||scan.mode!=='api'||scan.id!==exhibitionBinding.scan_id||scan.status!=='completed'||scan.resources.length!==57||scan.evidence.length!==106||scan.risks.length!==57||!scan.risks.every(r=>r.severity==='info'&&r.ruleId==='license-evidence-gate'))return null;
 if(result.result_id!==f.result_id||result.result_sha256!==f.result_sha256||result.revision!==3||!sameBinding(result.binding,exhibitionBinding)||result.data_scope!=='TEST_ONLY'||result.model_calls!==0||result.formal_effect!=='none'||result.resources.length!==57)return null;
 if(Object.keys(result.usage).length!==7||Object.entries(result.usage).some(([key,value])=>value!==(key==='commercial'||key==='distributed'?true:null)))return null;
 if(advice.result_id!==f.result_id||advice.result_sha256!==f.result_sha256||!sameBinding(advice.binding,exhibitionBinding)||advice.recommendation_id!==f.recommendation_id||advice.source_profile_sha256!==f.source_profile_sha256||advice.source_status!=='CHECKED'||advice.data_scope!=='TEST_ONLY'||advice.formal_effect!=='none'||advice.model_calls!==0||advice.supported_resource_ids.length!==1||advice.supported_resource_ids[0]!==f.resource_id||advice.uncovered_resource_ids.length!==56)return null;
 const saved=result.resources.find(r=>r.subject.resource_id===f.resource_id);
 if(!saved||saved.subject.version!=='4.1.2'||saved.user_assertions.DELIVERY_SCOPE_FOR_RESOURCES!=='YES_INCLUDE'||!saved.material_ids.includes(f.material_id))return null;
 for(const use of ['commercial','distributed']){
  const a=advice.advice.find(d=>d.usage===use),r=a?.resources[0];
  if(a?.state!=='CONDITIONAL_TEXT_BASIS'||a.resources.length!==1||!r||r.subject.resource_id!==f.resource_id||r.subject.version!=='4.1.2'||!r.material_ids.includes(f.material_id)||r.material_sha256[r.material_ids.indexOf(f.material_id)]!==f.material_sha256)return null;
 }
 return assessmentDraft;
}
