import type { Scan, Risk, Resource, Severity } from "../types/domain";
export const severityOrder: Severity[] = ["critical", "high", "medium", "low", "info"];

const zhCnText: Record<string, string> = {
  "License evidence requires verification": "许可证证据需要核验",
  "License evidence is unavailable": "缺少可用的许可证证据",
  "License or supporting evidence is pending verification":
    "许可证或佐证材料尚待核验",
  "No supporting evidence is available for the linked license":
    "关联许可证缺少可用的佐证材料",
  "No rule for normalized license": "标准化许可证暂无匹配规则",
  "No loaded rule matches the verified normalized license identifier":
    "已加载规则中没有与已核验许可证标识匹配的规则",
  "This is an evidence-based compliance reminder, not legal advice. Review the license text and the intended distribution before acting.":
    "这是基于证据的合规提示，不构成法律意见。采取行动前，请核对许可证原文和预期分发方式。",
  "License declaration requires review": "许可证声明需要复核",
  "Declaration is not verified authorization": "该声明尚未经过授权核验",
  "Review license": "复核许可证",
  "Check source": "核对来源",
  "AI remediation response was rejected.": "AI 整改建议未通过校验。",
  "A license evidence verification is pending. Action required to confirm or provide a valid license statement before deployment or distribution.":
    "许可证证据尚待核验。部署或分发前，需要确认或提供有效的许可证声明。",
  "License evidence is pending verification. Manual review of the file and its license content is required before any action is taken.":
    "许可证证据尚待核验。采取任何行动前，需要人工复核该文件及其许可证内容。",
  "License evidence is present but pending full verification. Manual review is required to confirm compliance.":
    "已发现许可证证据，但尚未完成核验。需要人工复核以确认合规情况。",
  "A license evidence verification is pending. Action required to confirm or provide license information before distribution or release.":
    "许可证证据尚待核验。分发或发布前，需要确认或补充许可证信息。",
  "A license evidence verification is required. The current evidence shows a pending license with no assertion. Manual review of the file and use context is necessary before any action is taken.":
    "需要核验许可证证据。当前证据显示许可证尚待确认且没有明确声明；采取任何行动前，需要人工复核文件及使用场景。",
  "License evidence is present but verification status is pending. Manual review is required to assess compliance and determine next steps.":
    "已发现许可证证据，但核验状态仍为待处理。需要人工复核合规情况并确定后续措施。",
  "Document the review outcome and update the manifest if necessary to include verified license information.":
    "记录复核结果；如有必要，更新依赖清单并补充已核验的许可证信息。",
  "Ensure compliance with organizational policies regarding open-source license usage.":
    "确认开源许可证的使用符合组织政策。",
  "Ensure the license is clearly documented and distributed as part of the software distribution.":
    "确保许可证已被清晰记录，并随软件一同分发。",
  "Confirm that the intended distribution and use case are clearly defined before proceeding with deployment or release.":
    "在部署或发布前，明确预期分发方式和使用场景。",
  "Ensure compliance with organizational policies before deploying or distributing the component.":
    "部署或分发该组件前，确认符合组织政策。",
  "Confirm whether the license text or supporting documentation is available and properly included in the repository.":
    "确认许可证原文或佐证文档是否可用，并已正确纳入仓库。",
  "Document the review outcome and update the license evidence if necessary.":
    "记录复核结果，并在必要时更新许可证证据。",
  "If no license is intended or the use case is non-commercial, document the rationale for not asserting a license.":
    "如果未指定许可证或用途为非商业用途，请记录未声明许可证的理由。",
  "Verify the content hash of the detected tool output to ensure integrity and authenticity.":
    "核对检测工具输出的内容摘要，以确认其完整性和真实性。",
  "Verify the content hash of the evidence to ensure integrity and authenticity of the detected artifact.":
    "核对证据的内容摘要，以确认检测结果的完整性和真实性。",
};

