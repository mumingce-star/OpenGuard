import { materialFixture, FILE_BYTES, FILE_SHA256, SOURCE_DESCRIPTION, flatBinding, indexFor, reviewFor } from '../../../p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend/tests/material-async-readonly/fixture';
import type { Bundle } from '../../../p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend/tests/bound-advice-maincard/fixture';

/** SYNTHETIC_TEST_ONLY. Reuse frozen fixture helpers without editing or copying
 * any of the 24 frozen sources. This has no real business object or LICENSE. */
export { FILE_BYTES, FILE_SHA256, SOURCE_DESCRIPTION, flatBinding, indexFor, reviewFor };
export function sentReceiptFixture(label: string) {
  const f = materialFixture('sent_receipt_' + label);
  // The frozen helper's two alternate r2 shapes share an ID. This NEW fixture
  // separates the accepted material receipt from the unrelated alternate r2,
  // so exact GET routing cannot return the wrong object under a shared ID.
  f.saved.result_id += '_material_saved';
  f.saved.companion_summary_id += '_material_saved';
  f.saved.result_sha256 = '0'.repeat(64);
  f.receipt.result = f.saved;
  const concurrent = structuredClone(f.saved);
  concurrent.result_id += '_concurrent_r3'; concurrent.revision = 3;
  concurrent.previous_result_id = f.saved.result_id;
  concurrent.companion_summary_id += '_concurrent_r3'; concurrent.result_sha256 = '1'.repeat(64);
  const bindingChanged: Bundle = structuredClone(f.base);
  // Same Assessment identity with a different complete Binding AND distinct
  // fixed Result identities. This closed structural reload challenge does not
  // pretend an immutable Result ID can acquire different Binding/content.
  // It cannot independently isolate a Binding-only same-ID transition.
  bindingChanged.binding.registry_revision++;
  for (const r of [bindingChanged.result, bindingChanged.newer]) {
    r.binding = { ...bindingChanged.binding }; r.result_id += '_registry_changed';
    r.companion_summary_id += '_registry_changed';
    r.result_sha256 = (r.revision === 1 ? '2' : '3').repeat(64);
  }
  bindingChanged.newer.previous_result_id = bindingChanged.result.result_id;
  bindingChanged.review.result_id = bindingChanged.result.result_id;
  bindingChanged.review.result_sha256 = bindingChanged.result.result_sha256;
  bindingChanged.review.binding = { ...bindingChanged.binding };
  bindingChanged.summary.result_id = bindingChanged.result.result_id;
  bindingChanged.summary.summary_id = bindingChanged.result.companion_summary_id;
  bindingChanged.summary.result_sha256 = bindingChanged.result.result_sha256;
  bindingChanged.summary.binding = { ...bindingChanged.binding };
  // Repeated hexadecimal hashes here remain explicit synthetic DTO markers,
  // not independently computed production Result self-hashes/attestations.
  return { ...f, concurrent, bindingChanged };
}
export type Fixture = ReturnType<typeof sentReceiptFixture>;
export type View = 'A' | 'B' | 'A_OTHER_RESULT' | 'A_OTHER_BINDING';
