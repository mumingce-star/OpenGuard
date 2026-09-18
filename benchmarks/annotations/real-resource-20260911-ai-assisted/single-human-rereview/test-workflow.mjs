import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DIMENSIONS, loadFirstRoundEffective, sha256 } from "./lib.mjs";

const toolDirectory = dirname(fileURLToPath(import.meta.url));
const baseDirectory = resolve(toolDirectory, "..");
const tempDirectory = await mkdtemp(join(tmpdir(), "openguard-single-rereview-"));
const paths = Object.fromEntries(["packet", "form", "short", "review", "comparison", "resolution", "tamperedComparison", "tamperedResolution", "tamperedFinal", "final"].map((name) => [name, join(tempDirectory, `${name}.json`)]));
const run = (script, args) => execFileSync(process.execPath, [resolve(toolDirectory, script), ...args], { encoding: "utf8", stdio: "pipe" });
const expectFailure = (script, args) => {
  let failed = false;
  try { run(script, args); } catch { failed = true; }
  assert.equal(failed, true, `${script} 应拒绝无效输入`);
};

try {
  run("prepare-rereview-packet.mjs", ["--output", paths.packet]);
  const packet = JSON.parse(await readFile(paths.packet, "utf8"));
  packet.generated_at = new Date(Date.now() - 80 * 3_600_000).toISOString();
  await writeFile(paths.packet, `${JSON.stringify(packet, null, 2)}\n`, "utf8");
  run("prepare-review-form.mjs", ["--packet", paths.packet, "--output", paths.form]);
  const forbiddenKeys = new Set(["judgments", "human_review_status", "issue_codes"]);
  const walk = (value) => {
    if (!value || typeof value !== "object") return;
    for (const [key, child] of Object.entries(value)) {
      assert.equal(forbiddenKeys.has(key), false, `盲化包泄露字段 ${key}`);
      walk(child);
    }
  };
  walk(packet);
  expectFailure("validate-rereview.mjs", ["--packet", paths.packet, "--review", paths.form]);
  const firstRound = await loadFirstRoundEffective(baseDirectory);
  const review = JSON.parse(await readFile(paths.form, "utf8"));
  const generatedAt = Date.parse(packet.generated_at);
  review.status = "submitted";
  review.reviewer.reviewer_id = "reviewer-self-test";
  for (const key of Object.keys(review.reviewer.attestation)) review.reviewer.attestation[key] = true;
  review.rereview_started_at = new Date(generatedAt + 73 * 3_600_000).toISOString();
  review.submitted_at = new Date(generatedAt + 75 * 3_600_000).toISOString();
  for (const record of review.records) {
    record.judgments = { ...firstRound.values[record.record_id] };
    record.rationales = Object.fromEntries(DIMENSIONS.map((dimension) => [dimension, `合成测试理由：${record.record_id} 的 ${dimension} 已按固定来源重新检查。`]));
    record.evidence_locators = [`synthetic-fixture:${record.record_id}:fixed-source-line`];
  }
  review.records[0].judgments.resource = "incorrect";
  await writeFile(paths.review, `${JSON.stringify(review, null, 2)}\n`, "utf8");
  const shortCooling = structuredClone(review);
  shortCooling.rereview_started_at = new Date(generatedAt + 3_600_000).toISOString();
  await writeFile(paths.short, `${JSON.stringify(shortCooling, null, 2)}\n`, "utf8");
  expectFailure("validate-rereview.mjs", ["--packet", paths.packet, "--review", paths.short]);
  run("validate-rereview.mjs", ["--packet", paths.packet, "--review", paths.review]);
  run("compare-rounds.mjs", ["--packet", paths.packet, "--review", paths.review, "--output", paths.comparison]);
  const comparison = JSON.parse(await readFile(paths.comparison, "utf8"));
  assert.equal(comparison.summary.total_dimensions, 60);
  assert.equal(comparison.summary.disagreements, 1);
  assert.equal(comparison.summary.exact_agreement_rate, 59 / 60);
  run("prepare-resolution.mjs", ["--comparison", paths.comparison, "--output", paths.resolution]);
  expectFailure("validate-resolution.mjs", ["--comparison", paths.comparison, "--resolution", paths.resolution]);
  const resolution = JSON.parse(await readFile(paths.resolution, "utf8"));
  resolution.status = "submitted";
  resolution.reviewer_id = review.reviewer.reviewer_id;
  resolution.submitted_at = new Date().toISOString();
  for (const key of Object.keys(resolution.attestation)) resolution.attestation[key] = true;
  resolution.records[0].final_judgment = "uncertain";
  resolution.records[0].decision_basis = "合成测试冲突仍缺少决定性证据，因此按保守规则保持不确定。";
  resolution.records[0].evidence_locators = ["synthetic-fixture:R01:conflict-source-line"];
  await writeFile(paths.resolution, `${JSON.stringify(resolution, null, 2)}\n`, "utf8");
  run("validate-resolution.mjs", ["--comparison", paths.comparison, "--resolution", paths.resolution]);
  const tamperedComparison = structuredClone(comparison);
  tamperedComparison.records[1].dimensions[0].first_round = "partially_correct";
  tamperedComparison.records[1].dimensions[0].second_round = "partially_correct";
  const tamperedComparisonText = `${JSON.stringify(tamperedComparison, null, 2)}\n`;
  await writeFile(paths.tamperedComparison, tamperedComparisonText, "utf8");
  const tamperedResolution = structuredClone(resolution);
  tamperedResolution.comparison_sha256 = sha256(tamperedComparisonText);
  await writeFile(paths.tamperedResolution, `${JSON.stringify(tamperedResolution, null, 2)}\n`, "utf8");
  expectFailure("finalize-rereview.mjs", ["--packet", paths.packet, "--review", paths.review, "--comparison", paths.tamperedComparison, "--resolution", paths.tamperedResolution, "--output", paths.tamperedFinal]);
  run("finalize-rereview.mjs", ["--packet", paths.packet, "--review", paths.review, "--comparison", paths.comparison, "--resolution", paths.resolution, "--output", paths.final]);
  const finalSnapshot = JSON.parse(await readFile(paths.final, "utf8"));
  assert.equal(finalSnapshot.status, "single_human_time_separated_rereview_finalized");
  assert.equal(finalSnapshot.reviewer_count, 1);
  assert.equal(finalSnapshot.records.length, 12);
  assert.equal(finalSnapshot.records[0].final_judgments.resource, "uncertain");
  console.log(JSON.stringify({ valid: true, tests: 14, disagreements: 1, exact_agreement_rate: 59 / 60 }));
} finally {
  await rm(tempDirectory, { recursive: true, force: true });
}
