import { act, Profiler } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { P2Workbench } from '../../src/components/P2Workbench';
import { pendingWriteFor } from '../../src/services/p2';
import { FILE_BYTES, FILE_SHA256, SOURCE_DESCRIPTION, materialFixture, type MaterialFixture } from './fixture';
import { check, closedTransport, deferred, type Options, type RequestRow } from './transport';

/** SOURCE ONLY / NOT_RUN. No MaterialForm/write/submitWrite/materialBytes/Service
 * function is replaced. Real React + Service code runs only in a future approved
 * complete frontend copy; only bottom fetch and a synthetic File wait are closed. */
type Settlement = 'FINALLY_OBSERVED' | 'MATERIAL_POST_OBSERVED' | 'SAVED_RESULT_OBSERVED' | 'ENTRY_REJECTED_WITHOUT_FILE_READ' | 'RECEIPT_REJECTED_ORIGINAL_PENDING_RETAINED';
type EventRow = { name: string; utc: string; cutoff: number };
type CaseRow = { name: string; status: 'passed' | 'failed' | 'NOT_ESTABLISHED'; error: string | null;
  events: EventRow[]; requests: RequestRow[]; nonGet: RequestRow[]; unknown: RequestRow[];
  file: { calls: number; entered: boolean; released: boolean; bufferResolved: boolean } | null;
  settlement: Settlement | null; mountPhases: string[]; actualBackendRequests: null };
const report = { classification: 'SYNTHETIC_TEST_ONLY_REAL_COMPONENT_MATERIAL_SERVICE_CLOSED_FETCH' as const,
  status: 'NOT_RUN' as 'NOT_RUN' | 'running' | 'passed' | 'failed' | 'NOT_ESTABLISHED',
  startedAt: null as string | null, finishedAt: null as string | null,
  productTestsExecutedInSourcePreparation: false, junit: null, actualBackendRequests: null,
  browserReceiverAcceptance: null, transportSelfcheck: null as unknown, cases: [] as CaseRow[] };
