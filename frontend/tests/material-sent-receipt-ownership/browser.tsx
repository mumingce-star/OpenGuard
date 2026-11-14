import { act, Profiler } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { P2Workbench } from '../../../p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend/src/components/P2Workbench';
import { canReplayWrite, pendingWriteFor, type PendingWrite } from '../../../p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend/src/services/p2';
import { FILE_BYTES, SOURCE_DESCRIPTION, sentReceiptFixture, type Fixture, type View } from './fixture';
import { check, closedTransport, deferred, type RequestRow } from './transport';

/** SOURCE PREPARATION ONLY / NOT_RUN. Real Workbench, MaterialForm, materialBytes,
 * write and submitWrite remain intact. Only bottom fetch and synthetic File wait
 * are controlled. This is not ASGI, browser receiver or business-write evidence. */
type Event = { name: string; utc: string; requestCutoff: number };
type Outcome = 'passed' | 'failed' | 'NOT_ESTABLISHED';
type UIState = { resultId: string | null; fixedUrl: string; success: string[]; pendingVisible: boolean; error: string[] };
type Case = { name: string; status: Outcome; error: string | null; events: Event[]; beforeRelease: UIState | null; afterRelease: UIState | null; ledger: RequestRow[]; nonGet: RequestRow[]; unknown: RequestRow[]; originalRequest: { serialized: string; idempotencyKey: unknown; expectedRevision: unknown; parentResultId: unknown; requestId: null; requestIdReason: string } | null; terminal: string | null };
const report = { classification: 'SYNTHETIC_TEST_ONLY_REAL_COMPONENT_SERVICE_CLOSED_BOTTOM_TRANSPORT', status: 'NOT_RUN' as 'NOT_RUN' | 'running' | Outcome,
  startedAt: null as string | null, finishedAt: null as string | null, testSourcePreparedOnly: true, junit: null,
  realBackendRequests: null, browserReceiverAcceptance: null, requestLedgerSelfcheck: null as unknown, cases: [] as Case[] };
