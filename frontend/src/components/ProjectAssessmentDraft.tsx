import type { assessmentDraft } from '../services/projectAssessmentDraft';
import './ProjectAssessmentDraft.css';

export function ProjectAssessmentDraft({draft,onScope,onMaterial}:{draft:typeof assessmentDraft;onScope:()=>void;onMaterial:()=>void}){
 return <article className="project-assessment-draft" aria-label="预生成项目综合评估">
  <header><span className="project-draft-source">{draft.label}</span><span>{draft.modelNotice}</span></header>
  <h2>{draft.title}</h2>
  <p className="project-draft-lead">{draft.lead}</p>
  <div className="project-draft-uses">{draft.uses.map(item=><section key={item.title}><h3>{item.title}</h3><strong>{item.verdict}</strong><p>{item.text}</p></section>)}</div>
  <div className="project-draft-next"><h3>建议按这个顺序推进</h3><ol>{draft.actions.map(item=><li key={item.title}><strong>{item.title}</strong><span>{item.text}</span></li>)}</ol></div>
  <div className="project-draft-actions"><button className="p2-primary" onClick={onScope}>确认交付范围</button><button onClick={onMaterial}>补充材料依据</button><span>依据：57 个资源 · 106 条证据 · 2 项已选用途</span></div>
  <details><summary>本稿依据与展示边界</summary><p>{draft.riskNote}</p><p>{draft.boundary}</p><p>生成来源：基于保存结果预先整理的展示文案，不是 Qwen3 历史输出或本次实时生成。正文只用于当前固定结果 r3，切换对象或材料身份不一致时不展示。</p><code>{draft.id}</code></details>
 </article>;
}
