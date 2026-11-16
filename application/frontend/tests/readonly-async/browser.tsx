/** NOT_RUN source. Real ReactDOM mount; closed synthetic fetch, never ASGI evidence. */
import { Profiler } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { ProjectUsageEditor } from '../../src/components/ProjectUsageEditor';
import {
  beginUsageUpdate, submitUsageUpdate, readPendingUsageUpdate,
  type UsageUpdateOperation,
} from '../../src/services/projectUsage';
import { check, fixture, installTransport, type Fixture, type TimelineEvent, type UnexpectedDispatch } from './transport';

const deadlineMs = 5000; // Failure watchdog only. No elapsed delay controls the race.
type Transport = ReturnType<typeof installTransport>;
type CaseRecord = {
  name: string; status: 'PASSED' | 'FAILED'; evidence_kind: 'SYNTHETIC_TRANSPORT_NOT_ASGI';
  error?: string; request_id: string; storage_key: string; timeline: TimelineEvent[];
  unexpected_dispatches: UnexpectedDispatch[];
  readonly_write_checks: { after_sequence: number; post_dispatches: number; non_get_dispatches: number }[];
  stored: unknown; mount_phases: string[]; assertions?: Record<string, unknown>;
};
const result = {
  status: 'NOT_RUN' as 'NOT_RUN' | 'RUNNING' | 'COMPLETED_WITH_FAILURES' | 'COMPLETED',
  evidence_kind: 'SYNTHETIC_TRANSPORT_NOT_ASGI' as const,
  actual_backend_requests: null, asgi_outcome: null, cases: [] as CaseRecord[],
};
declare global { interface Window { __OPENGUARD_READONLY_ASYNC_RESULTS__: typeof result } }
window.__OPENGUARD_READONLY_ASYNC_RESULTS__ = result;
const output = document.querySelector<HTMLPreElement>('#results')!;
const run = document.querySelector<HTMLButtonElement>('#run')!;
function show() { output.textContent = JSON.stringify(result, null, 2); }
show();