declare global { interface Window { __P2_MATERIAL_SENT_RECEIPT_SCOPE__: typeof report; runP2MaterialSentReceiptScope: () => Promise<typeof report> } }
window.__P2_MATERIAL_SENT_RECEIPT_SCOPE__ = report;
class NotEstablished extends Error {}
class IndependentLedgerViolation extends Error {}
function display() { document.querySelector('#results')!.textContent = JSON.stringify(report, null, 2); }
function bounded<T>(p: Promise<T>, label: string): Promise<T> {
  return new Promise((resolve, reject) => { const timer = window.setTimeout(() => reject(new NotEstablished('NOT_SETTLED: ' + label)), 5000);
    p.then(value => { clearTimeout(timer); resolve(value); }, error => { clearTimeout(timer); reject(error); }); });
}
function taskBoundary() { return new Promise<void>(resolve => { const c = new MessageChannel(); c.port1.onmessage = () => { c.port1.close(); c.port2.close(); resolve(); }; c.port2.postMessage(null); }); }
async function until(predicate: () => boolean, label: string) { let stop = false; try { await bounded((async () => { while (!stop && !predicate()) await act(async () => { await taskBoundary(); }); })(), label); } finally { stop = true; } }
function gatedFile() {
  const state = { calls: 0, entered: false, released: false, resolved: false }, entered = deferred<void>(), release = deferred<void>();
  const file = new File([FILE_BYTES], 'LICENSE', { type: 'text/plain', lastModified: 0 });
  Object.defineProperty(file, 'arrayBuffer', { configurable: false, value: async () => { state.calls++; check(state.calls === 1, 'File reread'); state.entered = true; entered.resolve(); await release.promise; state.resolved = true; return FILE_BYTES.slice().buffer; } });
  return { file, state, entered: entered.promise, release() { check(!state.released, 'File released twice'); state.released = true; release.resolve(); } };
}
type Gate = ReturnType<typeof gatedFile>;
type Transport = ReturnType<typeof closedTransport>;
function bundleFor(f: Fixture, view: View) { return view === 'B' ? f.alternate : view === 'A_OTHER_BINDING' ? f.bindingChanged : f.base; }
function fixedResultFor(f: Fixture, view: View) { return view === 'A_OTHER_RESULT' ? f.concurrent : bundleFor(f, view).result; }
function mount(f: Fixture, t: Transport) {
  const host = document.createElement('div'); document.querySelector('#mounts')!.append(host);
  const root = createRoot(host); let disposed = false, view: View = 'A'; const phases: string[] = [];
  function render(next: View, readOnly = false) {
    check(!disposed, 'Render after unmount'); view = next; t.setView(next); const bundle = bundleFor(f, next), result = fixedResultFor(f, next);
    window.history.replaceState(null, '', `/app/scans/${bundle.scan.id}/assessment?mode=api&assessment_id=${bundle.assessment.id}&assessment_version=${bundle.assessment.version}&p2_result=${result.result_id}`);
    flushSync(() => root.render(<Profiler id="sent-receipt-same-root" onRender={(_id, phase) => { phases.push(phase); }}><div data-view={next} data-readonly={String(readOnly)}>
      <P2Workbench scan={bundle.scan} assessment={bundle.assessment} readOnly={readOnly}/>
    </div></Profiler>));
  }
  render('A'); const originalNode = host.querySelector('.p2-workbench'); check(originalNode, 'Real Workbench absent');
  function button(text: string) { return Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(b => b.textContent === text) ?? null; }
  function fieldset() { return host.querySelector<HTMLFieldSetElement>('.p2-material-form > fieldset'); }
  return { host, phases, render, button, fieldset,
    sameInstance() { check(host.querySelector('.p2-workbench') === originalNode && phases.filter(p => p === 'mount').length === 1, 'Workbench was remounted'); },
    state(): UIState { return { resultId: host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultId ?? null,
      fixedUrl: window.location.href, success: Array.from(host.querySelectorAll('.p2-success')).map(x => x.textContent ?? ''),
      pendingVisible: Array.from(host.querySelectorAll('.p2-pending strong')).some(x => x.textContent === '保留待确认的原请求'),
      error: Array.from(host.querySelectorAll('.p2-workbench > div.p2-message.p2-error[role="alert"]')).map(x => x.textContent ?? '') }; },
    async ready(id = fixedResultFor(f, view).result_id) { await until(() => host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultId === id && !Array.from(host.querySelectorAll('[role="status"]')).some(x => x.textContent?.includes('正在读取当前对象')), 'fixed Result loaded through actual read effect'); },
    async prepare(gate: Gate) {
      const summary = host.querySelector<HTMLElement>('details.p2-optional > summary'); check(summary, 'Material disclosure absent');
      if (!summary.parentElement?.hasAttribute('open')) flushSync(() => summary.click());
      await until(() => !!button('补充 LICENSE / NOTICE'), 'Material tab'); flushSync(() => button('补充 LICENSE / NOTICE')!.click());
      await until(() => !!host.querySelector('.p2-material-form'), 'real MaterialForm mounted');
      const form = host.querySelector<HTMLFormElement>('.p2-material-form')!, select = form.querySelector<HTMLSelectElement>('select')!;
      check(!form.querySelector<HTMLFieldSetElement>('fieldset')!.disabled, 'Original form not editable');
      flushSync(() => { select.value = f.target.subject.resource_id; select.dispatchEvent(new Event('change', { bubbles: true })); });
      await until(() => !!form.querySelector('input[type="checkbox"]'), 'actual Evidence choices');
      const evidence = form.querySelector<HTMLInputElement>('input[type="checkbox"]')!; flushSync(() => evidence.click()); check(evidence.checked, 'Evidence not selected');
      const input = form.querySelector<HTMLInputElement>('input[type="file"]')!;
      Object.defineProperty(input, 'files', { configurable: true, value: { 0: gate.file, length: 1, item: (i: number) => i === 0 ? gate.file : null } });
      flushSync(() => input.dispatchEvent(new Event('change', { bubbles: true })));
      const description = form.querySelector<HTMLInputElement>('input[maxlength="512"]')!, setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      flushSync(() => { setter.call(description, SOURCE_DESCRIPTION); description.dispatchEvent(new Event('input', { bubbles: true })); });
      check(select.value === f.target.subject.resource_id && description.value === SOURCE_DESCRIPTION && input.files?.[0] === gate.file && !form.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled, 'Actual form setup failed');
      return form;
    },
    async start(form: HTMLFormElement, gate: Gate) { flushSync(() => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))); await bounded(gate.entered, 'real File.arrayBuffer entered');
      await act(async () => { await taskBoundary(); }); check(gate.state.entered && !gate.state.released && form.getAttribute('aria-busy') === 'true', 'File read was not genuinely suspended'); },
    async sentFinallyObserved(before: UIState) {
      // A faulty accepted A receipt could remove B's MaterialForm. Stop on an
      // observable ownership fault as well as normal finally; do not hide a
      // real contamination behind a missing-fieldset watchdog.
      await until(() => {
        const current = { resultId: host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultId ?? null,
          url: window.location.href, success: Array.from(host.querySelectorAll('.p2-success')).map(x => x.textContent ?? ''),
          error: Array.from(host.querySelectorAll('.p2-workbench > div.p2-message.p2-error[role="alert"]')).map(x => x.textContent ?? '') };
        return (!!fieldset() && fieldset()!.disabled === false) || current.resultId !== before.resultId || current.url !== before.fixedUrl
          || JSON.stringify(current.success) !== JSON.stringify(before.success) || JSON.stringify(current.error) !== JSON.stringify(before.error);
      }, 'real submit finally or actual receipt ownership violation');
    },
    dispose() { if (!disposed) { disposed = true; flushSync(() => root.unmount()); host.remove(); } },
  };
}
type UI = ReturnType<typeof mount>;
type Context = { f: Fixture; t: Transport; ui: UI; gate: Gate; form: HTMLFormElement; p: PendingWrite | null; mark: (s: string) => void; captureBefore: () => void; captureAfter: () => void; terminal: (s: string) => void };
function assertOriginal(p: PendingWrite, serialized: string, key: unknown, f: Fixture) {
  check(p.serialized === serialized && JSON.stringify(p.body) === serialized && p.body.idempotency_key === key && p.body.expected_revision === 1 && p.body.parent_result_id === f.base.result.result_id, 'Original PendingWrite/CAS/idempotency identity changed');
}
function assertBUnchanged(before: UIState, after: UIState, f: Fixture, t: Transport) {
  check(after.resultId === f.alternate.result.result_id && after.fixedUrl === before.fixedUrl && JSON.stringify(after.success) === JSON.stringify(before.success) && after.pendingVisible === before.pendingVisible && JSON.stringify(after.error) === JSON.stringify(before.error), 'A receipt contaminated B Result/URL/success/pending/error');
  check(pendingWriteFor(f.alternate.assessment) === null && t.materialPosts().length === 1 && t.nonGet.length === 1, 'B acquired A pending or automatic replay occurred');
}
async function scenario(name: string, action: (c: Context) => Promise<void>, options: { responseStatus?: 201 | 409; send?: boolean } = {}) {
  const f = sentReceiptFixture(name), t = closedTransport(f, options.responseStatus ?? 201), gate = gatedFile(), prior = window.location.href;
  const events: Event[] = []; let ui: UI | undefined, form: HTMLFormElement | undefined, p: PendingWrite | null = null, error: unknown;
  let beforeRelease: UIState | null = null, afterRelease: UIState | null = null, terminal: string | null = null;
  let originalRequest: Case['originalRequest'] = null;
  window.fetch = t.fetch; // Stay closed through teardown and between scenarios.
  try {
    ui = mount(f, t); await ui.ready(); form = await ui.prepare(gate); await ui.start(form, gate);
    if (options.send !== false) {
      gate.release(); await bounded(t.postEntered, 'actual original Material POST in independent ledger');
      p = pendingWriteFor(f.base.assessment); check(p, 'Actual sending attempt absent');
      check(t.materialPosts().length === 1 && t.materialPosts()[0].status === null && t.materialPosts()[0].body === p.serialized, 'Response not genuinely held after actual dispatch');
      originalRequest = { serialized: p.serialized, idempotencyKey: p.body.idempotency_key, expectedRevision: p.body.expected_revision, parentResultId: p.body.parent_result_id, requestId: null, requestIdReason: 'NOT_A_PUBLIC_FIELD: Material PendingWrite has no separate requestId; keep the same PendingWrite reference, serialized body and idempotency_key.' };
    }
    const mark = (s: string) => events.push({ name: s, utc: new Date().toISOString(), requestCutoff: t.mark() });
    await action({ f, t, ui, gate, form, p, mark, captureBefore: () => { beforeRelease = ui!.state(); }, captureAfter: () => { afterRelease = ui!.state(); }, terminal: s => { terminal = s; } });
    check(terminal, 'No actual terminal UI/form event established');
    check(t.unknown.length === 0, 'Independent unknown ledger nonempty despite product catch');
    if (p) assertOriginal(p, originalRequest!.serialized, originalRequest!.idempotencyKey, f);
  } catch (e) { error = e; }
  finally {
    ui?.dispose(); if (!gate.state.released) gate.release();
    try { await bounded(t.drain(), 'closed transport drain'); await act(async () => { await taskBoundary(); });
      if (t.unknown.length) throw new IndependentLedgerViolation('Unknown actual request survived product catch');
      const expected = options.send === false ? 0 : 1;
      if (t.materialPosts().length > expected || t.nonGet.length > expected) throw new IndependentLedgerViolation('Extra Material/nonGET request, including implicit replay');
      if (t.materialPosts().length !== expected || t.nonGet.length !== expected) throw new NotEstablished('Expected actual dispatch not established');
    } catch (e) { if (!error || (error instanceof NotEstablished && e instanceof IndependentLedgerViolation)) error = e; }
    report.cases.push({ name, status: error instanceof NotEstablished ? 'NOT_ESTABLISHED' : error ? 'failed' : 'passed', error: error instanceof Error ? error.message : error ? String(error) : null,
      events, beforeRelease, afterRelease, ledger: [...t.ledger], nonGet: [...t.nonGet], unknown: [...t.unknown], originalRequest, terminal });
    window.history.replaceState(null, '', prior); display();
  }
  // A watchdog/setup failure aborts the suite and is not a product red/green.
  if (error) { report.status = error instanceof NotEstablished ? 'NOT_ESTABLISHED' : 'failed'; report.finishedAt = new Date().toISOString(); throw error; }
}

