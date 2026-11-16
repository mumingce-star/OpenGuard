import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Scan } from '../types/domain';
import {
  listAssessments,
  readExactAssessment,
  getJob,
  getChat,
  sendChat,
  clearChat,
  assessmentReportUrl,
  type Assessment as AssessmentData,
  type Chat,
  type Job,
} from '../services/assessments';
import { Header, Panel } from '../components/ui';
import { DecisionBrief } from '../components/DecisionBrief';
import { AiReview } from '../components/AiReview';
import { P2Workbench } from '../components/P2Workbench';
import { p2WorkbenchEnabled } from '../services/p2';
import { usageDescription, usageTitle } from '../services/usageExperience';

import { readOnlyPreview, aiLoopOnly, assessmentFailure, type FailureStage } from '../services/assessmentFeedback';

function CompactRows<T>({ rows, label, render }: {
  rows: T[];
  label: string;
  render: (row: T, index: number) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      {rows.slice(0, 2).map(render)}
      {rows.length > 2 && (
        <details open={open} onToggle={e => setOpen(e.currentTarget.open)}>
          <summary>
            {open ? '收起' : '展开全部'}{label}（共 {rows.length} 项）
          </summary>
          {open && rows.slice(2).map((row, i) => render(row, i + 2))}
        </details>
      )}
    </div>
  );
}

