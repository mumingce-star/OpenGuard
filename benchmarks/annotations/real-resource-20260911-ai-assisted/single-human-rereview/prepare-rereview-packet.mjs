import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs, readJson, validatePacket, writeJsonExclusive } from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
if (!args.output) throw new Error("用法: node prepare-rereview-packet.mjs --output <隔离目录中的JSON路径>");
const toolDirectory = dirname(fileURLToPath(import.meta.url));
const baseDirectory = resolve(toolDirectory, "..");
const [draft, sourceReverification] = await Promise.all([
  readJson(resolve(baseDirectory, "ai-draft.json")),
  readJson(resolve(baseDirectory, "source-reverification.json"))
]);
if (sourceReverification.result !== "verified" || sourceReverification.records_verified !== 12) throw new Error("固定来源复核状态不是 12/12 verified，拒绝生成复标包。");
const verifiedSourceHashes = {};
for (const file of sourceReverification.files ?? []) {
  for (const recordId of file.records ?? []) verifiedSourceHashes[recordId] = file.sha256;
}
for (const record of draft.records) {
  if (verifiedSourceHashes[record.record_id] !== record.source.reported_source_sha256) throw new Error(`${record.record_id} 的来源哈希未通过固定来源回执绑定。`);
}
const packet = {
  schema_version: "openguard-single-human-rereview-packet/0.1",
  batch_id: draft.batch_id,
  purpose: "output_review",
  generated_at: new Date().toISOString(),
  minimum_cooling_hours: 72,
  disclosure: "单人第二轮时间隔离复标包。包含待评价的系统断言，不包含首轮标签、首轮理由、问题代码、AI复审结论或R05修订答案。",
  limitations: [
    "同一真人曾看过AI初标和系统输出，因此本流程不是第二位独立真人复核。",
    "本包用于output_review；不得作为隐藏预测的benchmark_gold盲标包。",
    "复标期间不得打开同批次的ai-draft、human-confirmation、human-amendment或second-ai-review。"
  ],
  records: draft.records.map((record) => ({
    record_id: record.record_id,
    assertion: {
      name: record.name,
      resource_type: record.resource_type,
      version: record.version,
      version_status: record.version_status,
      usage_context: record.usage_context,
      fact: record.fact,
      proposed_license_expression: record.proposed_license_expression,
      risk_outcome: record.system_snapshot?.outcome ?? null,
      risk_severity: record.system_snapshot?.severity ?? null,
      recommended_action: record.recommended_action
    },
    source: {
      scan_id: record.source.scan_id,
      target_id: record.source.resource_id,
      risk_id: record.source.risk_id,
      primary_evidence_id: record.source.primary_evidence_id,
      source_url: record.source.source_url,
      source_revision: record.source.source_revision,
      primary_locator: record.source.primary_locator,
      reported_source_sha256: record.source.reported_source_sha256,
      original_scan_status: record.source.original_scan_status
    }
  }))
};
const errors = validatePacket(packet);
if (errors.length) throw new Error(errors.join("\n"));
const result = await writeJsonExclusive(args.output, packet);
console.log(JSON.stringify({ output: result.destination, sha256: result.sha256, records: packet.records.length, minimum_cooling_hours: 72 }));
