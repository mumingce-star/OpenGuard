import { act, Profiler } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { P2Workbench } from '../../src/components/P2Workbench';
import { beginUsageUpdate, submitUsageUpdate, readPendingUsageUpdate, type UsageUpdateOperation } from '../../src/services/projectUsage';
import { ACTION_R1, ACTION_R2 } from '../bound-advice-maincard/fixture';
import { integrationFixture, type IntegrationFixture } from './fixture';
import { closedTransport, check, type RequestRow, type Options } from './transport';

/** SOURCE ONLY / NOT_RUN. This suite mounts the REAL Workbench and its REAL
 * Editor, projectUsage.ts and p2.ts. Only the lowest fetch boundary is synthetic.
 * It is not browser reception, ASGI, source attestation or a permission grant. */
type CaseRow = { name: string; status: 'passed' | 'failed'; error: string | null;
  requests: RequestRow[]; unknown: RequestRow[]; nonGet: RequestRow[];
  events: { name: string; cutoff: number; utc: string }[];
  mountPhases: string[]; requestId: string; stored: string | null };
const report = {
  classification: 'SYNTHETIC_TEST_ONLY_REAL_WORKBENCH_AND_SERVICES_CLOSED_FETCH' as const,
  status: 'NOT_RUN' as 'NOT_RUN' | 'running' | 'passed' | 'failed',
  startedAt: null as string | null, finishedAt: null as string | null,
  actualBackendRequests: null, asgi: null, receiverAcceptance: null,
  cases: [] as CaseRow[], transportSelfcheck: null as unknown,
};
declare global { interface Window {
  __P2_INTEGRATION_BOUNDARY__: typeof report;
  runP2IntegrationBoundary: () => Promise<typeof report>;
} }
window.__P2_INTEGRATION_BOUNDARY__ = report;
function display() { document.querySelector('#results')!.textContent = JSON.stringify(report, null, 2); }
function bounded<T>(promise: Promise<T>, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(Error('Failure watchdog: ' + label)), 5000);
    promise.then(v => { clearTimeout(timer); resolve(v); }, e => { clearTimeout(timer); reject(e); });
  });
}
function taskBoundary() {
  return new Promise<void>(resolve => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => { channel.port1.close(); channel.port2.close(); resolve(); };
    channel.port2.postMessage(null);
  });
}
async function settled(predicate: () => boolean, label: string) {
  let cancelled = false;
  try {
    await bounded((async () => {
      while (!cancelled && !predicate()) await act(async () => { await taskBoundary(); });
    })(), label);
  } finally { cancelled = true; }
}
function mainCard(host: HTMLElement) {
  const card = host.querySelector<HTMLElement>('[data-bound-advice-maincard]');
  check(card && !card.closest('details'), 'Real saved Advice main card missing/collapsed');
  return card;
}
function exactAction(host: HTMLElement, action: string) {
  return Array.from(mainCard(host).querySelectorAll('li,p')).some(n => n.textContent === action);
}
function assertCard(host: HTMLElement, revision: 1 | 2) {
  const card = mainCard(host), action = revision === 1 ? ACTION_R1 : ACTION_R2;
  check(card.dataset.resultRevision === String(revision), 'Wrong main-card revision');
  check(exactAction(host, action), 'Saved condition absent/changed');
  check(!card.textContent?.includes(revision === 1 ? ACTION_R2 : ACTION_R1), 'Another Result Advice leaked');
}
type Transport = ReturnType<typeof closedTransport>;
function mount(f: IntegrationFixture, initialReadOnly = true) {
  const host = document.createElement('div'); document.querySelector('#mounts')!.append(host);
  const root = createRoot(host), phases: string[] = [];
  function render(readOnly: boolean) {
    flushSync(() => root.render(<Profiler id={f.requestId} onRender={(_id, phase) => { phases.push(phase); }}>
      <div data-test-readonly={String(readOnly)}><P2Workbench scan={f.base.scan} assessment={f.base.assessment} readOnly={readOnly}/></div>
    </Profiler>));
  }
  render(initialReadOnly);
  const workbench = host.querySelector('.p2-workbench');
  check(workbench, 'Real Workbench did not mount');
  const button = (label: string) => Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(b => b.textContent === label) ?? null;
  function editor() { const value = host.querySelector<HTMLElement>('.project-usage-editor'); check(value, 'Actual nested Editor missing'); return value; }
  return { host, phases, render, button, editor,
    assertSameInstance(editorBefore?: HTMLElement) {
      check(host.querySelector('.p2-workbench') === workbench, 'Workbench subtree replaced');
      check(phases.filter(p => p === 'mount').length === 1, 'Different Workbench React mount');
      if (editorBefore) check(editor() === editorBefore, 'Nested Editor remounted during authority change');
    },
    async revealEditor() {
      const summary = host.querySelector<HTMLElement>('details.p2-optional > summary');
      check(summary, 'Real optional section missing');
      if (!summary.parentElement?.hasAttribute('open')) flushSync(() => summary.click());
      await settled(() => !!button('补充项目用途'), 'usage tab exists');
      flushSync(() => button('补充项目用途')!.click());
      await settled(() => !editor().closest('[hidden]'), 'actual Editor visible');
      return editor();
    },
    dispose() { flushSync(() => root.unmount()); host.remove(); },
  };
}
type UI = ReturnType<typeof mount>;
async function seed(f: IntegrationFixture, t: Transport) {
  const op = beginUsageUpdate(f.base.assessment, f.changed, f.requestId);
  const value = await submitUsageUpdate(op);
  check(value.phase === 'pending', 'Real service did not preserve seed pending');
  check(t.nonGet.length === 1 && t.nonGet[0].route === 'seed-assessment-post', 'Seed request not exactly one synthetic Assessment POST');
  return op;
}
function originalPending(f: IntegrationFixture, op: UsageUpdateOperation, p2Attempted: boolean) {
  check(readPendingUsageUpdate(f.base.assessment) === op, 'Original pending object replaced/cleared');
  const raw = sessionStorage.getItem(f.storageKey); check(raw, 'Original stored request missing');
  const saved = JSON.parse(raw);
  check(saved.requestId === op.requestId && op.requestId === f.requestId, 'Request identity regenerated');
  check(saved.complete === false && saved.p2Attempted === p2Attempted, 'Attempt/pending state changed incorrectly');
  check(!raw.includes('canWrite'), 'UI capability serialized into storage');
}
type Context = { f: IntegrationFixture; t: Transport; ui: UI;
  events: CaseRow['events']; mark: (name: string) => number };
