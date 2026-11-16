import type { P2Binding, P2Result } from '../types/p2Advice';
import { readP2Binding, readP2Index, readP2Result, sameBinding } from './p2Advice';

// Same-origin sessionStorage; retained for this tab's session until explicit acknowledgement.
// Never store upload bytes, descriptions, answers, evidence text or a replayable request body.
export type RecoveryMarker = {
  version: 1; binding: P2Binding; kind: 'results' | 'answers' | 'materials'; key: string;
  parent: string | null; expected: number; state: 'unknown' | 'saved' | 'conflict' | 'rejected';
  saved?: { id: string; revision: number; hash: string }; recordedAt: string;
};
export const recoveryIdentity = (b: Pick<P2Binding, 'scan_id' | 'assessment_id' | 'assessment_version'>) => [b.scan_id, b.assessment_id, b.assessment_version].join(':');
const storageKey = (id: string) => 'og-p2-recovery-v1:' + id;
export function readRecovery(id: string): RecoveryMarker | null {
  const raw = sessionStorage.getItem(storageKey(id));
  if (!raw) return null;
  try {
    const m = JSON.parse(raw);
    if (m.version !== 1 || !m.binding || recoveryIdentity(m.binding) !== id ||
      !['results','answers','materials'].includes(m.kind) || !['unknown','saved','conflict','rejected'].includes(m.state) ||
      typeof m.key !== 'string' || !m.key || !Number.isInteger(m.expected) || m.expected < 0 ||
      !(m.parent === null || typeof m.parent === 'string') || !Number.isFinite(Date.parse(m.recordedAt)) ||
      (m.state === 'saved' && (!m.saved || typeof m.saved.id !== 'string' || !Number.isInteger(m.saved.revision) || !/^[a-f0-9]{64}$/.test(m.saved.hash)))) throw Error();
    return m;
  } catch { throw new Error('本标签页恢复标记损坏；保存状态待确认，请先核对服务器，勿重复提交。'); }
}
export function saveRecovery(m: RecoveryMarker) {
  try { sessionStorage.setItem(storageKey(recoveryIdentity(m.binding)), JSON.stringify(m)); }
  catch { throw new Error('浏览器无法保存最小恢复标记，本次请求未发送。请允许当前站点的会话存储后重试。'); }
}
export function clearRecovery(id: string) { sessionStorage.removeItem(storageKey(id)); }
export async function recoverMarker(m: RecoveryMarker): Promise<{ head: P2Result | null; saved: P2Result | null }> {
  const b = await readP2Binding(m.binding.scan_id, m.binding.assessment_id, m.binding.assessment_version);
  if (!sameBinding(b, m.binding)) throw new Error('恢复标记与当前父绑定不符，不能认领结果或重放。');
  const index = await readP2Index(b);
  const head = index.head_result_id ? await readP2Result(b, index.head_result_id, index.head_revision) : null;
  const saved = m.saved ? await readP2Result(b, m.saved.id, m.saved.revision) : null;
  if (saved && saved.result_sha256 !== m.saved!.hash) throw new Error('已确认结果的摘要不匹配，保存状态待核对。');
  return { head, saved };
}