declare global { interface Window { __P2_MATERIAL_ASYNC_READONLY__: typeof report; runP2MaterialAsyncReadonly: () => Promise<typeof report> } }
window.__P2_MATERIAL_ASYNC_READONLY__ = report;
class NotEstablished extends Error {}
class ActualLedgerViolation extends Error {}
function display() { document.querySelector('#results')!.textContent = JSON.stringify(report, null, 2); }
function bounded<T>(promise: Promise<T>, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new NotEstablished('NOT_SETTLED: ' + label)), 5000);
    promise.then(v => { clearTimeout(timer); resolve(v); }, e => { clearTimeout(timer); reject(e); });
  });
}
function taskBoundary() {
  return new Promise<void>(resolve => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => { channel.port1.close(); channel.port2.close(); resolve(); }; channel.port2.postMessage(null);
  });
}
async function until(predicate: () => boolean, label: string) {
  let cancelled = false;
  try { await bounded((async () => { while (!cancelled && !predicate()) await act(async () => { await taskBoundary(); }); })(), label); }
  finally { cancelled = true; }
}
function gatedFile() {
  const state = { calls: 0, entered: false, released: false, bufferResolved: false };
  const entered = deferred<void>(), released = deferred<void>();
  const file = new File([FILE_BYTES], 'LICENSE', { type: 'text/plain', lastModified: 0 });
  Object.defineProperty(file, 'arrayBuffer', { configurable: false, value: async () => {
    state.calls++; check(state.calls === 1, 'File.arrayBuffer called more than once');
    state.entered = true; entered.resolve(); await released.promise;
    state.bufferResolved = true;
    // Only the File wait is synthetic. Real materialBytes performs UTF-8/base64
    // conversion and the real WebCrypto SHA-256 after this buffer is returned.
    return FILE_BYTES.slice().buffer;
  } });
  return { file, state, entered: entered.promise, release() { check(!state.released, 'File released twice'); state.released = true; released.resolve(); } };
}
type Gate = ReturnType<typeof gatedFile>;
type Transport = ReturnType<typeof closedTransport>;
function mount(f: MaterialFixture) {
  const host = document.createElement('div'); document.querySelector('#mounts')!.append(host);
  const root = createRoot(host), phases: string[] = []; let disposed = false;
  function render(readOnly: boolean, alternate = false) {
    check(!disposed, 'Render after test root was unmounted');
    const bundle = alternate ? f.alternate : f.base;
    flushSync(() => root.render(<Profiler id={f.base.scan.id} onRender={(_id, phase) => { phases.push(phase); }}>
      <div data-readonly={String(readOnly)} data-assessment={bundle.assessment.id}>
        <P2Workbench scan={bundle.scan} assessment={bundle.assessment} readOnly={readOnly}/>
      </div>
    </Profiler>));
  }
  render(false); const workbench = host.querySelector('.p2-workbench'); check(workbench, 'Real Workbench absent');
  function button(text: string) { return Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(b => b.textContent === text) ?? null; }
  return { host, phases, render, button,
    sameInstance() { check(host.querySelector('.p2-workbench') === workbench && phases.filter(p => p === 'mount').length === 1, 'Workbench was remounted'); },
    async ready(resultId = f.base.result.result_id) {
      await until(() => host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultId === resultId && !host.querySelector('[role="status"]')?.textContent?.includes('正在读取当前对象'), 'fixed saved Result displayed');
    },
    async prepareForm(gate: Gate) {
      const summary = host.querySelector<HTMLElement>('details.p2-optional > summary'); check(summary, 'Optional material section absent');
      if (!summary.parentElement?.hasAttribute('open')) flushSync(() => summary.click());
      await until(() => !!button('补充 LICENSE / NOTICE'), 'real Material tab');
      flushSync(() => button('补充 LICENSE / NOTICE')!.click());
      await until(() => !!host.querySelector('.p2-material-form'), 'real MaterialForm');
      const form = host.querySelector<HTMLFormElement>('.p2-material-form')!;
      const select = form.querySelector<HTMLSelectElement>('select')!;
      check(!form.querySelector<HTMLFieldSetElement>('fieldset')!.disabled, 'Material is not editable/head before gate');
      flushSync(() => { select.value = f.target.subject.resource_id; select.dispatchEvent(new Event('change', { bubbles: true })); });
      await until(() => !!form.querySelector('input[type="checkbox"]'), 'exact resource Evidence choices');
      const evidence = form.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
      flushSync(() => evidence.click()); check(evidence.checked, 'Evidence was not actually selected');
      const file = form.querySelector<HTMLInputElement>('input[type="file"]')!;
      const files = { 0: gate.file, length: 1, item: (i: number) => i === 0 ? gate.file : null };
      Object.defineProperty(file, 'files', { configurable: true, value: files });
      flushSync(() => file.dispatchEvent(new Event('change', { bubbles: true })));
      const description = form.querySelector<HTMLInputElement>('input[maxlength="512"]')!;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      flushSync(() => { setter.call(description, SOURCE_DESCRIPTION); description.dispatchEvent(new Event('input', { bubbles: true })); });
      check(select.value === f.target.subject.resource_id && file.files?.[0] === gate.file && description.value === SOURCE_DESCRIPTION, 'Form data was not entered');
      const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]')!;
      check(!submit.disabled, 'Material submit still invalid/disabled');
      return form;
    },
    async startFile(form: HTMLFormElement, gate: Gate) {
      flushSync(() => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
      await bounded(gate.entered, 'actual File.arrayBuffer entered');
      check(gate.state.entered && !gate.state.released && !gate.state.bufferResolved, 'File Promise was not actually pending');
      await act(async () => { await taskBoundary(); });
      check(form.textContent?.includes('正在核对文件'), 'Real MaterialForm reading state not committed');
      return form;
    },
    dispose() { if (!disposed) { disposed = true; flushSync(() => root.unmount()); host.remove(); } },
  };
}
type UI = ReturnType<typeof mount>;
/** Parent-compatible terminal observation. The parent does not have aria-busy:
 * absence alone is NEVER a failure. An actual unsafe POST is the red predicate.
 * For the candidate, the captured form's finally marker proves completion even
 * when it has been detached. If neither happens, report NOT_ESTABLISHED. */
