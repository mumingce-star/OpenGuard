import { useEffect, useRef, useState } from 'react';
import type { P2Answer, P2AnswerCode, P2Binding, P2Material, P2Result, P2ResultIndex, P2Summary } from '../types/p2Advice';
import { readP2Binding, readP2Index, readP2Result, p2StateLabels } from '../services/p2Advice';
import { answerLabels, createFields, P2WriteAttempt, p2ErrorMessage, p2ReadOnly, p2Selection, prepareAnswer, prepareMaterial, readP2Reference, readP2Summary } from '../services/p2Workflow';
import { P2VersionComparison } from './P2VersionComparison';
import { assessmentReportUrl } from '../services/assessments';
import { ApiError } from '../services/scans';
import { Panel } from './ui';
import { P2ResultView } from './P2AdvicePanel';

// Unresolved attempts survive SPA navigation in this tab only. Never persist uploaded text or formal state.
const attempts = new Map<string, P2WriteAttempt>();
const message = (e: unknown) => e instanceof Error ? e.message : '读取失败，请重试。';
export function p2ReadErrorText(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 404) return '当前固定评估或独立结果未找到；不会改选最新版本。请核对 URL 与服务端对象。';
    if (error.status === 503) return 'P2 读取服务不可用或未启用；Formal Assessment 仍可单独查看。请稍后重试。';
    if (error.status === 409) return '独立结果与父评估版本不一致；不会展示不匹配的建议。';
  }
  return message(error);
}
type Props = { scanId: string; assessmentId: string; assessmentVersion: number; evidenceIds: string[];
  query: URLSearchParams; onSelect: (result: P2Result) => void; onEvidence: (id: string) => void; openResources?: () => void };

export function P2SummaryView({ summary }: { summary: P2Summary }) {
  return <section className="og-p2-summary" aria-label="P2同版摘要">
    <h3>P2 同版摘要 · 非正式报告</h3>
    <p>摘要 {summary.summary_id} · Result第{summary.result_revision}版 · {p2StateLabels[summary.state]}</p>
    <p>只展示后端保存的摘要；不能替代或改写 Formal Assessment / 原报告。</p>
    <details><summary>摘要的资源状态与固定身份</summary>
      <p>Result：{summary.result_id} · SHA-256：{summary.result_sha256}</p>
      <ul>{Object.entries(summary.resource_states).map(([id, state]) => <li key={id}>{id}：{p2StateLabels[state]}</li>)}</ul>
      <p>材料：{summary.material_ids.join('、') || '未提供'}；回答：{summary.answer_ids.join('、') || '未提供'}</p>
    </details>
  </section>;
}

export function P2ReferenceView({ value, onEvidence }: { value: P2Material | P2Answer; onEvidence: (id: string) => void }) {
  return <section className="og-p2-reference" aria-label="P2引用读回">
    {'material_id' in value ? <>
      <h3>材料观察：{value.filename}</h3><p>{value.material_id} · {value.subject.resource_id} · {value.subject.version ?? '未获取'}</p>
      <p>待核验 / 用户提供、未经核验 / 已记录文本观察。不是原始 ScanRun Evidence，也不是许可确认。</p>
      <p>{value.completeness === 'FULL_TEXT_CLAIMED' ? '用户声称为全文，完整性未经核验' : '节选材料，可能缺少条款'}；{value.byte_count} 字节</p>
      <p>原文 SHA-256：{value.source_sha256}</p>
    </> : <>
      <h3>已保存的用户声明</h3><p>{value.answer_id} · Result第{value.revision}版</p>
      <p>{answerLabels[value.answer_code]}；USER_ASSERTED 不等于正式义务已履行或项目合规。</p>
      <p>仅覆盖：{value.subjects.map(s => s.resource_id + '@' + (s.version ?? '未知版本')).join('、')}</p>
    </>}
    <p>Formal影响：无。引用原扫描证据：</p>
    {value.evidence_ids.length ? value.evidence_ids.map(id => <button key={id} onClick={() => onEvidence(id)}>{id}</button>) : <p>没有证据引用，不能据此提升核验状态。</p>}
  </section>;
}