function bounded<T>(promise: Promise<T>, label: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('Watchdog: ' + label)), deadlineMs);
    promise.then(value => { clearTimeout(timer); resolve(value); }, error => { clearTimeout(timer); reject(error); });
  });
}
function waitFor<T>(host: HTMLElement, read: () => T | null | false, label: string): Promise<T> {
  return bounded(new Promise<T>((resolve, reject) => {
    const observer = new MutationObserver(checkNow);
    function checkNow() {
      try { const value = read(); if (value) { observer.disconnect(); resolve(value); } }
      catch (error) { observer.disconnect(); reject(error); }
    }
    observer.observe(host, { subtree: true, childList: true, attributes: true, characterData: true });
    checkNow();
    // A watchdog failure is terminal for the page; it is never converted to a pass.
  }), label);
}
function taskBoundary() {
  return new Promise<void>(resolve => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => { channel.port1.close(); channel.port2.close(); resolve(); };
    channel.port2.postMessage(null);
  });
}
function stored(f: Fixture) {
  const raw = sessionStorage.getItem(f.storageKey);
  check(raw !== null, 'Original operation storage key was removed');
  return JSON.parse(raw) as { requestId: string; assessmentAttempted: boolean; p2Attempted: boolean; complete: boolean };
}
function assertOriginal(f: Fixture, op: UsageUpdateOperation, expectedP2Attempted: boolean) {
  check(readPendingUsageUpdate(f.a) === op, 'Pending operation object identity changed or was cleared');
  const value = stored(f);
  check(value.requestId === op.requestId && op.requestId === f.requestId, 'Original request key was replaced');
  check(value.p2Attempted === expectedP2Attempted && value.complete === false, 'Incorrect pending/attempt state');
  check(!JSON.stringify(value).includes('canWrite'), 'UI callback leaked into stored state');
  return value;
}
function editor(f: Fixture, initialReadOnly = false, disabled = false) {
  const host = document.createElement('div');
  document.querySelector('#mounts')!.append(host);
  const root: Root = createRoot(host), phases: string[] = [], pending: boolean[] = [];
  const onPendingChange = (value: boolean) => { pending.push(value); };
  function render(readOnly: boolean, ordinaryDisabled = disabled) {
    flushSync(() => root.render(
      <Profiler id={f.requestId} onRender={(_id, phase) => { phases.push(phase); }}>
        <div data-test-readonly={String(readOnly)}>
          <ProjectUsageEditor assessment={f.a} readOnly={readOnly} disabled={ordinaryDisabled} onPendingChange={onPendingChange} />
        </div>
      </Profiler>,
    ));
  }
  render(initialReadOnly);
  const section = host.querySelector('section.project-usage-editor');
  check(section, 'Actual ProjectUsageEditor DOM did not mount');
  const button = (label = '读取本次保存进度') =>
    Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(b => b.textContent === label) ?? null;
  return {
    host, phases, pending, render, button,
    settled: (label = '读取本次保存进度') => waitFor(host, () => button(label), 'editor action: ' + label),
    assertSameInstance(readOnly: boolean) {
      check(host.querySelector('section.project-usage-editor') === section, 'DOM subtree was replaced');
      check(phases.filter(p => p === 'mount').length === 1, 'Expected one real ReactDOM mount');
      check(phases.some(p => p !== 'mount'), 'No ReactDOM update commit was observed');
      check(host.firstElementChild?.getAttribute('data-test-readonly') === String(readOnly), 'Requested authority props were not committed');
    },
    dispose() { flushSync(() => root.unmount()); host.remove(); },
  };
}
type Editor = ReturnType<typeof editor>;
async function seed(f: Fixture, t: Transport) {
  const op = beginUsageUpdate(f.a, f.changed, f.requestId);
  const value = await submitUsageUpdate(op);
  check(value.phase === 'pending', 'Synthetic seed did not establish a pending Assessment request');
  check(t.assessmentPosts().length === 1, 'Seed must dispatch one actual Assessment POST through real service');
  check(stored(f).assessmentAttempted === true, 'Seed intent was not retained');
  assertOriginal(f, op, false);
  return op;
}
function assertResultIdentity(f: Fixture, t: Transport) {
  const posts = t.resultPosts(); check(posts.length === 1, 'Expected exactly one real service Result POST dispatch');
  const body = JSON.parse(posts[0].requestBody);
  check(body.idempotency_key === 'usage_' + f.requestId, 'Result request lost original key');
  check(body.expected_revision === 0 && body.parent_result_id === null, 'Empty Index CAS identity changed');
  check(JSON.stringify(body.binding) === JSON.stringify(f.binding), 'Result request changed exact Binding');
  check(!('canWrite' in body), 'UI callback leaked into request DTO');
}
async function record(name: string, action: (f: Fixture, t: Transport, mount: (ro?: boolean, disabled?: boolean) => Editor) => Promise<Record<string, unknown>>, holdPost = false) {
  const f = fixture(name), t = installTransport(f, holdPost);
  const context: { ui?: Editor } = {};
  let assertions: Record<string, unknown> | undefined, error: unknown;
  try {
    assertions = await action(f, t, (ro = false, disabled = false) => {
      check(!context.ui, 'A scenario must use one createRoot, never a replacement mount');
      context.ui = editor(f, ro, disabled); return context.ui;
    });
  } catch (caught) { error = caught; }
  // Product catch handlers must never turn an unexpected transport rejection into a passing case.
  try { await taskBoundary(); await t.finishHashes(); t.assertClean(); }
  catch (caught) { if (!error) error = caught; }
  const storage = sessionStorage.getItem(f.storageKey);
  result.cases.push({ name, status: error ? 'FAILED' : 'PASSED', evidence_kind: 'SYNTHETIC_TRANSPORT_NOT_ASGI',
    ...(error ? { error: error instanceof Error ? error.message : String(error) } : {}),
    request_id: f.requestId, storage_key: f.storageKey, timeline: [...t.events],
    unexpected_dispatches: [...t.unexpectedDispatches], readonly_write_checks: t.readonlyChecks(),
    stored: storage === null ? null : JSON.parse(storage), mount_phases: context.ui ? [...context.ui.phases] : [], assertions });
  context.ui?.dispose(); t.dispose(); show();
  // Stop on failure. Keep the closed transport installed; never expose late continuations to native fetch.
  if (error) throw error;
}

