import type { Scan, Risk, Resource, Severity } from "../types/domain";
export const severityOrder: Severity[] = ["critical", "high", "medium", "low"];
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
