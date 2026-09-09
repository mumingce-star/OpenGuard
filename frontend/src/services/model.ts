import type { Scan, Risk, Resource, Severity } from "../types/domain";
export const severityOrder: Severity[] = ["critical", "high", "medium", "low", "info"];
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

// Only known rule IDs carry a legal category; titles and model prose are not classifiers.
const issueRules: Record<string, string> = {
  "license-evidence-gate": "许可证据待核验",
  "license-rule-coverage": "规则覆盖待补充",
  "LIC-MIT-NOTICE": "许可声明保留",
  "LIC-APACHE-2.0-NOTICE": "许可声明保留",
  "LIC-BSD-3-CLAUSE-NOTICE": "许可声明保留",
  "LIC-BSD-2-CLAUSE-NOTICE": "许可声明保留",
  "LIC-ISC-NOTICE": "许可声明保留",
  "LIC-GPL-3.0-ONLY-COPYLEFT": "分发与源码义务复核",
  "LIC-GPL-2.0-ONLY-COPYLEFT": "分发与源码义务复核",
  "LIC-MPL-2.0-FILE-COPYLEFT": "分发与源码义务复核",
  "LIC-EPL-2.0-RECIPROCAL": "分发与源码义务复核",
  "LIC-LGPL-2.1-ONLY-REVIEW": "分发与源码义务复核",
  "LIC-AGPL-3.0-ONLY-NETWORK": "网络使用义务复核",
  "LIC-CC-BY-4.0-ATTRIBUTION": "署名义务复核",
  "LIC-CC-BY-NC-4.0-NONCOMMERCIAL": "非商业限制复核",
  "LIC-CC0-1.0-ATTRIBUTION-REVIEW": "来源记录复核",
  "LIC-UNLICENSE-PROVENANCE": "来源记录复核",
};
export function riskCounts(rows: Risk[]) {
  const counts = Object.fromEntries(severityOrder.map(s => [s, rows.filter(r => r.severity === s).length])) as Record<Severity, number>;
  return { findings: rows.length, resources: new Set(rows.map(r => r.resourceId)).size,
    highest: severityOrder.find(s => counts[s] > 0), counts };
}
const typeLabels: Record<string, string> = {Package: "软件依赖", Model: "模型", Dataset: "数据集", API: "接口", Service: "服务", Asset: "其他资源"};
const outcomeLabels: Record<string, string> = {review_required: "待人工核验", unknown: "判断依据不足", warning: "存在规则提示", pass: "规则检查通过"};
function highestFirst(a: {highest?: Severity}, b: {highest?: Severity}) {
  return severityOrder.indexOf(a.highest ?? "info") - severityOrder.indexOf(b.highest ?? "info");
}
export function groupRisks(scan: Scan, rows: Risk[]) {
  const resources = new Map(scan.resources.map(r => [r.id, r]));
  const categories = new Map<string, Map<string, Risk[]>>();
  for (const risk of rows) {
    const category = issueRules[risk.ruleId ?? ""] ?? "其他／未分类发现";
    const resource = resources.get(risk.resourceId);
    const type = resource?.type ?? "未知资源";
    // Compare exact recorded license and trigger; do not infer usage from titles or AI.
    const subgroup = JSON.stringify([type, risk.ruleId ?? "未提供规则编号", risk.outcome ?? "未提供判断状态", resource?.license ?? "许可未知", risk.fact ?? "上下文未提供"]);
    if (!categories.has(category)) categories.set(category, new Map());
    const groups = categories.get(category)!;
    if (!groups.has(subgroup)) groups.set(subgroup, []);
    groups.get(subgroup)!.push(risk);
  }
  return [...categories].map(([title, groups]) => {
    const members = [...groups.values()].flat();
    return { title, ...riskCounts(members), groups: [...groups].map(([key, rows]) => {
      const [type, rule, outcome, license, trigger] = JSON.parse(key) as string[];
      const unknown = ["NOASSERTION", "许可未知"].includes(license);
      return { key, title: `${typeLabels[type] ?? "未知资源"} · ${unknown ? "许可待核验" : `已记录许可 ${license}`} · ${outcomeLabels[outcome] ?? "判断状态未提供"}`,
        summary: unknown ? "当前许可记录尚不能确定授权，需回到逐条证据核验。" : `记录中包含 ${license} 许可标识；是否满足使用条件仍需核对原文及实际用途。`,
        rule, trigger, rows, ...riskCounts(rows) };
    }).sort(highestFirst) };
  }).sort(highestFirst);
}
export function aiSourceLabel(risk: Risk): string {
  if (risk.ai.status === "failed") return "AI 生成失败 · 参考现有规则与证据";
  if (risk.ai.status !== "ready") return "规则回退 · 未提供有效 AI 解释";
  if (risk.ai.text?.startsWith("【资源级AI解释】")) return "资源级 AI 解释 · 仍需人工核验";
  if (risk.ai.text?.startsWith("【同类风险AI核验建议")) return "旧版同类共享建议 · 非逐资源解释";
  return "AI 辅助内容 · 未标明资源级生成";
}