async function revokedSettlement(form: HTMLFormElement, gate: Gate, t: Transport): Promise<Settlement> {
  const hadBusy = form.getAttribute('aria-busy') === 'true';
  check(gate.state.entered && !gate.state.released, 'Release requires an entered pending real File read');
  gate.release();
  let cancelled = false;
  try {
    const outcome = await bounded(Promise.race([
      t.postEntered.then(() => 'MATERIAL_POST_OBSERVED' as const),
      (async () => {
        while (!cancelled && !(hadBusy && form.getAttribute('aria-busy') === 'false')) await act(async () => { await taskBoundary(); });
        if (cancelled) return new Promise<never>(() => {});
        return 'FINALLY_OBSERVED' as const;
      })(),
    ]), 'read/digest continuation terminal event (not just File resolution)');
    await act(async () => { await taskBoundary(); });
    check(gate.state.bufferResolved, 'Continuation terminal observed before File buffer delivery');
    return outcome;
  } finally { cancelled = true; }
}
type Context = { f: MaterialFixture; t: Transport; ui: UI; gate: Gate; form: HTMLFormElement;
  mark: (name: string) => number; finish: () => Promise<void>; savedReceiptObserved: () => void;
  entryRejectedObserved: () => void; receiptRejectedObserved: () => void };
async function scenario(name: string, action: (ctx: Context) => Promise<void>, options: Options & { startRead?: boolean } = {}) {
  const f = materialFixture(name), t = closedTransport(f, options), gate = gatedFile();
  const prior = window.location.href, events: EventRow[] = []; let ui: UI | undefined, form: HTMLFormElement | undefined;
  let error: unknown, settlement: Settlement | null = null;
  // Remain closed during teardown: NEVER restore native fetch between cases.
  window.fetch = t.fetch;
  window.history.replaceState(null, '', `/app/scans/${f.base.scan.id}/assessment?mode=api&assessment_id=${f.base.assessment.id}&assessment_version=1&p2_result=${f.base.result.result_id}`);
  try {
    ui = mount(f); await ui.ready(); form = await ui.prepareForm(gate);
    if (options.startRead !== false) await ui.startFile(form, gate);
    await action({ f, t, ui, gate, form,
      mark: label => { const cutoff = t.mark(); events.push({ name: label, utc: new Date().toISOString(), cutoff }); return cutoff; },
      finish: async () => { settlement = await revokedSettlement(form!, gate, t); check(settlement !== 'MATERIAL_POST_OBSERVED', 'Actual Material POST dispatched after authority revocation'); },
      savedReceiptObserved: () => { settlement = 'SAVED_RESULT_OBSERVED'; },
      entryRejectedObserved: () => { settlement = 'ENTRY_REJECTED_WITHOUT_FILE_READ'; },
      receiptRejectedObserved: () => { settlement = 'RECEIPT_REJECTED_ORIGINAL_PENDING_RETAINED'; },
    });
    check(t.unknown.length === 0, 'Independent unknown-route ledger is nonempty even if product caught the exception');
  } catch (e) { error = e; }
  finally {
    ui?.dispose();
    try {
      if (!gate.state.released) gate.release();
      await bounded(t.drain(), 'actual closed transport completion'); await act(async () => { await taskBoundary(); });
      const permitted = options.holdReceipt || name === 'stable_editable_exactly_one_Material_POST' ? 1 : 0;
      if (t.unknown.length > 0) throw new ActualLedgerViolation('Actual unknown request survived product catch');
      if (t.materialPosts().length > permitted || t.nonGet.length > permitted) throw new ActualLedgerViolation('Actual extra non-GET/Material POST in independent final ledger');
      if (t.materialPosts().length !== permitted || t.nonGet.length !== permitted) throw new NotEstablished('Expected dispatch not established in independent final ledger');
    } catch (e) {
      // A missing expected request cannot turn a timeout/setup gap into a target
      // red assertion. Only an actually observed extra/unknown request can.
      if (!error || (error instanceof NotEstablished && e instanceof ActualLedgerViolation)) error = e;
    }
    report.cases.push({ name, status: error instanceof NotEstablished ? 'NOT_ESTABLISHED' : error ? 'failed' : 'passed',
      error: error instanceof Error ? error.message : error ? String(error) : null, events,
      requests: [...t.ledger], nonGet: [...t.nonGet], unknown: [...t.unknown], file: { ...gate.state }, settlement,
      mountPhases: ui ? [...ui.phases] : [], actualBackendRequests: null });
    window.history.replaceState(null, '', prior); display();
  }
  // Never swap to the next transport while an old asynchronous continuation is
  // unaccounted for. A watchdog is NOT a red/green product assertion.
  if (error) {
    report.status = error instanceof NotEstablished ? 'NOT_ESTABLISHED' : 'failed';
    report.finishedAt = new Date().toISOString(); display(); throw error;
  }
}

