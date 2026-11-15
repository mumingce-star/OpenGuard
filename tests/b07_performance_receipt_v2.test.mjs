import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
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
    const second = receipt(2, "failure");
    second.environment.tools = Object.fromEntries(Object.entries(second.environment.tools).reverse());
    second.environment.memory.observed_peak_bytes = 1500;
    await writeFile(input, JSON.stringify([receipt(1, "success"), second]));
    execFileSync(process.execPath, [join(root, "benchmarks/b07-summarize-receipts.mjs"), "--input", input, "--output", output]);
    const summary = JSON.parse(await readFile(output, "utf8"));
    assert.equal(summary.failure_rate, 0.5);
    assert.equal(summary.coverage.expected_stage_observations, 10);
    assert.equal(summary.coverage.timed_stage_observations, 8);
    assert.equal(summary.coverage.rate, 0.8);
    assert.deepEqual(summary.error_classification, { syft_failed: 1 });
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test("B07 rejects duplicate runs and mixed groups before writing a summary", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "og-b07-v2-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const input = join(directory, "receipts.json");
  const first = receipt(1, "success");
  const cases = [
    ["repeat receipt", { ...receipt(2, "success"), receipt_id: first.receipt_id }, /receipt_id must be unique/],
    ["repeat run", { ...receipt(2, "success"), run_id: first.run_id }, /run_id must be unique/],
    ["missing run", { ...receipt(2, "success"), run_id: undefined }, /receipt: run_id/],
    ["non-string run", { ...receipt(2, "success"), run_id: ["run-2"] }, /receipt: run_id/],
    ["source", { ...receipt(2, "success"), source: { ...first.source, commit: "1".repeat(40) } }, /receipt sources must match/],
    ["input", { ...receipt(2, "success"), artifacts: { ...first.artifacts, input_sha256: "1".repeat(64) } }, /receipt inputs must match/],
    ["configuration", { ...receipt(2, "success"), artifacts: { ...first.artifacts, config_sha256: "1".repeat(64) } }, /receipt configurations must match/],
    ["tools", { ...receipt(2, "success"), environment: { ...first.environment, tools: { ...first.environment.tools, syft: "1.50.0" } } }, /receipt environments must match/],
  ];
  for (const [name, second, expected] of cases) {
    await t.test(name, async () => {
      const output = join(directory, `${name}.json`);
      await writeFile(input, JSON.stringify([first, second]));
      assert.throws(
        () => execFileSync(process.execPath, [join(root, "benchmarks/b07-summarize-receipts.mjs"), "--input", input, "--output", output], { stdio: "pipe" }),
        (error) => error.status === 1 && expected.test(error.stderr.toString()),
      );
      await assert.rejects(readFile(output), { code: "ENOENT" });
    });
  }
});
