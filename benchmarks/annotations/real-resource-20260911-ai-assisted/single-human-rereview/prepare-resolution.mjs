import { readFile } from "node:fs/promises";
import { parseArgs, sha256, validateComparison, writeJsonExclusive } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.comparison || !args.output) throw new Error("用法: node prepare-resolution.mjs --comparison <比较结果> --output <冲突复核模板>");
const comparisonText = await readFile(args.comparison, "utf8");
const comparison = JSON.parse(comparisonText);
const errors = validateComparison(comparison);
if (errors.length) throw new Error(errors.join("\n"));
const records = comparison.records.flatMap((record) => record.dimensions
  .filter((item) => !item.agree)
  .map((item) => ({
    record_id: record.record_id,
    dimension: item.dimension,
    first_round: item.first_round,
    second_round: item.second_round,
    final_judgment: null,
    decision_basis: null,
    evidence_locators: []
  })));
const resolution = {
  schema_version: "openguard-single-human-rereview-resolution/0.1",
  status: "draft",
  batch_id: comparison.batch_id,
  comparison_sha256: sha256(comparisonText),
  reviewer_id: null,
  submitted_at: null,
  attestation: {
    reopened_primary_sources: null,
    did_not_optimize_for_detector_metrics: null,
    unresolved_defaults_to_uncertain: null,
    understands_same_human_resolution: null
  },
  records
};
const result = await writeJsonExclusive(args.output, resolution);
console.log(JSON.stringify({ output: result.destination, sha256: result.sha256, conflicts: records.length }));
