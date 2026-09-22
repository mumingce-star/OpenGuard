import { readFile, writeFile } from "node:fs/promises";

const args = process.argv.slice(2); const value = (name) => args[args.indexOf(name) + 1];
const input = value("--input"), output = value("--output");
if (!input || !output) throw new Error("usage: --input <controlled-receipts.json> --output <summary.json>");
const receipts = JSON.parse(await readFile(input, "utf8"));
if (!Array.isArray(receipts) || receipts.length < 2) throw new Error("at least two controlled receipts are required; a single run is not a performance conclusion");
const percentile = (values, p) => { const sorted = [...values].sort((a,b) => a-b); return sorted[Math.ceil(sorted.length * p) - 1]; };
const durations = []; const stages = new Map(); let failures = 0; let environment = null;
for (const receipt of receipts) {
  if (receipt.schema !== "openguard.controlled-pipeline-receipt/1" || receipt.execution_mode !== "controlled" || receipt.production_scan_started === true) throw new Error("only controlled non-production receipts are accepted");
  if (!receipt.environment || typeof receipt.environment !== "object" || Array.isArray(receipt.environment)) throw new Error("environment summary is required for every receipt");
  if (!Number.isFinite(receipt.total_duration_ms) || receipt.total_duration_ms < 0) throw new Error("total duration is required for every receipt");
  if (!environment) environment = receipt.environment; else if (JSON.stringify(environment) !== JSON.stringify(receipt.environment)) throw new Error("receipt environments must match");
  if (receipt.status !== "success") failures++;
  durations.push(receipt.total_duration_ms);
  for (const stage of receipt.stages ?? []) { if (!Number.isFinite(stage.duration_ms)) throw new Error("stage duration missing"); const values = stages.get(stage.name) ?? []; values.push(stage.duration_ms); stages.set(stage.name, values); }
}
const summary = { schema: "openguard.b07.performance-summary/1", status: "descriptive_controlled_receipts_not_production_benchmark", sample_count: receipts.length, successful_samples: receipts.length - failures, failure_rate: failures / receipts.length, total_duration_ms: { p50: percentile(durations,.5), p95: percentile(durations,.95) }, stage_duration_ms: Object.fromEntries([...stages.entries()].sort(([a],[b]) => a.localeCompare(b)).map(([name, values]) => [name, { p50: percentile(values,.5), p95: percentile(values,.95) }])), environment_summary: environment, formal_performance_claimed: false };
await writeFile(output, `${JSON.stringify(summary, null, 2)}\n`, "utf8"); console.log(JSON.stringify(summary));