export function Assessment({
  scan,
  query,
  selectVersion,
  openResources,
  compact = false,
  initialChatOpen = false,
}: {
  scan: Scan;
  query: URLSearchParams;
  selectVersion: (id: string) => void;
  openResources?: () => void;
  compact?: boolean;
  initialChatOpen?: boolean;
}) {
  const readOnly = readOnlyPreview || aiLoopOnly;
  const lastFailure = useRef<ReturnType<typeof assessmentFailure> | null>(null);
  function showFailure(stage: FailureStage, cause: unknown) {
    const failure=assessmentFailure(stage,cause);
    lastFailure.current=failure;setError(failure.message);
  }
  const [items, setItems] = useState<AssessmentData[]>([]);
  const [chat, setChat] = useState<Chat | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const [evidenceId, setEvidenceId] = useState('');
  const [chatOpen, setChatOpen] = useState(initialChatOpen);
  const [copyNotice, setCopyNotice] = useState('');
  const [showAllHistory, setShowAllHistory] = useState(false);

  const evidencePanel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (evidenceId) {
      evidencePanel.current?.scrollIntoView({ block: 'center', behavior: 'auto' });
    }
  }, [evidenceId]);

  const readEpoch = useRef(0);
  const life = useRef(0);
  const lock = useRef(false);
  const chatKey = useRef(crypto.randomUUID());

  // A save event belongs to its submitted usage and explicit view context.
  const jobScan = useRef(scan.id);
  const requested = query.get('assessment_id');
  const selected = requested ? items.find(a => a.id === requested) : items[0];
  const pending = job?.status === 'pending' || chat?.items.some(t => t.status === 'pending');

  // 本次修复：在组件内部定义发送受阻原因，供按钮和提示区共同使用。
  // 这里只解释原有禁用条件，不放宽后端、评估或聊天限制。
  const chatBlockReason = (() => {
    if (readOnly) return '只读预览不能发送或清空问答；已有记录仍可查看。';
    if (busy) {
      return '正在提交或处理请求，请稍候。';
    }
    if (job?.status === 'pending') {
      return '项目评估正在生成，完成后才能继续提问。';
    }
    if (chat?.items.some(t => t.status === 'pending')) {
      return '已有问答正在处理。请等待；长时间无变化时，点击“重新读取评估”检查状态。';
    }
    if (!selected) {
      return '尚未选中可用的项目评估，请先选择或生成评估。';
    }
    if (!chat) {
      return '聊天状态尚未读取成功，请检查后端连接，再点击“重新读取评估”。';
    }
    if (!message.trim()) {
      return '请先输入你的问题。';
    }
    if (chat.items.length >= chat.limits.max_turns) {
      return '本任务聊天记录已达到上限。请先保存需要的内容，再使用页面的确认清空功能。';
    }
    return '';
  })();

  useEffect(() => {
    life.current++;
    setJob(null);setBusy(false);lock.current=false;
    return () => { life.current++; };
  }, [scan.id]);

  useEffect(() => {
    setMessage('');
    setShowAllHistory(false);
    setEvidenceId('');
    setConfirmClear(false);
    chatKey.current = crypto.randomUUID();
  }, [scan.id, selected?.id, selected?.version]);

  useEffect(() => {
    setChatOpen(initialChatOpen);
  }, [initialChatOpen]);

  useEffect(() => {
    if (scan.mode !== 'api') {
      setLoading(false);
      return;
    }
    const epoch = ++readEpoch.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function read() {
      try {
        const result = await listAssessments(scan.id, controller.signal);
        if (requested && !result.items.some(item => item.id === requested)) {
          result.items.push(await readExactAssessment(scan.id, requested, controller.signal));
        }
        if (controller.signal.aborted || readEpoch.current !== epoch) return;
        setItems(result.items);

        let history: Chat | null = null;
        let nextJob = result.pending_job ?? (jobScan.current===scan.id?job:null);
        if (nextJob?.status === 'pending') {
          nextJob = await getJob(scan.id, nextJob.request_id, controller.signal);
        }
        if (controller.signal.aborted || readEpoch.current !== epoch) return;
        setItems(result.items);
        setError('');

        // 读取已保存版本不会创建评估，也不会更改正式用途。
        if (nextJob && (
          nextJob.status !== job?.status || nextJob.request_id !== job?.request_id
        )) {
          jobScan.current=scan.id;setJob(nextJob);
          if (nextJob.status === 'succeeded') {
            // Only the matching local save operation may follow its returned version; see acceptSaved below.
            setRevision(n => n + 1);
          }
        }
        // A validated saved object remains evidence even if this subsequent read fails.
        if (!compact && !p2WorkbenchEnabled) history = await getChat(scan.id, controller.signal);
        if (controller.signal.aborted || readEpoch.current !== epoch) return;
        setChat(history);
        if (nextJob?.status === 'pending' || history?.items.some(t => t.status === 'pending')) {
          timer = setTimeout(read, 2500);
        }
      } catch (e) {
        if (!controller.signal.aborted && readEpoch.current === epoch) {
          showFailure('read',e);
        }
      } finally {
        if (!controller.signal.aborted && readEpoch.current === epoch) {
          setLoading(false);
        }
      }
    }

    void read();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
    // A response belongs to this mounted scan only; App keys this component by scan and mode.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan.id, scan.mode, compact, revision, job?.request_id, requested]);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (readOnly || !selected || !chat || lock.current || !message.trim()) return;
    lock.current = true;
    setBusy(true);
    setError('');
    const token = life.current;
    try {
      await sendChat(scan.id, {
        assessment_id: selected.id,
        request_id: chatKey.current,
        message: message.trim(),
        generation: chat.generation,
      });
      if (life.current !== token) return;
      setMessage('');
      chatKey.current = crypto.randomUUID();
      setRevision(n => n + 1);
    } catch (e) {
      if (life.current === token) showFailure('chat-submit',e);
    } finally {
      if (life.current === token) {
        lock.current = false;
        setBusy(false);
      }
    }
  }

  async function clear() {
    if (readOnly || !chat || lock.current) return;
    lock.current = true;
    setBusy(true);
    const token = life.current;
    try {
      ++readEpoch.current;
      await clearChat(scan.id, chat.generation);
      if (life.current !== token) return;
      setChat(null);
      setConfirmClear(false);
      chatKey.current = crypto.randomUUID();
      setRevision(n => n + 1);
    } catch (e) {
      if (life.current === token) showFailure('chat-clear',e);
    } finally {
      if (life.current === token) {
        lock.current = false;
        setBusy(false);
        setRevision(n => n + 1);
      }
    }
  }

  async function copyAnswer(answer: string) {
    try {
      await navigator.clipboard.writeText(answer);
      setCopyNotice('已复制答复');
    } catch {
      setCopyNotice('复制未成功，请选中文字手动复制。');
    }
  }

  const references = (ids: string[]) => (
    <CompactRows
      rows={ids}
      label="证据引用"
      render={(id, index) => (
        <button
          className="og-evidence-ref"
          key={id}
          type="button"
          title="查看已引用证据"
          aria-label={'查看本任务证据'}
          onClick={() => setEvidenceId(id)}
        >
          {scan.evidence.some(e => e.id === id) ? '查看证据' : '证据待核对'} {index + 1}
        </button>
      )}
    />
  );

  if (scan.mode !== 'api') {
    return (
      <Panel title="项目整体评估">
        <p>演示快照不生成真实评估或本地模型答疑。请通过真实接口完成扫描。</p>
      </Panel>
    );
  }

  const evidence = scan.evidence.find(e => e.id === evidenceId);

  return (
    <section className={"og-assessment compact-result"+(p2WorkbenchEnabled?" p2-assessment-view":"")}>
      <Header
        title={p2WorkbenchEnabled ? scan.project+' · 项目评估' : compact ? '项目评估摘要' : '项目整体评估'}
        description={selected?.usage ? "本次用途："+usageTitle(selected.usage)+" · 第 "+selected.version+" 版" : selected ? "该历史评估未记录用途" : "读取本次已保存评估的用途与结果"}
        action={selected?.usage&&<details key={selected.id+selected.version} className="assessment-usage-details"><summary>查看完整用途</summary><p>{usageDescription(selected.usage)}</p></details>}
      />
      {readOnly && <p className="og-use-draft" role="note">{readOnlyPreview ? '只读预览：可查看结果和依据，不能保存或重新评估。' : 'TEST_ONLY隔离工作台：仅可保存本页AI问题回答及尝试官方补证；用途评估、问答和其他业务写入关闭。'}</p>}
      {loading && <p role="status">正在读取已保存评估…</p>}
      {error && <p className="og-error" role="alert">{error}</p>}



      {requested && !selected && !loading && (
        <p className="og-error">当前扫描中未找到所选评估版本，不会替换为其他任务的结论。</p>
      )}

      <div className={compact || p2WorkbenchEnabled ? '' : 'og-assessment-layout' + (chatOpen ? '' : ' chat-collapsed')}>
        <div className="og-assessment-main">
          {selected ? (
            <>
              <>{p2WorkbenchEnabled ? <P2Workbench key={"p2-"+selected.id+selected.version} assessment={selected} scan={scan} readOnly={readOnly} /> : <AiReview key={"ai-"+selected.id} assessment={selected} readOnly={readOnlyPreview} evidence={scan.evidence} />}</>
          <details key={"records-"+selected.id+selected.version} className="assessment-full-records" onToggle={e=>{const d=e.currentTarget;if(!d.open&&d.contains(document.activeElement))d.querySelector('summary')?.focus({preventScroll:true});}}><summary>正式评估与材料记录 · 历史版本与下载</summary>
          {!p2WorkbenchEnabled&&selected.usage&&<DecisionBrief key={selected.id} assessment={selected} compact={compact} readOnly={readOnly} usageReadOnly />}
              <section className="og-assessment-detail" aria-label="历史评估">
                <h3>已保存的评估</h3>
      <div className="og-actions">
        <button disabled={busy} onClick={() => setRevision(n => n + 1)}>
          重新读取评估
        </button>
        {items.length > 0 && (
          <label>
            评估版本
            <select
              aria-label="评估版本"
              value={requested ?? selected?.id ?? ''}
              disabled={busy}
              onChange={e => selectVersion(e.target.value)}
            >
              {requested && !selected && <option value={requested}>所选版本不存在</option>}
              {items.map(a => (
                <option key={a.id} value={a.id}>
                  第 {a.version} 版 · {new Date(a.generated_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
              <p>本次固定评估：第 {selected.version} 版 · {selected.usage?usageTitle(selected.usage):'未记录用途'} · {new Date(selected.generated_at).toLocaleString()}</p>
              <div className="og-actions">
                <a download href={assessmentReportUrl(scan.id, selected.id, 'html')}>下载本版评估 HTML</a>
                <a download href={assessmentReportUrl(scan.id, selected.id, 'json')}>下载本版评估 JSON</a>
              </div>
              </section>
              </details>
            </>
          ) : !loading && <section className="og-current-use og-use-empty"><h2>尚无可读取的已保存评估</h2><p>扫描前确认的用途由原初始评估流程采用；本页不会补发评估，也不会用草稿冒充保存结果。</p><button type="button" onClick={()=>setRevision(n=>n+1)}>重新读取已保存结果</button></section>}



        </div>

        {!compact && !p2WorkbenchEnabled && (
          <aside className="og-assessment-chat">
            <button aria-expanded={chatOpen} onClick={() => setChatOpen(v => !v)}>
              {chatOpen ? '收起项目答疑' : '展开项目答疑'}
            </button>
            {chatOpen && (
              <Panel title="本地 Qwen3 项目答疑">
                <p>只解释当前扫描和所选评估；聊天不会修改正式用途、结论或重新扫描。</p>
                {chat && (
                  <p>
                    已保存 {chat.items.length} / {chat.limits.max_turns} 轮；每条最多 {chat.limits.max_message_chars} 字符。历史跨刷新保留，切版本仍显示各条所属版本。
                  </p>
                )}
                <label>
                  <input
                    type="checkbox"
                    checked={showAllHistory}
                    onChange={e => setShowAllHistory(e.target.checked)}
                  />
                  查看其他评估版本的历史问答（旧答复不代表本版结论）
                </label>

                <div className="og-chat-history">
                  {chat?.items
                    .filter(t => showAllHistory || t.assessment_id === selected?.id)
                    .map(t => (
                      <article key={t.request_id} className="og-chat-turn">
                        <small>
                          评估 {items.find(a => a.id === t.assessment_id)?.version ?? t.assessment_id} · {new Date(t.created_at).toLocaleString()}
                        </small>
                        <p><strong>你：</strong>{t.question}</p>
                        <p>
                          <strong>Qwen3 辅助答复：</strong>
                          {t.status === 'pending'
                            ? '正在生成…'
                            : t.status === 'failed'
                              ? '未能生成回答：' + (t.error ?? '请稍后重试')
                              : t.answer ?? '未返回有效回答'}
                        </p>
                        {references(t.evidence_ids)}
                        {t.status === 'succeeded' && t.answer && (
                          <button onClick={() => copyAnswer(t.answer!)}>复制答复</button>
                        )}
                        {t.status === 'failed' && (
                          <button
                            disabled={busy || !!pending || t.assessment_id !== selected?.id}
                            onClick={() => {
                              chatKey.current = crypto.randomUUID();
                              setMessage(t.question);
                            }}
                          >
                            重新填写此问题
                          </button>
                        )}
                      </article>
                    ))}
                </div>

                <p role="status">{copyNotice}</p>
                <div className="og-actions" aria-label="建议问题">
                  {['当前用途最需要核对哪些证据？', '哪些条件尚未满足？', '我应该先完成哪三项核验？'].map(question => (
                    <button
                      key={question}
                      disabled={busy || !!pending || !selected}
                      onClick={() => {
                        setMessage(question);
                        chatKey.current = crypto.randomUUID();
                      }}
                    >
                      {question}
                    </button>
                  ))}
                </div>

                <form onSubmit={ask}>
                  <label className="og-field">
                    向当前评估提问
                    <textarea
                      value={message}
                      maxLength={chat?.limits.max_message_chars ?? 2000}
                      disabled={busy || !!pending || !selected || !chat}
                      onChange={e => {
                        setMessage(e.target.value);
                        chatKey.current = crypto.randomUUID();
                      }}
                      placeholder="例如：这个项目用于对外在线服务，还需要核对哪些证据？"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={chatBlockReason !== ''}
                    aria-describedby="og-chat-send-help"
                  >
                    发送给本地 Qwen3
                  </button>
                  <p id="og-chat-send-help" role="status">
                    {chatBlockReason || '可以发送。回答完成前请勿重复提交。'}
                  </p>
                  {error && <p className="og-error" role="alert">{error}</p>}
                </form>

                {confirmClear ? (
                  <div className="og-actions">
                    <span>确认清空本任务全部问答？所有评估版本与报告会保留。</span>
                    <button disabled={readOnly || busy} onClick={clear}>确认清空问答</button>
                    <button onClick={() => setConfirmClear(false)}>取消</button>
                  </div>
                ) : (
                  <button
                    disabled={readOnly || busy || !chat || !chat.items.length}
                    onClick={() => {if(!readOnly)setConfirmClear(true);}}
                  >
                    清空本任务问答
                  </button>
                )}
              </Panel>
            )}
          </aside>
        )}
      </div>

      {evidenceId && (
        <div ref={evidencePanel} tabIndex={-1}>
          <Panel title="本任务证据原文">
            <button onClick={() => setEvidenceId('')}>关闭证据</button>
            <p>{evidenceId}</p>
            {evidence ? (
              <>
                <p>{evidence.path ?? evidence.url ?? evidence.label}</p>
                <pre>{evidence.text ?? '未提供原文，请核对扫描证据。'}</pre>
              </>
            ) : <p>本扫描未提供对应证据，不能据此确认授权。</p>}
          </Panel>
        </div>
      )}
    </section>
  );
}
