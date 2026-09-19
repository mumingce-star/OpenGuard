import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { auditBatch, INPUT_FILES } from "./audit-lib.mjs";

const toolDirectory = dirname(fileURLToPath(import.meta.url));
const sourceDirectory = resolve(toolDirectory, "..");
const tempRoot = await mkdtemp(join(tmpdir(), "openguard-auto-audit-"));

async function fixture(name) {
  const directory = join(tempRoot, name);
  await cp(sourceDirectory, directory, {
    recursive: true,
    filter: (source) => !source.includes("automated-consistency-audit") && (source === sourceDirectory || INPUT_FILES.includes(source.split(/[\\/]/).at(-1)))
  });
  return directory;
}

async function edit(directory, filename, mutate) {
  const path = join(directory, filename);
  const value = JSON.parse(await readFile(path, "utf8"));
  mutate(value);
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

try {
  const clean = await auditBatch(sourceDirectory, "2026-09-18T08:40:00.000Z");
  assert.equal(clean.summary.errors, 0);
  assert.equal(clean.summary.records, 12);
  assert.equal(clean.summary.dimensions, 60);
  assert.equal(clean.summary.automated_pass_with_known_limitations, 12);
  assert.equal(clean.summary.needs_future_human_review, 0);
  assert.equal(clean.human_review_claim.independent_second_human, false);

  const labelDirectory = await fixture("bad-label-gate");
  await edit(labelDirectory, "ai-draft.json", (value) => { value.records[0].judgments.license.value = "correct"; });
  const badLabel = await auditBatch(labelDirectory);
  assert(badLabel.diagnostics.some((item) => item.code === "LICENSE_GATE_CONTRADICTION" && item.record_id === "R01"));
  assert.equal(badLabel.records[0].status, "needs_future_human_review");

  const sourceDirectoryBad = await fixture("bad-source-hash");
  await edit(sourceDirectoryBad, "source-reverification.json", (value) => { value.files[0].sha256 = "0".repeat(64); });
  const badSource = await auditBatch(sourceDirectoryBad);
  assert(badSource.diagnostics.some((item) => item.code === "SOURCE_HASH_MISMATCH" && item.record_id === "R01"));

  const confirmationDirectory = await fixture("missing-confirmation");
  await edit(confirmationDirectory, "human-confirmation.json", (value) => { value.records.pop(); });
  const missingConfirmation = await auditBatch(confirmationDirectory);
  assert(missingConfirmation.diagnostics.some((item) => item.code === "RECORD_SET_INVALID"));
  assert(missingConfirmation.diagnostics.some((item) => item.code === "HUMAN_RECORD_NOT_CONFIRMED" && item.record_id === "R12"));

  const manifestDirectory = await fixture("bad-manifest-counts");
  await edit(manifestDirectory, "manifest.json", (value) => { value.adjudicated_judgment_counts.risk.accept += 1; });
  const badManifest = await auditBatch(manifestDirectory);
  assert(badManifest.diagnostics.some((item) => item.code === "MANIFEST_COUNTS_MISMATCH"));

  const amendmentDirectory = await fixture("bad-amendment");
  await edit(amendmentDirectory, "human-amendment-r05.json", (value) => { value.judgments.risk = "accept"; });
  const badAmendment = await auditBatch(amendmentDirectory);
  assert(badAmendment.diagnostics.some((item) => item.code === "R05_ADJUDICATION_MISMATCH"));

  console.log(JSON.stringify({ valid: true, tests: 16, baseline_warnings: clean.summary.warnings }));
} finally {
  await rm(tempRoot, { recursive: true, force: true });
}