async function scenario(name: string, action: (ctx: Context, op: UsageUpdateOperation | null) => Promise<void>,
  options: Options & { pending?: boolean; initialReadOnly?: boolean; mixed?: boolean; expectedWrites?: number } = {}) {
  const f = integrationFixture(name, options.mixed), t = closedTransport(f, options);
  const priorHref = window.location.href;
  // Intentionally no restoration to native fetch: late buggy continuations
  // remain closed. The approved harness must discard this test page at the end.
  window.fetch = t.fetch;
  window.history.replaceState(null, '', `/app/scans/${f.base.scan.id}/assessment?mode=api&assessment_id=${f.base.assessment.id}&assessment_version=1&p2_result=${f.base.result.result_id}`);
  const events: CaseRow['events'] = [];
  let ui: UI | undefined, error: unknown;
  try {
    const op = options.pending ? await seed(f, t) : null;
    ui = mount(f, options.initialReadOnly ?? true);
    await settled(() => !!ui!.host.querySelector('[data-bound-advice-maincard]'), 'main card saved Result');
    await action({ f, t, ui, events, mark: name => { const cutoff = t.mark(); events.push({ name, cutoff, utc: new Date().toISOString() }); return cutoff; } }, op);
    check(t.unknown.length === 0, 'Independent unknown-route ledger nonempty (even if caught by product)');
    check(t.nonGet.length === (options.expectedWrites ?? 0), 'Unexpected total non-GET dispatch count');
  } catch (e) { error = e; }
  finally {
    ui?.dispose();
    try {
      await bounded(t.drainAfterUnmount(), 'closed transport teardown'); await taskBoundary();
      check(t.unknown.length === 0, 'Unknown late request after unmount');
      check(t.nonGet.length === (options.expectedWrites ?? 0), 'Unexpected late non-GET after unmount');
    } catch (e) { if (!error) error = e; }
    report.cases.push({ name, status: error ? 'failed' : 'passed', error: error instanceof Error ? error.message : error ? String(error) : null,
      requests: [...t.ledger], unknown: [...t.unknown], nonGet: [...t.nonGet], events,
      mountPhases: ui ? [...ui.phases] : [], requestId: f.requestId, stored: sessionStorage.getItem(f.storageKey) });
    sessionStorage.removeItem(f.storageKey); window.history.replaceState(null, '', priorHref); display();
  }
  if (error) throw error;
}

