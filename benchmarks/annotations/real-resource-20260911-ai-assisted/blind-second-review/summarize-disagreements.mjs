import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

const args = process.argv.slice(2);
const value = (name) => args[args.indexOf(name) + 1];
const firstPath = value("--first"), secondPath = value("--second"), outputPath = value("--output");
if (!firstPath || !secondPath || !outputPath) throw new Error("usage: --first <review> --second <review> --output <summary>");
const [firstText, secondText] = await Promise.all([readFile(firstPath, "utf8"), readFile(secondPath, "utf8")]);
const [first, second] = [JSON.parse(firstText), JSON.parse(secondText)];
if (first.reviewer?.type !== "human" || second.reviewer?.type !== "human" || !first.reviewer?.reviewer_id || !second.reviewer?.reviewer_id || first.reviewer.reviewer_id === second.reviewer.reviewer_id) throw new Error("two distinct human reviewers are required");
const attestation = second.reviewer?.independence_attestation;
for (const key of ["independent_from_first_reviewer", "has_not_seen_ai_draft", "has_not_seen_first_human_decision", "has_not_seen_r05_amendment", "has_not_seen_second_ai_review"]) if (attestation?.[key] !== true) throw new Error("second reviewer must provide a complete blind-review independence attestation");
const dimensions = ["resource", "evidence", "license", "risk", "suggestion"];
const right = new Map((second.records ?? []).map((record) => [record.record_id, record]));
const disagreements = [];
let total = 0;
for (const record of first.records ?? []) {
  const other = right.get(record.record_id); if (!other) throw new Error(`missing second review record: ${record.record_id}`);
  for (const dimension of dimensions) { total++; if (record.judgments?.[dimension] !== other.judgments?.[dimension]) disagreements.push({ record_id: record.record_id, dimension, first: record.judgments?.[dimension], second: other.judgments?.[dimension], status: "pending_human_adjudication" }); }
}
if (right.size !== (first.records ?? []).length) throw new Error("review record sets differ");
const summary = { schema_version: "openguard-b06-disagreement-summary/1", status: "not_gold_pending_human_adjudication", first_review_sha256: createHash("sha256").update(firstText).digest("hex"), second_review_sha256: createHash("sha256").update(secondText).digest("hex"), reviewer_ids: [first.reviewer.reviewer_id, second.reviewer.reviewer_id].sort(), dimensions_total: total, disagreements, agreement_rate: total ? (total - disagreements.length) / total : null, gold_frozen: false };
await writeFile(outputPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ valid: true, disagreements: disagreements.length, gold_frozen: false }));
