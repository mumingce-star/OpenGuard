import { readFile, writeFile } from "node:fs/promises";
import { REQUIRED_STAGES, validateControlledReceipt } from "./b07-controlled-receipt.mjs";

const args = process.argv.slice(2);
const value = (name) => {
  const index = args.indexOf(name);
  return index < 0 ? undefined : args[index + 1];
};
const input = value("--input"), output = value("--output");
if (!input || !output) throw new Error("usage: --input <controlled-receipts.json> --output <summary.json>");
const receipts = JSON.parse(await readFile(input, "utf8"));
if (!Array.isArray(receipts) || receipts.length < 2) throw new Error("at least two controlled Linux receipts are required; a single run is not a performance conclusion");
const percentile = (values, p) => { const sorted = [...values].sort((a,b) => a-b); return sorted[Math.ceil(sorted.length * p) - 1]; };
const durations = []; const stages = new Map(REQUIRED_STAGES.map((name) => [name, []])); const errorCounts = new Map(); const startup = { cold: [], warm: [] }; let failures = 0, timedStages = 0;
const receiptIds = new Set();
const runIds = new Set();
const environmentIdentity = ({ os, cpu, memory, tools }) => JSON.stringify([
  os.family, os.kernel, os.image_digest, cpu.model, cpu.logical_cores, memory.limit_bytes,
  tools.scancode, tools.syft, tools.static_detector, tools.rule_version,
]);
const sourceIdentity = ({ source_id, commit, source_sha256 }) => JSON.stringify([source_id, commit, source_sha256]);
const baseline = receipts[0];
for (const receipt of receipts) {
  const errors = validateControlledReceipt(receipt);
  if (errors.length) throw new Error(`invalid controlled Linux receipt: ${errors.join(",")}`);
  if (receiptIds.has(receipt.receipt_id)) throw new Error("receipt_id must be unique");
  if (runIds.has(receipt.run_id)) throw new Error("run_id must be unique");
  receiptIds.add(receipt.receipt_id);
  runIds.add(receipt.run_id);
  if (sourceIdentity(baseline.source) !== sourceIdentity(receipt.source)) throw new Error("receipt sources must match");
  if (baseline.artifacts.input_sha256 !== receipt.artifacts.input_sha256) throw new Error("receipt inputs must match");
  if (baseline.artifacts.config_sha256 !== receipt.artifacts.config_sha256) throw new Error("receipt configurations must match");
  if (environmentIdentity(baseline.environment) !== environmentIdentity(receipt.environment)) throw new Error("receipt environments must match");
  if (receipt.status !== "success") { failures++; for (const code of receipt.error_classification.errors) errorCounts.set(code, (errorCounts.get(code) ?? 0) + 1); }
  durations.push(receipt.total_duration_ms); startup[receipt.startup_mode].push(receipt.total_duration_ms);
  for (const stage of receipt.stages) if (stage.status !== "not_run") { timedStages++; stages.get(stage.name).push(stage.duration_ms); }
}
const metrics = (values) => values.length ? { p50: percentile(values,.5), p95: percentile(values,.95), sample_count: values.length } : null;
const summary = { schema: "openguard.b07.performance-summary/2", status: "descriptive_controlled_linux_receipts_not_formal_performance_benchmark", sample_count: receipts.length, successful_samples: receipts.length - failures, failure_rate: failures / receipts.length, coverage: { expected_stage_observations: receipts.length * REQUIRED_STAGES.length, timed_stage_observations: timedStages, rate: timedStages / (receipts.length * REQUIRED_STAGES.length) }, total_duration_ms: metrics(durations), startup_duration_ms: { cold: metrics(startup.cold), warm: metrics(startup.warm) }, stage_duration_ms: Object.fromEntries(REQUIRED_STAGES.map((name) => [name, metrics(stages.get(name))])), error_classification: Object.fromEntries([...errorCounts.entries()].sort(([a],[b]) => a.localeCompare(b))), environment_summary: baseline.environment, formal_performance_claimed: false };
await writeFile(output, `${JSON.stringify(summary, null, 2)}\n`, "utf8"); console.log(JSON.stringify(summary));