export async function runP2IntegrationBoundary() {
  check(report.status === 'NOT_RUN', 'One suite invocation per fresh isolated page');
  report.status = 'running'; report.startedAt = new Date().toISOString();
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  try {
    // Explicit selfcheck has its OWN ledger, never counted as product requests.
    const self = closedTransport(integrationFixture('ledger_selfcheck'));
    let refused = 0;
    for (const [path, method] of [['/api/v1/cross-unknown', 'GET'], ['/api/v1/cross-unknown', 'DELETE']] as const) {
      try { await self.fetch(path, { method }); } catch { refused++; }
    }
    check(refused === 2 && self.unknown.length === 2 && self.nonGet.length === 1 && self.ledger.length === 2, 'Closed independent ledger selfcheck failed');
    report.transportSelfcheck = { classification: 'NOT_APPLICATION_REQUESTS', ledger: self.ledger };

    await scenario('same_Workbench_saved_Advice_and_readOnly_pending_entry', async ({ f, t, ui, mark }, op) => {
      assertCard(ui.host, 1); const nested = await ui.revealEditor();
      await settled(() => !!ui.button('读取本次保存进度'), 'pending action');
      check(ui.button('读取本次保存进度')!.disabled, 'Workbench did not pass independent readOnly');
      const cutoff = mark('readOnly-entry-committed');
      flushSync(() => { ui.button('读取本次保存进度')!.click(); nested.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
      await act(async () => { await taskBoundary(); });
      check(t.nonGetsAfter(cutoff).length === 0 && t.resultPosts().length === 0, 'Passive/readOnly entry dispatched a write');
      originalPending(f, op!, false); assertCard(ui.host, 1);
    }, { pending: true, expectedWrites: 1 });

    await scenario('same_Workbench_Index_hang_readOnly_commit_release_zero_Result_POST', async ({ f, t, ui, mark }, op) => {
      assertCard(ui.host, 1); const nested = await ui.revealEditor();
      await settled(() => !!ui.button('读取本次保存进度'), 'pending recovery action');
      check(!ui.button('读取本次保存进度')!.disabled, 'Editable recovery disabled');
      flushSync(() => ui.button('读取本次保存进度')!.click());
      await bounded(t.recoveryEntered, 'saved-next exact Index GET entered');
      check(t.resultPosts().length === 0, 'Result POST before Index release');
      ui.render(true); ui.assertSameInstance(nested);
      check(ui.host.firstElementChild?.getAttribute('data-test-readonly') === 'true', 'ReadOnly prop not committed');
      const cutoff = mark('readOnly-commit-before-recovery-Index-release');
      t.releaseRecovery();
      await settled(() => !!ui.button('读取本次保存进度'), 'revoked recovery settled');
      check(ui.button('读取本次保存进度')!.disabled, 'Revoked recovery action not disabled');
      check(t.resultPosts().length === 0 && t.nonGetsAfter(cutoff).length === 0, 'New write after readOnly commit');
      check(t.ledger.some(r => r.route === 'main-index') && t.ledger.some(r => r.route === 'recovery-index'), 'Test conflated Workbench and saved-next Index');
      originalPending(f, op!, false); assertCard(ui.host, 1);
    }, { pending: true, initialReadOnly: false, expectedWrites: 1 });

    await scenario('ordinary_loading_disabled_still_allows_explicit_original_recovery', async ({ f, t, ui, mark }, op) => {
      const nested = await ui.revealEditor();
      await settled(() => !!ui.button('读取本次保存进度'), 'pending recovery action');
      t.armMainIndexHold();
      const latest = ui.button('查看当前结果 r2'); check(latest && !latest.disabled, 'Explicit main-head refresh unavailable');
      flushSync(() => latest.click()); await bounded(t.mainEntered, 'main Index loading gate');
      check(nested.querySelector<HTMLFieldSetElement>('.project-usage-fields')!.disabled, 'Real Workbench loading did not set ordinary disabled');
      check(!ui.button('读取本次保存进度')!.disabled, 'Ordinary disabled incorrectly became readOnly');
      const cutoff = mark('ordinary-disabled-explicit-recovery');
      flushSync(() => ui.button('读取本次保存进度')!.click());
      await bounded(t.recoveryEntered, 'distinct saved-next Index'); t.releaseRecovery();
      await bounded(t.resultPostEntered, 'actual service Result fetch invocation');
      await settled(() => !!ui.button('读取本次保存进度'), 'uncertain receipt retained');
      check(t.nonGetsAfter(cutoff).length === 1 && t.resultPosts().length === 1, 'Editable recovery dispatched wrong writes');
      const body = JSON.parse(t.resultPosts()[0].body);
      check(body.idempotency_key === 'usage_' + op!.requestId, 'Result idempotency identity changed');
      originalPending(f, op!, true); ui.assertSameInstance(nested);
      t.releaseMain(); await settled(() => ui.host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultRevision === '2', 'r2 main refresh');
      assertCard(ui.host, 2);
    }, { pending: true, initialReadOnly: false, expectedWrites: 2 });

    await scenario('readOnly_new_draft_submit_with_Advice_never_starts_write', async ({ f, t, ui, mark }) => {
      const nested = await ui.revealEditor();
      const radio = nested.querySelector<HTMLInputElement>('input[name="project-usage-commercial"][value="false"]');
      check(radio && !radio.disabled, 'Editable radio missing'); flushSync(() => radio.click());
      check(radio.checked, 'Draft did not really change');
      ui.render(true); ui.assertSameInstance(nested); const cutoff = mark('changed-draft-readOnly-committed');
      flushSync(() => nested.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
      await act(async () => { await taskBoundary(); });
      check(t.nonGetsAfter(cutoff).length === 0 && readPendingUsageUpdate(f.base.assessment) === null, 'ReadOnly new submit created operation/write');
      assertCard(ui.host, 1);
    }, { initialReadOnly: false });

    await scenario('same_Workbench_r1_to_r2_late_old_derived_cannot_replace_saved_Advice', async ({ t, ui, mark }) => {
      assertCard(ui.host, 1); await bounded(t.oldAutomaticEntered, 'old derived GET hangs');
      const latest = ui.button('查看当前结果 r2'); check(latest, 'Explicit r2 selection missing');
      flushSync(() => latest.click());
      await settled(() => ui.host.querySelector<HTMLElement>('[data-bound-advice-maincard]')?.dataset.resultRevision === '2', 'saved r2 committed');
      ui.assertSameInstance(); const cutoff = mark('fixed-r2-committed-before-old-derived-release');
      t.releaseOldAutomatic(); await act(async () => { await taskBoundary(); });
      assertCard(ui.host, 2); check(t.nonGetsAfter(cutoff).length === 0, 'Passive Result switch wrote');
      check(t.ledger.some(r => r.route === 'fixed-r1') && t.ledger.some(r => r.route === 'fixed-r2'), 'Real fixed Result services not both consumed');
      check(new URL(window.location.href).searchParams.get('p2_result') === mainCard(ui.host).dataset.resultId, 'URL and saved card diverged');
    }, { holdOldAutomatic: true });

    await scenario('derived_503_keeps_saved_Advice_and_pending_readOnly_guard', async ({ t, ui, mark }) => {
      await settled(() => !!ui.host.querySelector('.auto-review-error'), 'derived 503 rendered');
      check(ui.host.textContent?.includes('自动初评暂未读回'), 'Explicit derived error omitted');
      assertCard(ui.host, 1); await ui.revealEditor();
      await settled(() => !!ui.button('读取本次保存进度'), 'pending guard retained with derived failure');
      const cutoff = mark('derived-error-readOnly-entry');
      check(ui.button('读取本次保存进度')!.disabled, 'Derived failure removed readOnly authority');
      flushSync(() => ui.button('读取本次保存进度')!.click()); await taskBoundary();
      check(t.nonGetsAfter(cutoff).length === 0, 'Derived failure caused business write'); assertCard(ui.host, 1);
    }, { pending: true, expectedWrites: 1, automatic503: true });

    await scenario('mixed_basis_neutral_in_real_readOnly_Workbench', async ({ t, ui }) => {
      const card = mainCard(ui.host);
      check(card.querySelector('[data-bound-advice-notice="BASIS_INDIRECT_UNCONFIRMED"]'), 'Mixed direct/indirect reason missing');
      check(card.textContent?.includes('已有保存的条件依据，其中间接来源尚未完成当前视图的独立关联核验；可查看逐资源依据。'), 'Mixed basis wording not accurate');
      check(!card.querySelector('[data-bound-advice-resource]') && !exactAction(ui.host, ACTION_R1), 'Unconfirmed indirect basis granted main-card support');
      check(!card.textContent?.includes('禁止使用') && !card.textContent?.includes('已确认允许商业使用'), 'Unknown was rewritten as permission/prohibition');
      await ui.revealEditor(); await act(async () => { await taskBoundary(); });
      check(t.nonGet.length === 0, 'Passive mixed/readOnly view wrote');
    }, { mixed: true });
    report.status = 'passed';
  } catch (error) { report.status = 'failed'; throw error; }
  finally { report.finishedAt = new Date().toISOString(); display(); }
  return report;
}
window.runP2IntegrationBoundary = runP2IntegrationBoundary;
document.querySelector<HTMLButtonElement>('#run')!.addEventListener('click', () => {
  void runP2IntegrationBoundary().catch(error => { document.querySelector('#error')!.textContent = error instanceof Error ? error.message : String(error); });
});
display();
