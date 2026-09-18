import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const [outputPath] = process.argv.slice(2);
if (!outputPath) {
  throw new Error("用法: node prepare-blind-packet.mjs <安全输出路径>");
}

const draftPath = new URL("../ai-draft.json", import.meta.url);
const draft = JSON.parse(await readFile(draftPath, "utf8"));
const packet = {
  schema_version: "openguard-second-human-blind-packet/0.1",
  batch_id: draft.batch_id,
  generated_at: new Date().toISOString(),
  disclosure: "仅包含待评估断言、行动建议和固定原文入口；不包含任何既有五维判断、理由、问题代码、首位真人裁决或 R05 修订。",
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
      source_url: record.source.source_url,
      source_revision: record.source.source_revision,
      primary_locator: record.source.primary_locator,
      reported_source_sha256: record.source.reported_source_sha256,
      original_scan_status: record.source.original_scan_status
    }
  }))
};
const serialized = `${JSON.stringify(packet, null, 2)}\n`;
await writeFile(resolve(outputPath), serialized, { encoding: "utf8", flag: "wx" });
console.log(JSON.stringify({ output: resolve(outputPath), sha256: createHash("sha256").update(serialized).digest("hex"), records: packet.records.length }));
