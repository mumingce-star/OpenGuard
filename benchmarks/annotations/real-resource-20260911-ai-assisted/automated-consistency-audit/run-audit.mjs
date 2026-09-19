import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { auditBatch, sha256 } from "./audit-lib.mjs";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    if (!argv[index]?.startsWith("--") || argv[index + 1] === undefined) throw new Error(`无效参数：${argv[index] ?? "<empty>"}`);
    args[argv[index].slice(2)] = argv[index + 1];
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const toolDirectory = dirname(fileURLToPath(import.meta.url));
const baseDirectory = resolve(args.base ?? toolDirectory, args.base ? "." : "..");
if (!args.output) throw new Error("用法：node run-audit.mjs --output <新目录> [--base <批次目录>]");
const outputDirectory = resolve(args.output);
await mkdir(outputDirectory, { recursive: false });

const report = await auditBatch(baseDirectory);
const reportText = `${JSON.stringify(report, null, 2)}\n`;
const summaryText = `# 全自动标签一致性审计报告

## 结论

${report.summary.errors === 0 ? "PASS_WITH_KNOWN_LIMITATIONS" : "FAIL"}

状态：\`${report.status}\`

## 汇总

| 检查项 | 结果 |
| --- | ---: |
| 记录数 | ${report.summary.records} |
| 判断维度 | ${report.summary.dimensions} |
| 自动审计通过（带已知限制） | ${report.summary.automated_pass_with_known_limitations} |
| 隔离待未来真人复核 | ${report.summary.needs_future_human_review} |
| 错误 | ${report.summary.errors} |
| 警告 | ${report.summary.warnings} |

## 标签分布

\`\`\`json
${JSON.stringify(report.summary.effective_judgment_counts, null, 2)}
\`\`\`

## 召回率重算

\`\`\`json
${JSON.stringify(report.summary.recall_metrics_recomputed, null, 2)}
\`\`\`

## 已知限制

- 只有一名真人，且该真人看过 AI 初稿。
- 三份旧扫描附件和额外 Evidence 对象尚未直接恢复复核。
- 召回率 gold 由 AI 构建，当前没有真人 gold 审阅者。
- 自动审计只能验证结构、证据链和内部一致性，不能代替第二位真人或证明语义真值。

## 正式披露

${report.disclosure}
`;

const reportPath = resolve(outputDirectory, "audit-report.json");
const summaryPath = resolve(outputDirectory, "AUDIT_SUMMARY.md");
await writeFile(reportPath, reportText, { encoding: "utf8", flag: "wx" });
await writeFile(summaryPath, summaryText, { encoding: "utf8", flag: "wx" });
const outputHashes = {
  "AUDIT_SUMMARY.md": sha256(summaryText),
  "audit-report.json": sha256(reportText)
};
const chainMaterial = [
  ...Object.entries(report.input_sha256).map(([name, hash]) => `input:${name}:${hash}`),
  ...Object.entries(outputHashes).sort(([left], [right]) => left.localeCompare(right)).map(([name, hash]) => `output:${name}:${hash}`)
].join("\n");
const hashChain = {
  schema_version: "openguard-automated-label-audit-hash-chain/0.1",
  batch_id: report.batch_id,
  generated_at: report.generated_at,
  input_sha256: report.input_sha256,
  output_sha256: outputHashes,
  chain_root_sha256: sha256(chainMaterial),
  original_labels_modified: false
};
const chainPath = resolve(outputDirectory, "hash-chain.json");
await writeFile(chainPath, `${JSON.stringify(hashChain, null, 2)}\n`, { encoding: "utf8", flag: "wx" });

console.log(JSON.stringify({
  output: outputDirectory,
  status: report.status,
  records: report.summary.records,
  passed: report.summary.automated_pass_with_known_limitations,
  quarantined: report.summary.needs_future_human_review,
  errors: report.summary.errors,
  warnings: report.summary.warnings,
  chain_root_sha256: hashChain.chain_root_sha256
}));
if (report.summary.errors > 0) process.exitCode = 1;