export async function runP2MaterialSentReceiptScope() {
  check(report.status === 'NOT_RUN', 'Once per fresh isolated page'); report.status = 'running'; report.startedAt = new Date().toISOString();
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const self = closedTransport(sentReceiptFixture('ledger_selfcheck')); let refused = 0;
  for (const [path, method] of [['/api/v1/unknown-sent-receipt', 'GET'], ['/api/v1/unknown-sent-receipt', 'DELETE']] as const) { try { await self.fetch(path, { method }); } catch { refused++; } }
  check(refused === 2 && self.unknown.length === 2 && self.nonGet.length === 1 && self.ledger.length === 2, 'Independent refusal ledger selfcheck failed');
  report.requestLedgerSelfcheck = { classification: 'NOT_PRODUCT_REQUESTS', ledger: self.ledger };

  await scenario('sent_201_unchanged_original_scope_positive_control', async ({ f, t, ui, p, mark, captureBefore, captureAfter, terminal }) => {
    check(p, 'Original pending absent'); mark('original-scope-unchanged-before201'); captureBefore();
    t.releaseReceipt(); await bounded(t.responseConsumed, 'valid unchanged-scope A201 consumed'); await ui.ready(f.saved.result_id);
    await until(() => ui.state().success.some(s => s.includes('已保存独立结果第 2 版')), 'unchanged-scope valid receipt UI'); captureAfter();
    const q = new URL(ui.state().fixedUrl).searchParams;
    check(q.get('assessment_id') === f.base.assessment.id && q.get('p2_result') === f.saved.result_id && !ui.state().pendingVisible && pendingWriteFor(f.base.assessment) === null && t.materialPosts().length === 1 && t.nonGet.length === 1, 'Unchanged-scope receipt lost identity or repeated POST');
    terminal('UNCHANGED_A_VALID_RECEIPT_ACCEPTED');
  });

  await scenario('sent_201_A_to_B_preserves_B_UI', async ({ f, t, ui, p, mark, captureBefore, captureAfter, terminal }) => {
    check(p, 'Original pending absent'); ui.render('B'); await ui.ready(); ui.sameInstance();
    check(ui.fieldset()?.disabled === true && !ui.state().pendingVisible, 'B should remain busy for sent A while own pending absent');
    mark('B-loaded-before-A201-release'); captureBefore(); const before = ui.state();
    t.releaseReceipt(); await bounded(t.responseConsumed, 'A201 consumed by real request/Service'); await ui.sentFinallyObserved(before); captureAfter();
    assertBUnchanged(before, ui.state(), f, t); check(pendingWriteFor(f.base.assessment) === null, 'Validated A201 did not clear original Service attempt');
    terminal('B_EDITABLE_AFTER_ORIGINAL_SUBMIT_FINALLY');
  });

  await scenario('sent_201_exact_A_B_A_accepts_original_valid_receipt', async ({ f, t, ui, p, mark, captureBefore, captureAfter, terminal }) => {
    check(p, 'Original pending absent'); ui.render('B'); await ui.ready(); ui.render('A'); await ui.ready(); ui.sameInstance();
    check(pendingWriteFor(f.base.assessment) === p && ui.state().pendingVisible, 'Exact ABA return did not preserve original pending identity');
    mark('exact-original-scope-restored-not-an-unsent-lease'); captureBefore();
    t.releaseReceipt(); await bounded(t.responseConsumed, 'original valid A201 consumed'); await ui.ready(f.saved.result_id);
    await until(() => ui.state().success.some(s => s.includes('已保存独立结果第 2 版')), 'valid original receipt applied on exact original scope'); captureAfter();
    const q = new URL(ui.state().fixedUrl).searchParams;
    check(q.get('assessment_id') === f.base.assessment.id && q.get('p2_result') === f.saved.result_id && !ui.state().pendingVisible && pendingWriteFor(f.base.assessment) === null, 'Exact ABA accepted receipt not bound to original A');
    check(t.materialPosts().length === 1 && t.nonGet.length === 1, 'Exact ABA caused replay'); terminal('EXACT_A_SCOPE_VALID_SENT_RECEIPT_ACCEPTED');
  });

  for (const view of ['A_OTHER_RESULT', 'A_OTHER_BINDING'] as const) {
    await scenario('sent_201_same_Assessment_on_return_changed_' + (view === 'A_OTHER_RESULT' ? 'Result' : 'Binding'), async ({ f, t, ui, p, mark, captureBefore, captureAfter, terminal }) => {
      check(p, 'Original pending absent'); ui.render('B'); await ui.ready(); ui.render(view); await ui.ready(); ui.sameInstance();
      const before = ui.state(); mark('same-Assessment-return-current-scope-differs'); captureBefore();
      t.releaseReceipt(); await bounded(t.responseConsumed, 'old A201 consumed against captured original Binding'); await ui.sentFinallyObserved(before); captureAfter();
      const after = ui.state(); check(after.resultId === before.resultId && after.fixedUrl === before.fixedUrl && JSON.stringify(after.success) === JSON.stringify(before.success) && after.error.length === 0 && !after.pendingVisible, 'Old receipt contaminated changed Result/Binding scope');
      check(pendingWriteFor(f.base.assessment) === null && t.materialPosts().length === 1 && t.nonGet.length === 1, 'Changed-scope receipt repeated write or lost valid original service completion');
      terminal('CHANGED_SCOPE_EDITABLE_AFTER_ORIGINAL_SUBMIT_FINALLY');
    });
  }

  await scenario('sent_409_A_to_B_retains_only_original_A_conflict', async ({ f, t, ui, p, mark, captureBefore, captureAfter, terminal }) => {
    check(p, 'Original pending absent'); ui.render('B'); await ui.ready(); const before = ui.state(); mark('B-loaded-before-A409-release'); captureBefore();
    t.releaseReceipt(); await bounded(t.responseConsumed, 'A409 consumed by real request'); await ui.sentFinallyObserved(before); captureAfter();
    assertBUnchanged(before, ui.state(), f, t); check(pendingWriteFor(f.base.assessment) === p && !canReplayWrite(f.base.assessment), '409 original pending lost or replay enabled');
    ui.render('A'); await ui.ready(); ui.sameInstance(); await until(() => ui.state().pendingVisible, 'A original conflict restored after read-only reload');
    check(pendingWriteFor(f.base.assessment) === p && !canReplayWrite(f.base.assessment) && t.materialPosts().length === 1 && t.nonGet.length === 1, 'Returning to A rebuilt/replayed conflict');
    const replay = ui.button('使用原请求再次确认'); check(replay?.disabled === true, '409 replay must remain disabled until original recovery policy permits');
    terminal('A_CONFLICT_PENDING_RESTORED_WITHOUT_REPLAY');
  }, { responseStatus: 409 });

  await scenario('sent_409_exact_A_B_A_is_original_scope_error_not_success', async ({ f, t, ui, p, mark, captureBefore, captureAfter, terminal }) => {
    check(p, 'Original pending absent'); ui.render('B'); await ui.ready(); ui.render('A'); await ui.ready(); ui.sameInstance(); mark('exact-A-restored-before409'); captureBefore();
    t.releaseReceipt(); await bounded(t.responseConsumed, 'A409 consumed');
    await until(() => ui.state().error.some(s => s.includes('结果已变化或提交发生冲突') && s.includes('synthetic_material_conflict')), 'real original-scope conflict UI'); captureAfter();
    check(ui.state().resultId === f.base.result.result_id && ui.state().success.length === 0 && ui.state().pendingVisible && pendingWriteFor(f.base.assessment) === p && !canReplayWrite(f.base.assessment), '409 created success/replaced Result/lost pending');
    check(t.materialPosts().length === 1 && t.nonGet.length === 1, '409 replayed'); terminal('ORIGINAL_A_CONFLICT_VISIBLE_NO_SUCCESS');
  }, { responseStatus: 409 });

  await scenario('pre_dispatch_A_B_A_never_revives_old_File_lease', async ({ f, t, ui, gate, form, mark, captureBefore, captureAfter, terminal }) => {
    check(t.materialPosts().length === 0 && !gate.state.released && pendingWriteFor(f.base.assessment) === null, 'Pre-dispatch control already wrote');
    ui.render('B'); await ui.ready(); ui.render('A'); await ui.ready(); ui.sameInstance(); mark('ABA-committed-before-File-release'); captureBefore();
    gate.release(); await until(() => gate.state.resolved && form.getAttribute('aria-busy') === 'false', 'detached original MaterialForm finally after actual read/digest continuation');
    await act(async () => { await taskBoundary(); }); captureAfter();
    check(!form.isConnected && t.materialPosts().length === 0 && t.nonGet.length === 0 && pendingWriteFor(f.base.assessment) === null && ui.state().resultId === f.base.result.result_id && ui.state().success.length === 0, 'Unsent ABA lease revived');
    terminal('DETACHED_FILE_FINALLY_NO_POST');
  }, { send: false });

  report.status = report.cases.some(c => c.status === 'failed') ? 'failed' : report.cases.some(c => c.status === 'NOT_ESTABLISHED') ? 'NOT_ESTABLISHED' : 'passed';
  report.finishedAt = new Date().toISOString(); display(); return report;
}
window.runP2MaterialSentReceiptScope = runP2MaterialSentReceiptScope;
document.querySelector('#run')!.addEventListener('click', () => { void runP2MaterialSentReceiptScope().catch(error => { report.status = error instanceof NotEstablished ? 'NOT_ESTABLISHED' : 'failed'; report.finishedAt = new Date().toISOString(); document.querySelector('#error')!.textContent = error instanceof Error ? error.stack ?? error.message : String(error); display(); }); });
display();