export async function runP2MaterialAsyncReadonly() {
  check(report.status === 'NOT_RUN', 'Run once per fresh isolated test page');
  report.status = 'running'; report.startedAt = new Date().toISOString();
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const self = closedTransport(materialFixture('independent_ledger_selfcheck'));
  let refused = 0;
  for (const [path, method] of [['/api/v1/unknown-material-route', 'GET'], ['/api/v1/unknown-material-route', 'DELETE']] as const) {
    try { await self.fetch(path, { method }); } catch { refused++; }
  }
  check(refused === 2 && self.unknown.length === 2 && self.nonGet.length === 1 && self.ledger.length === 2, 'Independent ledger refusal selfcheck');
  report.transportSelfcheck = { classification: 'NOT_PRODUCT_REQUESTS', ledger: self.ledger };

  await scenario('same_instance_readOnly_commit_during_File_read', async ({ t, ui, finish, mark }) => {
    check(t.materialPosts().length === 0, 'POST before File release'); ui.render(true); ui.sameInstance();
    check(ui.host.firstElementChild?.getAttribute('data-readonly') === 'true', 'readOnly commit absent');
    const cutoff = mark('readOnly-committed-before-File-release'); await finish();
    check(t.nonGetsAfter(cutoff).length === 0 && t.materialPosts().length === 0, 'New non-GET after readOnly commit');
    check(!ui.host.textContent?.includes('已保存独立结果第 2 版'), 'False saved success after revocation');
  });
  await scenario('readOnly_false_true_false_does_not_revive_old_File', async ({ t, ui, finish, mark }) => {
    ui.render(true); ui.sameInstance(); mark('readOnly-true-committed'); ui.render(false); ui.sameInstance();
    check(ui.host.firstElementChild?.getAttribute('data-readonly') === 'false', 'Editable ABA return absent');
    const cutoff = mark('ABA-return-committed-before-File-release'); await finish();
    check(t.materialPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0, 'Old File capability revived on ABA');
  });
  await scenario('Result_r1_to_r2_revokes_detached_old_MaterialForm', async ({ f, t, ui, form, finish, mark }) => {
    const historySummary = ui.host.querySelector<HTMLElement>('details.p2-history > summary'); check(historySummary, 'History UI absent');
    if (!historySummary.parentElement?.hasAttribute('open')) flushSync(() => historySummary.click());
    const more = ui.button('读取更早结果'); check(more, 'Real pagination action absent'); flushSync(() => more.click());
    await until(() => !!ui.button('查看当前结果 r2'), 'real concurrent head r2 observed through Index');
    flushSync(() => ui.button('查看当前结果 r2')!.click()); await ui.ready(f.base.newer.result_id); ui.sameInstance();
    check(!form.isConnected, 'Old Result keyed MaterialForm was not detached');
    const cutoff = mark('fixed-r2-committed-before-old-File-release'); await finish();
    check(t.materialPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0, 'Old r1 File wrote after Result change');
  }, { switchableResult: true });
  await scenario('Assessment_switch_revokes_old_File', async ({ f, t, ui, form, finish, mark }) => {
    window.history.replaceState(null, '', `/app/scans/${f.alternate.scan.id}/assessment?mode=api&assessment_id=${f.alternate.assessment.id}&assessment_version=2&p2_result=${f.alternate.result.result_id}`);
    ui.render(false, true); await ui.ready(f.alternate.result.result_id); ui.sameInstance();
    check(!form.isConnected, 'Old Assessment MaterialForm not detached');
    const cutoff = mark('new-Assessment-committed-before-old-File-release'); await finish();
    check(t.materialPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0, 'Old Assessment File wrote after scope switch');
  });
  await scenario('unmount_revokes_File_and_observes_detached_finally', async ({ t, ui, form, finish, mark }) => {
    ui.dispose(); check(!form.isConnected, 'Captured form still connected after root unmount');
    const cutoff = mark('root-unmounted-before-File-release'); await finish();
    check(t.materialPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0, 'Unmounted File continuation wrote');
  });
  await scenario('material_tab_unmount_revokes_File_while_Workbench_stays_mounted', async ({ t, ui, form, finish, mark }) => {
    const usage = ui.button('补充项目用途'); check(usage && !usage.disabled, 'Real usage tab action absent/disabled');
    flushSync(() => usage.click()); ui.sameInstance();
    await until(() => !form.isConnected, 'actual MaterialForm-only tab unmount');
    check(ui.host.querySelector('.p2-workbench') && ui.host.querySelector('.project-usage-editor'), 'Workbench/Editor should remain mounted after tab switch');
    const cutoff = mark('MaterialForm-only-unmounted-before-File-release'); await finish();
    check(t.materialPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0, 'Detached MaterialForm kept authority through parent Workbench');
  });
  await scenario('stable_editable_exactly_one_Material_POST', async ({ f, t, ui, gate, mark, savedReceiptObserved }) => {
    const cutoff = mark('stable-editable-before-File-release'); gate.release();
    await bounded(t.postEntered, 'real Material POST dispatch'); await ui.ready(f.saved.result_id);
    await until(() => !!ui.host.textContent?.includes('已保存独立结果第 2 版'), 'real validated Receipt success');
    savedReceiptObserved();
    check(gate.state.bufferResolved && t.materialPosts().length === 1 && t.nonGetsAfter(cutoff).length === 1 && t.unknown.length === 0, 'Normal editable path did not dispatch exactly once');
    const post = t.materialPosts()[0], body = JSON.parse(post.body);
    check(post.status === 201 && body.source_sha256 === FILE_SHA256 && body.expected_revision === 1 && body.parent_result_id === f.base.result.result_id, 'Real service request/validated response identity wrong');
    check(pendingWriteFor(f.base.assessment) === null, 'Successful real Service attempt remained pending');
    check(ui.host.textContent?.includes('许可适用性仍待审核'), 'Pending applicability boundary lost');
  });
  await scenario('already_dispatched_receipt_remains_real_after_readOnly', async ({ f, t, ui, gate, mark, savedReceiptObserved }) => {
    gate.release(); await bounded(t.postEntered, 'Material POST already dispatched before readOnly');
    const pending = pendingWriteFor(f.base.assessment); check(pending, 'Real Service did not retain sending request');
    const serialized = pending.serialized, key = pending.body.idempotency_key;
    check(JSON.stringify(pending.body) === serialized && pending.body.expected_revision === 1 && pending.body.parent_result_id === f.base.result.result_id, 'Initial sending request identity missing');
    ui.render(true); ui.sameInstance(); const cutoff = mark('readOnly-committed-after-actual-Material-POST');
    check(pendingWriteFor(f.base.assessment) === pending && pending.serialized === serialized && pending.body.idempotency_key === key, 'Revocation regenerated/lost already-sent pending/CAS/key');
    t.releaseReceipt(); await ui.ready(f.saved.result_id);
    await until(() => !!ui.host.textContent?.includes('已保存独立结果第 2 版'), 'already-dispatched valid receipt accepted');
    savedReceiptObserved();
    check(t.materialPosts().length === 1 && t.nonGetsAfter(cutoff).length === 0, 'Receipt handling replayed or wrote after readOnly');
    check(t.materialPosts()[0].body === serialized && t.materialPosts()[0].status === 201 && pendingWriteFor(f.base.assessment) === null, 'Actual successful receipt not handled with original identity');
  }, { holdReceipt: true });

  await scenario('filled_form_readOnly_before_submit_never_reads_or_writes', async ({ f, t, ui, gate, form, mark, entryRejectedObserved }) => {
    // Form was filled in the editable real component, not skipped or replaced.
    check(form.querySelector<HTMLSelectElement>('select')!.value === f.target.subject.resource_id && form.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked, 'Filled resource/Evidence state missing');
    check(gate.state.calls === 0 && !gate.state.entered && t.materialPosts().length === 0, 'Preparation itself started reading/writing');
    ui.render(true); ui.sameInstance(); const cutoff = mark('filled-form-readOnly-committed-before-submit');
    check(form.querySelector<HTMLFieldSetElement>('fieldset')!.disabled, 'Committed readOnly not reflected in real form');
    flushSync(() => form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    await act(async () => { await taskBoundary(); });
    check(gate.state.calls === 0 && !gate.state.entered && !gate.state.bufferResolved, 'No valid write entry still called File.arrayBuffer');
    check(t.materialPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0 && pendingWriteFor(f.base.assessment) === null, 'Rejected entry created write/pending');
    entryRejectedObserved();
  }, { startRead: false });

  await scenario('wrong_Material_version_201_is_rejected_without_retry', async ({ f, t, ui, gate, mark, receiptRejectedObserved }) => {
    gate.release(); await bounded(t.postEntered, 'real stable Material POST before negative receipt');
    const pending = pendingWriteFor(f.base.assessment); check(pending, 'Original sending request absent');
    const serialized = pending.serialized, key = pending.body.idempotency_key;
    check(JSON.stringify(pending.body) === serialized && pending.body.expected_revision === 1 && pending.body.parent_result_id === f.base.result.result_id, 'Original negative-case CAS/parent/bytes wrong');
    mark('original-request-captured-before-wrong-version-receipt'); t.releaseReceipt();
    await until(() => !!ui.host.querySelector('.p2-workbench > div.p2-message.p2-error[role="alert"]')?.textContent?.includes('提交结果尚未确认'), 'real Service validation rejection rendered (not preliminary 503)');
    await act(async () => { await taskBoundary(); });
    check(ui.host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultId === f.base.result.result_id, 'Invalid Material receipt replaced saved r1');
    check(!ui.host.textContent?.includes('已保存独立结果第 2 版'), 'Wrong-version 201 displayed false save success');
    check(pendingWriteFor(f.base.assessment) === pending && pending.serialized === serialized && pending.body.idempotency_key === key && JSON.stringify(pending.body) === serialized, 'Rejected receipt lost/regenerated original pending identity');
    check(t.materialPosts().length === 1 && t.nonGet.length === 1 && t.materialPosts()[0].body === serialized && t.materialPosts()[0].status === 201, 'Rejected receipt retried or obscured the actually-sent request');
    const received = JSON.parse(t.materialPosts()[0].responseBody!);
    check(received.material.subject.version === '9.9.9' && received.result.resources[0].subject.version === f.target.subject.version, 'Negative receipt did not preserve the intended wrong-version relationship');
    receiptRejectedObserved();
  }, { holdReceipt: true, wrongMaterialVersion: true });

  report.status = report.cases.some(c => c.status === 'failed') ? 'failed' : report.cases.some(c => c.status === 'NOT_ESTABLISHED') ? 'NOT_ESTABLISHED' : 'passed';
  report.finishedAt = new Date().toISOString(); display(); return report;
}
window.runP2MaterialAsyncReadonly = runP2MaterialAsyncReadonly;
document.querySelector('#run')!.addEventListener('click', () => { void runP2MaterialAsyncReadonly().catch(e => {
  report.status = e instanceof NotEstablished ? 'NOT_ESTABLISHED' : 'failed'; report.finishedAt = new Date().toISOString();
  document.querySelector('#error')!.textContent = e instanceof Error ? e.stack ?? e.message : String(e); display();
}); });
display();
