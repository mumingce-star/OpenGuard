import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

const root = resolve(new URL("..", import.meta.url).pathname.slice(1));
const stageNames = ["unpack", "scancode", "syft", "static_detector", "rule_consolidation"];
const receipt = (id, status) => ({
  schema: "openguard.controlled-pipeline-receipt/2", execution_mode: "controlled_linux",
  production_scan_started: false, startup_mode: id === 1 ? "cold" : "warm",
  receipt_id: `receipt-${id}`, run_id: `run-${id}`,
  source: { source_id: "source-1", commit: "a".repeat(40), source_sha256: "b".repeat(64) },
  artifacts: { input_sha256: "c".repeat(64), config_sha256: "d".repeat(64), result_sha256: "e".repeat(64) },
  status, error_classification: status === "success" ? { status: "not_observed", errors: [] } : { status: "observed", errors: ["syft_failed"] },
  total_duration_ms: id * 10,
  environment: { os: { family: "linux", kernel: "6.8", image_digest: `sha256:${"f".repeat(64)}` }, cpu: { model: "cpu", logical_cores: 2 }, memory: { limit_bytes: 2048, observed_peak_bytes: 1024 }, tools: { scancode: "32.5.0", syft: "1.51.0", static_detector: "0.3.0", rule_version: "r1" } },
  stages: stageNames.map((name, index) => ({ name, duration_ms: status === "failure" && index > 2 ? 0 : id, status: status === "failure" && index === 2 ? "failed" : status === "failure" && index > 2 ? "not_run" : "completed", failure_reason: status === "failure" && index === 2 ? "syft_failed" : null })),
});

test("B07 retains failed samples and reports stage coverage separately", async () => {
  const directory = await mkdtemp(join(tmpdir(), "og-b07-v2-"));
  try {
    const input = join(directory, "receipts.json"), output = join(directory, "summary.json");
    await writeFile(input, JSON.stringify([receipt(1, "success"), receipt(2, "failure")]));
    execFileSync(process.execPath, [join(root, "benchmarks/b07-summarize-receipts.mjs"), "--input", input, "--output", output]);
    const summary = JSON.parse(await readFile(output, "utf8"));
    assert.equal(summary.failure_rate, 0.5);
    assert.equal(summary.coverage.expected_stage_observations, 10);
    assert.equal(summary.coverage.timed_stage_observations, 8);
    assert.equal(summary.coverage.rate, 0.8);
    assert.deepEqual(summary.error_classification, { syft_failed: 1 });
  } finally { await rm(directory, { recursive: true, force: true }); }
});
