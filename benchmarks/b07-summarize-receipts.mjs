import { readFile, writeFile } from "node:fs/promises";
import { REQUIRED_STAGES, validateControlledReceipt } from "./b07-controlled-receipt.mjs";

const args = process.argv.slice(2); const value = (name) => args[args.indexOf(name) + 1];
const input = value("--input"), output = value("--output");
if (!input || !output) throw new Error("usage: --input <controlled-receipts.json> --output <summary.json>");
const receipts = JSON.parse(await readFile(input, "utf8"));
if (!Array.isArray(receipts) || receipts.length < 2) throw new Error("at least two controlled Linux receipts are required; a single run is not a performance conclusion");
const percentile = (values, p) => { const sorted = [...values].sort((a,b) => a-b); return sorted[Math.ceil(sorted.length * p) - 1]; };
const durations = []; const stages = new Map(REQUIRED_STAGES.map((name) => [name, []])); const errorCounts = new Map(); const startup = { cold: [], warm: [] }; let failures = 0, timedStages = 0; let environment = null;
const receiptIds = new Set();
const environmentIdentity = (value) => JSON.stringify({ os: value.os, cpu: value.cpu, memory: { limit_bytes: value.memory.limit_bytes }, tools: value.tools });
for (const receipt of receipts) {
  const errors = validateControlledReceipt(receipt);
  if (errors.length) throw new Error(`invalid controlled Linux receipt: ${errors.join(",")}`);
  if (receiptIds.has(receipt.receipt_id)) throw new Error("receipt_id must be unique");
  receiptIds.add(receipt.receipt_id);
  if (!environment) environment = receipt.environment; else if (environmentIdentity(environment) !== environmentIdentity(receipt.environment)) throw new Error("receipt environments must match");
  if (receipt.status !== "success") { failures++; for (const code of receipt.error_classification.errors) errorCounts.set(code, (errorCounts.get(code) ?? 0) + 1); }
  durations.push(receipt.total_duration_ms); startup[receipt.startup_mode].push(receipt.total_duration_ms);
  for (const stage of receipt.stages) if (stage.status !== "not_run") { timedStages++; stages.get(stage.name).push(stage.duration_ms); }
}
const metrics = (values) => values.length ? { p50: percentile(values,.5), p95: percentile(values,.95), sample_count: values.length } : null;
const summary = { schema: "openguard.b07.performance-summary/2", status: "descriptive_controlled_linux_receipts_not_formal_performance_benchmark", sample_count: receipts.length, successful_samples: receipts.length - failures, failure_rate: failures / receipts.length, coverage: { expected_stage_observations: receipts.length * REQUIRED_STAGES.length, timed_stage_observations: timedStages, rate: timedStages / (receipts.length * REQUIRED_STAGES.length) }, total_duration_ms: metrics(durations), startup_duration_ms: { cold: metrics(startup.cold), warm: metrics(startup.warm) }, stage_duration_ms: Object.fromEntries(REQUIRED_STAGES.map((name) => [name, metrics(stages.get(name))])), error_classification: Object.fromEntries([...errorCounts.entries()].sort(([a],[b]) => a.localeCompare(b))), environment_summary: environment, formal_performance_claimed: false };
await writeFile(output, `${JSON.stringify(summary, null, 2)}\n`, "utf8"); console.log(JSON.stringify(summary));