async function cases() {
  await record('readonly_pending', async (f, t, mount) => {
    const op = await seed(f, t), ui = mount(true), restore = await ui.settled();
    check(restore.disabled, 'Readonly pending recovery must be disabled');
    const seq = t.markReadOnly();
    flushSync(() => { restore.click(); ui.host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); });
    await taskBoundary();
    check(t.events.filter(e => e.kind === 'fetch-dispatch' && e.sequence > seq).length === 0, 'Readonly entry dispatched a request');
    check(t.nonGets(seq).length === 0, 'Readonly pending entry dispatched a non-GET');
    check(ui.host.querySelector<HTMLFieldSetElement>('.project-usage-fields')!.disabled, 'Readonly questions remain editable');
    assertOriginal(f, op, false);
    return { non_get_dispatches_after_readonly_commit: 0, post_dispatches_after_readonly_commit: 0, pending_key_preserved: true };
  });
  await record('readonly_changed_draft', async (f, t, mount) => {
    const ui = mount(); await taskBoundary();
    const commercial = ui.host.querySelector<HTMLInputElement>('input[name="project-usage-commercial"][value="true"]')!;
    flushSync(() => commercial.click());
    check(commercial.checked, 'Fresh form must have a real changed draft before testing the entry guard');
    ui.render(true); ui.assertSameInstance(true); const seq = t.markReadOnly();
    flushSync(() => ui.host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    await taskBoundary();
    check(t.nonGets(seq).length === 0, 'Readonly form dispatched a non-GET to any endpoint');
    check(sessionStorage.getItem(f.storageKey) === null && readPendingUsageUpdate(f.a) === null, 'Readonly form created an operation');
    return { changed_draft_before_readonly: true, non_get_dispatches_after_readonly_commit: 0, post_dispatches_after_readonly_commit: 0 };
  });
  await record('ordinary_disabled', async (f, t, mount) => {
    const op = await seed(f, t), ui = mount(false, true), restore = await ui.settled();
    check(!restore.disabled, 'Ordinary disabled incorrectly prevents explicit editable recovery');
    const recoverySeq = t.latestSequence();
    restore.click(); await bounded(t.indexEntered, 'editable Index dispatch');
    check(t.resultPosts().length === 0, 'Result POST occurred before Index release'); t.releaseIndex();
    await bounded(t.resultPostEntered, 'editable Result dispatch'); await ui.settled();
    assertResultIdentity(f, t); assertOriginal(f, op, true);
    check(t.assessmentPosts().length === 1, 'continueUsageUpdate re-submitted Assessment');
    check(t.nonGets(recoverySeq).length === 1 && t.posts(recoverySeq).length === 1, 'Editable recovery dispatched an extra write');
    return { result_post_dispatches: 1, assessment_post_dispatches_in_recovery: 0, server_receipt: null, completion: 'UNCONFIRMED' };
  });
  // TEST4 is the separate AST source check; TEST5 below is authoritative real ReactDOM evidence when run.
  await record('test5_dynamic', async (f, t, mount) => {
    const op = await seed(f, t), ui = mount(), restore = await ui.settled();
    restore.click(); await bounded(t.indexEntered, 'TEST5 Index dispatch');
    check(t.resultPosts().length === 0, 'TEST5 Result POST happened before release');
    ui.render(true); ui.assertSameInstance(true); const seq = t.markReadOnly(); t.releaseIndex();
    const retained = await ui.settled(); check(retained.disabled, 'Readonly action was not retained disabled');
    check(t.nonGets(seq).length === 0, 'TEST5: a new non-GET to any endpoint occurred after readonly commit');
    check(t.resultPosts().length === 0, 'TEST5: Result POST occurred');
    check(t.assessmentPosts().length === 1, 'TEST5 recovery repeated Assessment POST');
    assertOriginal(f, op, false);
    return { same_root_rerender: true, index_release_after_readonly_commit: true, non_get_dispatches_after_commit: 0, post_dispatches_after_commit: 0, original_key_preserved: true };
  });
  await record('revoked_not_revived', async (f, t, mount) => {
    const op = await seed(f, t), ui = mount(); (await ui.settled()).click();
    await bounded(t.indexEntered, 'monotonic Index dispatch');
    ui.render(true); const seq = t.markReadOnly(); ui.render(false); ui.assertSameInstance(false); t.releaseIndex();
    await ui.settled(); check(t.nonGets(seq).length === 0, 'Returning to writable revived an old permit or dispatched another non-GET');
    assertOriginal(f, op, false);
    return { old_permit_remains_revoked_after_writable_return: true, non_get_dispatches_after_commit: 0, post_dispatches_after_commit: 0 };
  });
  await record('post_already_sent', async (f, t, mount) => {
    const op = await seed(f, t), ui = mount(); (await ui.settled()).click();
    await bounded(t.indexEntered, 'sent-case Index dispatch'); t.releaseIndex();
    await bounded(t.resultPostEntered, 'POST already dispatched');
    check(t.resultPosts().length === 1, 'The sent-case prerequisite is missing');
    ui.render(true); ui.assertSameInstance(true); const seq = t.markReadOnly(); t.releaseWithheldPost();
    await ui.settled(); assertResultIdentity(f, t); assertOriginal(f, op, true);
    check(t.nonGets(seq).length === 0, 'Another non-GET to any endpoint was dispatched after readonly');
    return { result_post_dispatches_before_commit: 1, non_get_dispatches_after_commit: 0, post_dispatches_after_commit: 0, server_receipt: null, completion: 'UNCONFIRMED', cancellation_or_rollback_proven: false };
  }, true);
  await record('prepared_not_attempted', async (f, t, mount) => {
    const op = beginUsageUpdate(f.a, f.changed, f.requestId); let allowed = true;
    const flight = submitUsageUpdate(op, () => allowed); allowed = false; // Before real single() microtask.
    const value = await flight;
    check(value.canSubmitOriginal === true, 'Definitely-unsent operation did not expose explicit original-submit capability');
    check(t.nonGets().length === 0 && stored(f).assessmentAttempted === false, 'Revoked microtask dispatched a write or consumed an unsent attempt');
    assertOriginal(f, op, false);
    const ui = mount(); (await ui.settled()).click();
    const originalSave = await ui.settled('保存原请求');
    check(t.nonGets().length === 0, 'Ordinary continue unexpectedly dispatched a write');
    originalSave.click(); await bounded(t.assessmentPostEntered, 'explicit original Assessment dispatch');
    ui.render(true); ui.assertSameInstance(true); const seq = t.markReadOnly(); await ui.settled();
    check(t.nonGets(seq).length === 0, 'Prepared-case dispatched a new non-GET after readonly commit');
    check(t.assessmentPosts().length === 1 && stored(f).assessmentAttempted === true, 'Explicit original save did not dispatch exactly once');
    check(JSON.parse(t.assessmentPosts()[0].requestBody).request_id === op.requestId, 'Explicit save regenerated original request key');
    assertOriginal(f, op, false);
    return { initial_revoked_assessment_dispatches: 0, explicit_original_save_dispatches: 1, original_key_preserved: true, server_receipt: 'SYNTHETIC_202_PENDING_ONLY' };
  });
}

run.addEventListener('click', () => {
  if (result.status !== 'NOT_RUN') return;
  run.disabled = true; result.status = 'RUNNING'; show();
  void cases().then(() => { result.status = 'COMPLETED'; show(); }, () => { result.status = 'COMPLETED_WITH_FAILURES'; show(); });
});