export function P2Workbench(props: Props) {
  const { scanId, assessmentId, assessmentVersion, evidenceIds, onEvidence, onSelect, openResources } = props;
  const identity = [scanId, assessmentId, assessmentVersion].join(':');
  const [binding, setBinding] = useState<P2Binding | null>(null);
  const [index, setIndex] = useState<P2ResultIndex | null>(null);
  const [result, setResult] = useState<P2Result | null>(null);
  const [summary, setSummary] = useState<P2Summary | null>(null);
  const [summaryError, setSummaryError] = useState('');
  const [readError, setReadError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [offset, setOffset] = useState(0);
  const [history, setHistory] = useState<string[]>([]);
  const [writeEnabled, setWriteEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState<P2WriteAttempt | null>(() => attempts.get(identity) ?? null);
  const [writeMessage, setWriteMessage] = useState(() => attempts.has(identity) ? '此页有尚未解决的提交；请先只读核对，勿创建新的请求键。' : '');
  const [recoveredHead, setRecoveredHead] = useState<P2Result | null>(null);
  const [questionId, setQuestionId] = useState('');
  const [answer, setAnswer] = useState<P2AnswerCode | ''>('');
  const [subjects, setSubjects] = useState<string[]>([]);
  const [resourceId, setResourceId] = useState('');
  const [evidence, setEvidence] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [description, setDescription] = useState('');
  const [completeness, setCompleteness] = useState<'FULL_TEXT_CLAIMED' | 'EXCERPT'>('EXCERPT');
  const [reference, setReference] = useState<P2Material | P2Answer | null>(null);
  const [referenceError, setReferenceError] = useState('');
  const referenceController = useRef<AbortController | null>(null);
  const lock = useRef(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; referenceController.current?.abort(); }; }, []);
  const unresolved = !!attempt && attempt.state !== 'saved';
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (unresolved) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [unresolved]);
  const query = props.query.toString();
  useEffect(() => {
    const controller = new AbortController();
    referenceController.current?.abort();
    setLoading(true); setReadError(''); setBinding(null); setIndex(null); setHistory([]); setOffset(0);
    setResult(null); setSummary(null); setSummaryError(''); setReference(null);
    setQuestionId(''); setAnswer(''); setSubjects([]); setResourceId(''); setEvidence([]); setFile(null);
    void (async () => {
      const selection = p2Selection(new URLSearchParams(query), assessmentVersion);
      const b = await readP2Binding(scanId, assessmentId, assessmentVersion, controller.signal);
      const list = await readP2Index(b, 0, controller.signal);
      const selected = selection ? await readP2Result(b, selection.id, selection.revision, controller.signal) :
        list.head_result_id ? await readP2Result(b, list.head_result_id, list.head_revision, controller.signal) : null;
      if (controller.signal.aborted) return;
      setBinding(b); setIndex(list); setHistory(list.result_ids); setOffset(0); setResult(selected); setLoading(false);
      // Pin the first read to its immutable identity; later refresh must not select a newer head.
      if (selected && !selection) { onSelect(selected); return; }
      if (selected) {
        try { const s = await readP2Summary(selected, controller.signal); if (!controller.signal.aborted) setSummary(s); }
        catch (e) { if (!controller.signal.aborted) setSummaryError(message(e)); }
      }
    })().catch(e => { if (!controller.signal.aborted) { setReadError(p2ReadErrorText(e)); setLoading(false); } });
    return () => controller.abort();
  }, [scanId, assessmentId, assessmentVersion, query, reload]);

  async function run(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    try { await action(); } catch (e) { if (alive.current) setWriteMessage(attempts.has(identity) ? p2ErrorMessage(e) : message(e)); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  async function send(a: P2WriteAttempt) {
    attempts.set(identity, a); setAttempt(a);
    try {
      const saved = await a.send(); attempts.delete(identity);
      if (alive.current) { setWriteMessage('独立结果已保存。正式评估未改变；正在按返回的固定身份读回。'); onSelect(saved.result); setReload(n => n + 1); }
    } finally { if (alive.current) setAttempt(a); }
  }
  async function recover() {
    if (!attempt) return;
    await run(async () => {
      const head = await attempt.recover();
      if (alive.current) { setRecoveredHead(head); setAttempt(attempt); setWriteMessage('已只读核对服务器 head：' + (head ? head.result_id + ' / revision ' + head.revision : '暂无结果') + '。这不证明原请求未保存。'); }
    });
  }
  async function select(id: string) {
    if (!binding || unresolved || busy) return;
    await run(async () => { const r = await readP2Result(binding, id); if (alive.current) onSelect(r); });
  }
  const current = !!result && result.result_id === index?.head_result_id && result.revision === index.head_revision;
  const editable = !p2ReadOnly && writeEnabled && !busy && !loading && !readError && !unresolved && current;
  const question = result?.questions.find(q => q.question_id === questionId);
  const resource = result?.resources.find(r => r.subject.resource_id === resourceId);
  const toggle = (values: string[], id: string, checked: boolean) => checked ? [...values, id] : values.filter(x => x !== id);
  return <Panel title="P2 用途建议与补充材料 · 独立结果">
    <div className="og-p2-panel">
      <p>以下为确定性资源候选，不是 Qwen 答疑或 Formal Conclusion。候选算法和父评估规则分别展示。</p>
      {loading && <p role="status">正在读取固定版本…</p>}
      {readError && <p role="alert" className="og-error">{readError} 不会改选 latest 或自动生成。</p>}
      <div className="og-actions">
        <button disabled={busy} onClick={() => setReload(n => n + 1)}>重新读取固定结果</button>
        {index && <button disabled={busy || unresolved || !index.head_result_id} onClick={() => void select(index.head_result_id!)}>显式查看当前 head</button>}
      </div>
      {!!history.length && <details><summary>独立结果历史（Assessment版本不随之改变）</summary>
        <ul>{history.map(id => <li key={id}><button disabled={busy || unresolved} onClick={() => void select(id)}>{id}{id === result?.result_id ? '（当前展示）' : ''}</button></li>)}</ul>
        {index?.has_more && <button disabled={busy} onClick={() => void run(async () => {
          const page = await readP2Index(binding!, offset + 20); if (!alive.current) return;
          setHistory(items => [...new Set([...items, ...page.result_ids])]); setIndex(page); setOffset(n => n + 20);
        })}>加载更多历史</button>}
      </details>}
      {!loading && !readError && !result && <p>没有已保存P2结果；浏览页面不会自动创建。</p>}
      {result && <>
        <P2ResultView result={result} evidenceIds={evidenceIds} onEvidence={onEvidence} openResources={openResources} />
        <p>候选算法：{result.algorithm_version}；父 Formal 规则：{result.binding.rule_version}</p>
        <p>父 Assessment 第{result.binding.assessment_version}版 / 独立 Result 第{result.revision}版</p>
        <P2VersionComparison key={result.result_id} current={result} />
        {summary && <P2SummaryView summary={summary} />}
        {summaryError && <p role="alert">同版摘要未读取成功：{summaryError}。结果仍已保存，不会生成替代报告。</p>}
        <div className="og-actions"><a href={assessmentReportUrl(scanId, assessmentId, 'html')} download>下载此父版本原 Formal HTML</a><a href={assessmentReportUrl(scanId, assessmentId, 'json')} download>下载此父版本原 Formal JSON</a></div>
        <p>原报告是否存在由后端响应确认；这里不把 P2 摘要当作旧v6报告。</p>
        <details><summary>读回材料与用户声明</summary>
          {(['materials','answers'] as const).map(kind => (kind === 'materials' ? result.material_ids : result.answer_ids).map(id =>
            <button key={id} disabled={busy} onClick={() => void run(async () => {
              referenceController.current?.abort();
              const controller = new AbortController(); referenceController.current = controller;
              setReference(null); setReferenceError('');
              try { const ref = await readP2Reference(result, kind, id, controller.signal); if (alive.current && !controller.signal.aborted) setReference(ref); }
              catch (e) { if (alive.current && !controller.signal.aborted) setReferenceError(message(e)); }
              finally { if (referenceController.current === controller) referenceController.current = null; }
            })}>{kind === 'materials' ? '材料' : '回答'}：{id}</button>))}
          {referenceError && <p role="alert">{referenceError}</p>}
          {reference && <P2ReferenceView value={reference} onEvidence={onEvidence} />}
        </details>
      </>}
      {p2ReadOnly && <p role="status">当前前端为只读配置，P2写入已禁用；这不是后端授权状态。</p>}
      <label><input type="checkbox" checked={writeEnabled} disabled={p2ReadOnly || busy || unresolved} onChange={e => setWriteEnabled(e.target.checked)} />我确认在获准数据环境中显式提交P2结果（服务端仍可拒绝写入）</label>
      {result && !current && <p>正在查看旧版；只读。需显式选择服务器head后重新填写，不能覆盖历史。</p>}
      {!result && binding && !readError && <button disabled={p2ReadOnly || !writeEnabled || busy || loading || unresolved} onClick={() => void run(() => send(new P2WriteAttempt('results', createFields(binding, null))))}>明确生成首个独立结果（不创建Assessment）</button>}
      {result && <>
        <form onSubmit={e => { e.preventDefault(); if (!editable || !answer) return; void run(() => send(new P2WriteAttempt('answers', prepareAnswer(result, questionId, answer, subjects)))); }}>
          <fieldset disabled={!editable}><legend>L2 资源范围与履行声明</legend>
            <label>服务端问题<select value={questionId} onChange={e => { setQuestionId(e.target.value); setAnswer(''); setSubjects([]); }}><option value="">请选择，不默认作答</option>{result.questions.map(q => <option key={q.question_id} value={q.question_id}>{q.question_code === 'DELIVERY_SCOPE_FOR_RESOURCES' ? '交付资源范围' : '义务履行声明'} · {q.question_id}</option>)}</select></label>
            {question && <>
              <label>回答<select value={answer} onChange={e => setAnswer(e.target.value as P2AnswerCode)}><option value="">请选择</option>{question.options.map(code => <option key={code} value={code}>{answerLabels[code]}</option>)}</select></label>
              <p>只提交勾选的资源；未勾选不等于排除。用户声明不会替代正式评估。</p>
              <div className="og-p2-subjects">{question.subjects.map(s => <label key={s.resource_id}><input type="checkbox" checked={subjects.includes(s.resource_id)} onChange={e => setSubjects(toggle(subjects, s.resource_id, e.target.checked))} />{s.resource_id} @ {s.version ?? '版本未获取'}</label>)}</div>
            </>}
            <button type="submit" disabled={!answer || !subjects.length}>确认提交所选资源的声明</button>
          </fieldset>
        </form>
        <form onSubmit={e => { e.preventDefault(); if (!editable || !file) return; void run(async () => {
          if (file.size > 65536) throw new Error('材料超过65,536字节。');
          const input = await prepareMaterial(result, resourceId, evidence, file.name, new Uint8Array(await file.arrayBuffer()), description, completeness);
          await send(new P2WriteAttempt('materials', input));
        }); }}>
          <fieldset disabled={!editable}><legend>L2 小文本材料</legend>
            <p>≤65,536原字节，每Assessment≤20份，请求体≤98,304字节；仅UTF-8 LICENSE/LICENCE/NOTICE（可带txt/md/rst）。缺少NOTICE不等于没有NOTICE义务。</p>
            <p>只上传你有权提供的材料。请勿包含密钥、个人信息、商业秘密或无权分享的内容；提交后将由后端持久化，不能通过关闭页面撤回。</p>
            <label>精确资源<select value={resourceId} onChange={e => { setResourceId(e.target.value); setEvidence([]); }}><option value="">请选择资源</option>{result.resources.map(r => <option key={r.subject.resource_id} value={r.subject.resource_id}>{r.subject.resource_id} @ {r.subject.version ?? '版本未知，不能上传'}</option>)}</select></label>
            <div className="og-p2-subjects">{resource?.evidence_ids.map(id => <label key={id}><input type="checkbox" checked={evidence.includes(id)} onChange={e => setEvidence(toggle(evidence, id, e.target.checked))} />原扫描Evidence：{id}</label>)}</div>
            <label>材料文件<input type="file" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
            <label>来源说明<textarea value={description} maxLength={512} onChange={e => setDescription(e.target.value)} /></label>
            <label>完整性声明<select value={completeness} onChange={e => setCompleteness(e.target.value as typeof completeness)}><option value="EXCERPT">节选（可能不完整）</option><option value="FULL_TEXT_CLAIMED">我声称为全文（未经核验）</option></select></label>
            <button type="submit" disabled={!resource?.subject.version || !evidence.length || !file || !description.trim()}>确认提交未核验材料</button>
          </fieldset>
        </form>
      </>}
      <div role="status" aria-live="polite">{busy ? '请求处理中，请勿重复提交。' : writeMessage}</div>
      {unresolved && <section aria-label="保存恢复">
        <p>请求状态：{attempt.state}；键：{attempt.input.idempotency_key}；父Result：{attempt.input.parent_result_id ?? '无'} / expected_revision={attempt.input.expected_revision}。</p>
        <p>原请求仅保留在本标签页内存。关闭或刷新前请先处理；不会自动POST或另换请求键。</p>
        <button disabled={busy} onClick={() => void recover()}>只读核对服务器状态</button>
        {attempt.state === 'unknown' && <button disabled={p2ReadOnly || busy || !attempt.recovered} onClick={() => void run(() => send(attempt))}>手动重放原键与原内容</button>}
        {(attempt.state === 'conflict' || attempt.state === 'rejected') && <button disabled={busy || !attempt.recovered} onClick={() => {
          attempts.delete(identity); setAttempt(null); setWriteMessage('原请求已结束；请确认当前父版本并重新填写，未自动提交。');
          if (recoveredHead) onSelect(recoveredHead); setReload(n => n + 1);
        }}>确认读取结果并返回修改输入</button>}
      </section>}
    </div>
  </Panel>;
}
