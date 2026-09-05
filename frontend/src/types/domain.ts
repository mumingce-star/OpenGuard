export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type Mode = "mock" | "api";
export type ScanStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "partial"
  | "cancelled";
export type Handling = "open" | "reviewing" | "resolved";
export type Verification = "unverified" | "passed" | "failed";
export type ResourceType =
  | "Package"
  | "Model"
  | "Dataset"
  | "API"
  | "Service"
  | "Asset";
export type EvidenceKind = "code" | "license" | "rule";
export interface Evidence {
  id: string;
  kind: EvidenceKind;
  label: string;
  source: string;
  path?: string;
  url?: string;
  startLine?: number;
  highlightLines?: number[];
  text: string | null;
}
export interface Risk {
  id: string;
  resourceId: string;
  title: string;
  severity: Severity;
  handling: Handling;
  verification: Verification;
  fact: string | null;
  conclusion: string | null;
  remediation: string | null;
  ai: { status: "ready" | "failed" | "unavailable"; text: string | null };
  evidenceIds: string[];
  outcome?: string;
}
export interface Resource {
  id: string;
  name: string;
  type: ResourceType;
  version: string | null;
  origin: string | null;
  license: string | null;
  licenseStatus: "confirmed" | "review_required" | "unknown";
  evidenceIds: string[];
}
export interface Scan {
  id: string;
  mode: Mode;
  project: string;
  input: string;
  createdAt: string | null;
  finishedAt: string | null;
  status: ScanStatus;
  stageIndex: number;
  stages: string[];
  error: string | null;
  resources: Resource[];
  risks: Risk[];
  evidence: Evidence[];
  progress?: number;
  reportFormats?: ReportFormat[];
  resultsReady?: boolean;
  // This frontend contract requires complete snapshots; reject paginated fragments.
  completeness: "full";
  snapshotVersion: string;
}
export interface ScanInput {
  kind: "github" | "zip";
  url?: string;
  file?: File;
  scopes?: string[];
}
export const statusLabels: Record<ScanStatus, string> = {
  queued: "等待中",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  partial: "部分结果",
  cancelled: "已取消",
};
export const handlingLabels: Record<Handling, string> = {
  open: "待处理",
  reviewing: "复核中",
  resolved: "已处理",
};
export const verificationLabels: Record<Verification, string> = {
  unverified: "未复扫验证",
  passed: "复扫通过",
  failed: "复扫未通过",
};
export const severityLabels: Record<Severity, string> = {
  critical: "严重",
  high: "高风险",
  medium: "中风险",
  low: "低风险",
  info: "提示",
};
export const resourceTypes: ResourceType[] = [
  "Package",
  "Model",
  "Dataset",
  "API",
  "Service",
  "Asset",
];

export type ReportFormat = "html" | "json" | "csv" | "resource_inventory";