const zhCnSentencePatterns: [RegExp, string][] = [
  [
    /A license evidence verification is required for '([^']+)' in the (.+?) file\./g,
    "需要核验 $2 文件中“$1”的许可证证据。",
  ],
  [
    /The license expression is currently marked as '([^']+)' with pending verification\./g,
    "当前许可证表达式为“$1”，状态为待核验。",
  ],
  [
    /Manual review is needed before any action is taken\./g,
    "采取任何行动前需要人工复核。",
  ],
  [
    /Document the license source and verification result before distribution\./g,
    "分发前请记录许可证来源和核验结果。",
  ],
  [
    /Review the license text and the intended distribution before acting\./g,
    "采取行动前，请核对许可证原文和预期分发方式。",
  ],
  [
    /License evidence is pending verification; manual review of the '([^']+)' license is required before any action is taken\./g,
    "“$1”的许可证证据尚待核验；采取任何行动前需要人工复核。",
  ],
  [
    /Check the license expression '([^']+)' to understand the legal implications and whether it meets compliance requirements\./g,
    "检查许可证表达式“$1”，了解其法律影响以及是否满足合规要求。",
  ],
  [
    /Check the license expression '([^']+)' to understand the implications for distribution and usage\./g,
    "检查许可证表达式“$1”，了解其对分发和使用的影响。",
  ],
  [
    /Ensure the license expression '([^']+)' is properly contextualized and that no distribution or usage conditions are missing\./g,
    "确认许可证表达式“$1”的适用场景清晰，且没有遗漏分发或使用条件。",
  ],
  [
    /If no license is present or the evidence is incomplete, update the repository with a proper license file or reference\./g,
    "如果缺少许可证或证据不完整，请在仓库中补充适当的许可证文件或引用。",
  ],
  [
    /If no license is present or evidence is missing, add a clear license file or reference to the appropriate open-source license\./g,
    "如果缺少许可证或相关证据，请补充明确的许可证文件或适当的开源许可证引用。",
  ],
  [
    /Review the license evidence in the (.+?) file to confirm the presence of a valid license statement\./g,
    "复核 $1 文件中的许可证证据，确认是否存在有效的许可证声明。",
  ],
  [
    /Review the license evidence in the file (.+?) to confirm the presence of a valid license statement\./g,
    "复核文件 $1 中的许可证证据，确认是否存在有效的许可证声明。",
  ],
  [
    /Update the verification status to 'verified' only after confirming the license and its implications for the intended use\./g,
    "仅在确认许可证及其对预期用途的影响后，才将核验状态更新为“已核验”。",
  ],
  [
    /Verify the content hash \((sha256: [a-f0-9]+)\) matches the actual content of the file\./g,
    "核对内容摘要（$1）是否与文件实际内容一致。",
  ],
  [
    /Confirm the intended distribution and usage context of the ([^ ]+) component\./g,
    "确认 $1 组件的预期分发和使用场景。",
  ],
  [
    /Confirm the intended distribution and usage scenario of the '([^']+)' package\./g,
    "确认“$1”软件包的预期分发和使用场景。",
  ],
  [
    /Review the license text associated with '([^']+)' in the (.+?) file\./g,
    "复核 $2 文件中与“$1”关联的许可证原文。",
  ],
  [
    /Verify the license evidence by checking the provided content hash and source details\./g,
    "通过核对所提供的内容摘要和来源详情来验证许可证证据。",
  ],
  [
    /Verify the license evidence by checking the content hash and source of the license file\./g,
    "通过核对许可证文件的内容摘要和来源来验证许可证证据。",
  ],
  [
    /Verify the license expression '([^']+)' and confirm its applicability to the intended distribution\./g,
    "核对许可证表达式“$1”，并确认其是否适用于预期分发方式。",
  ],
  [
    /Confirm the license expression '([^']+)' is appropriate for the intended distribution and use case\./g,
    "确认许可证表达式“$1”适用于预期分发方式和使用场景。",
  ],
  [
    /Update the compliance record to reflect the verification status as 'verified' or 'reviewed' based on the assessment\./g,
    "根据评估结果更新合规记录，将核验状态标记为“已核验”或“已复核”。",
  ],
  [
    /Review the license expression '([^']+)' in the context of the '([^']+)' component\./g,
    "结合“$2”组件的使用场景复核许可证表达式“$1”。",
  ],
  [
    /Verify the content hash of the license evidence matches the detected value to ensure integrity\./g,
    "核对许可证证据的内容摘要是否与检测值一致，以确认其完整性。",
  ],
];

export function localizeDisplayText(value?: string | null): string | null {
  if (value === null || value === undefined) return null;
  return value
    .split("\n")
    .map((line) => {
      const exact = zhCnText[line.trim()];
      if (exact) return line.replace(line.trim(), exact);
      return zhCnSentencePatterns.reduce(
        (translated, [pattern, replacement]) =>
          translated.replace(pattern, replacement),
        line,
      );
    })
    .join("\n");
}

export function licenseDisplay(value?: string | null): string {
  if (!value) return "许可证未知";
  return value === "NOASSERTION" ? "待核验（NOASSERTION）" : value;
}

