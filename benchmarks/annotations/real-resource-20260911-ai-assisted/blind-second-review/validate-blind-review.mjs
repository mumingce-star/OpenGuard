import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";

const args = process.argv.slice(2);
const option = (name) => args[args.indexOf(name) + 1];
const packetPath = option("--packet");
const reviewPath = option("--review");
if (!packetPath || !reviewPath) throw new Error("用法: node validate-blind-review.mjs --packet <盲审包> --review <回执>");

const packetText = await readFile(packetPath, "utf8");
const [packet, review] = await Promise.all([Promise.resolve(JSON.parse(packetText)), readFile(reviewPath, "utf8").then(JSON.parse)]);
const errors = [];
const expectedIds = packet.records.map((item) => item.record_id);
const actualIds = review.records?.map((item) => item.record_id) ?? [];
const sameSet = expectedIds.length === actualIds.length && new Set(expectedIds).size === expectedIds.length && expectedIds.every((id) => actualIds.filter((value) => value === id).length === 1);
if (!sameSet) errors.push("回执必须与盲审包中的 R01-R12 一一对应，且不得重复或缺失。");
if (review.status !== "submitted") errors.push("回执状态必须为 submitted。");
if (review.reviewer?.type !== "human" || !String(review.reviewer?.reviewer_id ?? "").trim()) errors.push("必须声明非空的人类评审匿名 ID。");
for (const [key, value] of Object.entries(review.reviewer?.independence_attestation ?? {})) if (value !== true) errors.push(`独立性声明 ${key} 必须为 true。`);
for (const key of ["independent_from_first_reviewer", "has_not_seen_ai_draft", "has_not_seen_first_human_decision", "has_not_seen_r05_amendment", "has_not_seen_second_ai_review"]) if (review.reviewer?.independence_attestation?.[key] !== true) errors.push(`缺少或拒绝独立性声明：${key}。`);
const expectedHash = createHash("sha256").update(packetText).digest("hex");
if (review.blind_packet_sha256 !== expectedHash) errors.push("blind_packet_sha256 与实际盲审包不匹配。");
const values = {
  resource: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  evidence: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  license: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  risk: new Set(["accept", "revise", "reject", "uncertain", "not_applicable"]),
  suggestion: new Set(["actionable", "too_generic", "incorrect", "uncertain", "not_applicable"])
};
for (const record of review.records ?? []) {
  for (const [dimension, allowed] of Object.entries(values)) if (!allowed.has(record.judgments?.[dimension])) errors.push(`${record.record_id}.${dimension} 必须填写合法值。`);
  if (!String(record.reason ?? "").trim()) errors.push(`${record.record_id} 必须填写判断理由。`);
  if (!String(record.evidence_locator ?? "").trim()) errors.push(`${record.record_id} 必须填写证据定位或无法定位的原因。`);
}
if (!String(review.submitted_at ?? "").trim()) errors.push("必须填写 submitted_at。");
console.log(JSON.stringify({ valid: errors.length === 0, errors, packet_sha256: expectedHash, records: actualIds.length }, null, 2));
process.exitCode = errors.length ? 1 : 0;
