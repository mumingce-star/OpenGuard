import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import { DIMENSIONS, hashFile, loadFirstRoundEffective, parseArgs, readJson, sha256, validateReview, writeJsonExclusive } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.packet || !args.review || !args.output) throw new Error("用法: node compare-rounds.mjs --packet <盲化包> --review <已提交回执> --output <比较结果>");
const packetText = await readFile(args.packet, "utf8");
const [packet, review] = await Promise.all([Promise.resolve(JSON.parse(packetText)), readJson(args.review)]);
const validation = validateReview(packetText, packet, review, 72);
if (validation.errors.length) throw new Error(`复标回执未通过校验：\n${validation.errors.join("\n")}`);
const baseDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const firstRound = await loadFirstRoundEffective(baseDirectory);
const secondById = Object.fromEntries(review.records.map((record) => [record.record_id, record]));
const perDimension = Object.fromEntries(DIMENSIONS.map((dimension) => [dimension, { agreements: 0, disagreements: 0 }]));
let agreements = 0;
let disagreements = 0;
const records = packet.records.map((packetRecord) => {
  const dimensions = DIMENSIONS.map((dimension) => {
    const first = firstRound.values[packetRecord.record_id][dimension];
    const second = secondById[packetRecord.record_id].judgments[dimension];
    const agree = first === second;
    perDimension[dimension][agree ? "agreements" : "disagreements"] += 1;
    if (agree) agreements += 1; else disagreements += 1;
    return { dimension, first_round: first, second_round: second, agree };
  });
  return { record_id: packetRecord.record_id, dimensions, needs_resolution: dimensions.some((item) => !item.agree) };
});
const comparison = {
  schema_version: "openguard-single-human-rereview-comparison/0.1",
  batch_id: packet.batch_id,
  created_at: new Date().toISOString(),
  method: "same-human-time-separated-exact-agreement",
  status: disagreements === 0 ? "no_conflicts" : "resolution_required",
  input_hashes: { ...firstRound.hashes, packet_sha256: sha256(packetText), rereview_sha256: await hashFile(args.review) },
  summary: {
    total_dimensions: agreements + disagreements,
    agreements,
    disagreements,
    exact_agreement_rate: agreements / (agreements + disagreements),
    per_dimension: perDimension
  },
  records,
  limitations: [
    "这是同一标注者的时间隔离一致率，不是标注者间一致率。",
    "差异不得按对Detector有利的方向自动解决；证据不足时必须保留uncertain。",
    "只有冲突复核完成并生成最终快照后，批次才可标记为single-human finalized。"
  ]
};
const result = await writeJsonExclusive(args.output, comparison);
console.log(JSON.stringify({ output: result.destination, sha256: result.sha256, ...comparison.summary }));