export function evidenceSourceLabel(value: string): string {
  const labels: Record<string, string> = {
    manifest_parser: "依赖清单解析器（manifest_parser）",
    scancode: "ScanCode 扫描器",
    syft: "Syft 扫描器",
    static_pattern: "静态模式检测器（static_pattern）",
    ast: "语法树分析器（ast）",
    manual: "人工录入（manual）",
    ai_candidate: "AI 候选识别（ai_candidate）",
  };
  return labels[value] ?? value;
}
export function summarize(scan: Scan) {
  return {
    resources: scan.resources.length,
    risks: scan.risks.length,
    pending: scan.risks.filter((r) => r.handling !== "resolved").length,
    high: scan.risks.filter(
      (r) => r.severity === "high" || r.severity === "critical",
    ).length,
    unknown: scan.resources.filter((r) => r.licenseStatus !== "confirmed")
      .length,
  };
}
export function filterRisks(scan: Scan, params: URLSearchParams): Risk[] {
  const q = (params.get("q") ?? "").toLowerCase();
  return scan.risks
    .filter((r) => {
      const resource = scan.resources.find((x) => x.id === r.resourceId);
      return (
        [r.title, r.id, resource?.name].join(" ").toLowerCase().includes(q) &&
        (!params.get("severity") || r.severity === params.get("severity")) &&
        (!params.get("handling") ||
          (params.get("handling") === "pending"
            ? r.handling !== "resolved"
            : r.handling === params.get("handling"))) &&
        (!params.get("type") || resource?.type === params.get("type"))
      );
    })
    .sort(
      (a, b) =>
        severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity),
    );
}
export function filterResources(
  scan: Scan,
  params: URLSearchParams,
): Resource[] {
  const q = (params.get("q") ?? "").toLowerCase();
  return scan.resources.filter(
    (r) =>
      [r.name, r.version, r.origin].join(" ").toLowerCase().includes(q) &&
      (!params.get("type") || r.type === params.get("type")) &&
      (params.get("unknown") !== "1" || r.licenseStatus !== "confirmed") &&
      (!params.get("risk") ||
        scan.risks.some(
          (x) =>
            x.resourceId === r.id &&
            (params.get("risk") === "any" || x.severity === params.get("risk")),
        )),
  );
}
export function validateGithub(value: string): string | null {
  if (!value.trim()) return "请输入 GitHub 仓库地址。";
  try {
    const u = new URL(value.trim());
    if (
      u.protocol !== "https:" ||
      u.hostname !== "github.com" ||
      u.port ||
      u.username ||
      u.password ||
      u.search ||
      u.hash ||
      !/^\/[a-zA-Z0-9-]+\/[a-zA-Z0-9_.-]+\/?$/.test(u.pathname)
    )
      return "请输入 https://github.com/所有者/仓库 格式，不包含查询参数或登录信息。";
    return null;
  } catch {
    return "仓库地址格式不正确。";
  }
}
export function validateZip(
  file: { name: string; size: number } | null,
  limit: number | null,
): string | null {
  if (!file) return "请选择 ZIP 文件。";
  if (!/\.zip$/i.test(file.name))
    return "仅支持 .zip 文件；安全检查和解压由后端执行。";
  if (file.size === 0) return "ZIP 文件为空，请重新选择。";
  if (limit !== null && file.size > limit)
    return "文件超过已配置的上传大小上限。";
  return null;
}
export function safeUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const u = new URL(value);
    return ["http:", "https:"].includes(u.protocol) &&
      !u.username &&
      !u.password
      ? u.href
      : null;
  } catch {
    return null;
  }
}
export function reportPayload(scan: Scan) {
  return {
    schemaVersion: "frontend-report-v2",
    ...scan,
    summary: summarize(scan),
    disclaimer:
      "合规信息整理与风险提示，不构成法律意见；已处理不等于复扫通过。",
  };
}
export function csvCell(value: unknown): string {
  let s = String(value ?? "");
  if (/^[\s]*[=+\-@]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
export function resourceCsv(scan: Scan, resources: Resource[]): string {
  return (
    "\ufeff" +
    [
      [
        "任务编号",
        "数据模式",
        "资源编号",
        "名称",
        "类型",
        "版本",
        "来源",
        "许可证",
        "许可状态",
      ],
      ...resources.map((r) => [
        scan.id,
        scan.mode,
        r.id,
        r.name,
        r.type,
        r.version,
        r.origin,
        r.license,
        r.licenseStatus,
      ]),
    ]
      .map((row) => row.map(csvCell).join(","))
      .join("\r\n")
  );
}
