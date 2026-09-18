import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DIMENSIONS, hashFile, loadFirstRoundEffective, parseArgs, readJson, sha256, validateResolution, validateReview, writeJsonExclusive } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.packet || !args.review || !args.comparison || !args.resolution || !args.output) throw new Error("用法: node finalize-rereview.mjs --packet <包> --review <复标> --comparison <比较> --resolution <冲突复核> --output <最终快照>");
const [packetText, comparisonText] = await Promise.all([readFile(args.packet, "utf8"), readFile(args.comparison, "utf8")]);
const [packet, review, comparison, resolution] = await Promise.all([
  Promise.resolve(JSON.parse(packetText)), readJson(args.review), Promise.resolve(JSON.parse(comparisonText)), readJson(args.resolution)
]);
const reviewValidation = validateReview(packetText, packet, review, 72);
const errors = [...reviewValidation.errors, ...validateResolution(comparisonText, comparison, resolution)];
if (comparison.input_hashes?.packet_sha256 !== sha256(packetText)) errors.push("comparison 绑定的 packet 哈希不匹配。");
if (comparison.input_hashes?.rereview_sha256 !== await hashFile(args.review)) errors.push("comparison 绑定的复标回执哈希不匹配。");
if (resolution.reviewer_id !== review.reviewer.reviewer_id) errors.push("冲突复核 reviewer_id 必须与第二轮复标一致。");
const baseDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const firstRound = await loadFirstRoundEffective(baseDirectory);
for (const [key, value] of Object.entries(firstRound.hashes)) {
  if (comparison.input_hashes?.[key] !== value) errors.push(`comparison 绑定的 ${key} 不匹配。`);
}
const comparisonRecords = Object.fromEntries((comparison.records ?? []).map((record) => [record.record_id, record]));
for (const reviewRecord of review.records ?? []) {
  for (const dimension of DIMENSIONS) {
    const item = comparisonRecords[reviewRecord.record_id]?.dimensions?.find((candidate) => candidate.dimension === dimension);
    const expectedFirst = firstRound.values[reviewRecord.record_id]?.[dimension];
    const expectedSecond = reviewRecord.judgments?.[dimension];
    if (!item || item.first_round !== expectedFirst || item.second_round !== expectedSecond || item.agree !== (expectedFirst === expectedSecond)) errors.push(`${reviewRecord.record_id}:${dimension} comparison 未忠实反映两轮输入。`);
  }
}
if (errors.length) throw new Error(errors.join("\n"));
const reviewById = Object.fromEntries(review.records.map((record) => [record.record_id, record]));
const resolutionByKey = Object.fromEntries(resolution.records.map((item) => [`${item.record_id}:${item.dimension}`, item]));
const comparisonById = Object.fromEntries(comparison.records.map((record) => [record.record_id, record]));
const records = packet.records.map((packetRecord) => {
  const reviewRecord = reviewById[packetRecord.record_id];
  const finalJudgments = {};
  const finalRationales = {};
  for (const dimension of DIMENSIONS) {
    const difference = comparisonById[packetRecord.record_id].dimensions.find((item) => item.dimension === dimension);
    const resolutionItem = resolutionByKey[`${packetRecord.record_id}:${dimension}`];
    finalJudgments[dimension] = difference.agree ? reviewRecord.judgments[dimension] : resolutionItem.final_judgment;
    finalRationales[dimension] = difference.agree ? reviewRecord.rationales[dimension] : resolutionItem.decision_basis;
  }
  return {
    record_id: packetRecord.record_id,
    final_judgments: finalJudgments,
    final_rationales: finalRationales,
    evidence_locators: reviewRecord.evidence_locators,
    conflict_evidence_locators: Object.fromEntries(DIMENSIONS
      .filter((dimension) => !comparisonById[packetRecord.record_id].dimensions.find((item) => item.dimension === dimension).agree)
      .map((dimension) => [dimension, resolutionByKey[`${packetRecord.record_id}:${dimension}`].evidence_locators])),
    changed_during_conflict_resolution: comparisonById[packetRecord.record_id].needs_resolution
  };
});
const finalSnapshot = {
  schema_version: "openguard-single-human-finalized-review/0.1",
  status: "single_human_time_separated_rereview_finalized",
  batch_id: packet.batch_id,
  finalized_at: new Date().toISOString(),
  reviewer_count: 1,
  review_rounds: 2,
  reviewer_id: review.reviewer.reviewer_id,
  method: {
    name: "single-human-time-separated-blinded-rereview",
    minimum_cooling_hours: 72,
    prior_ai_exposure_disclosed: true,
    independent_second_human: false,
    exact_agreement_rate: comparison.summary.exact_agreement_rate,
    disagreements_resolved: comparison.summary.disagreements
  },
  input_hashes: {
    blind_packet_sha256: sha256(packetText),
    rereview_sha256: await hashFile(args.review),
    comparison_sha256: sha256(comparisonText),
    resolution_sha256: await hashFile(args.resolution),
    ...comparison.input_hashes
  },
  records,
  allowed_claim: "一名真人完成两阶段时间隔离复标，并对差异重新查证后冻结。",
  prohibited_claims: ["双人独立复核", "标注者间一致率", "AI是第二名真人", "许可证或授权已经自动通过"],
  limitations: [
    "复标人和首轮确认人为同一人，无法消除单人系统性偏差。",
    "首轮复核人曾接触AI初标和系统输出；冷却期只能降低记忆影响，不能形成真正独立性。",
    "本批是output_review，不是对Detector预测隐藏的benchmark_gold。"
  ]
};
const result = await writeJsonExclusive(args.output, finalSnapshot);
console.log(JSON.stringify({ output: result.destination, sha256: result.sha256, status: finalSnapshot.status, records: records.length, exact_agreement_rate: comparison.summary.exact_agreement_rate }));
