import type { Scan } from "../types/domain";
export const stages = [
  "获取仓库",
  "分析项目结构",
  "识别第三方资源",
  "许可证标准化",
  "规则检查",
  "AI 辅助解释",
  "生成报告",
];
export type Scenario =
  | "standard"
  | "clean"
  | "empty"
  | "missing"
  | "partial"
  | "failed";
export const scenarios: Record<Scenario, string> = {
  standard: "标准演示",
  clean: "无风险",
  empty: "无资源",
  missing: "证据缺失 / AI 失败",
  partial: "部分扫描失败",
  failed: "任务失败",
};
// Synthetic, versioned fixture. It is not a scan or a legal assessment of any real project.
export function createSnapshot(
  id: string,
  scenario: Scenario,
  createdAt = new Date().toISOString(),
): Scan {
  const scan: Scan = {
    id,
    mode: "mock",
    project: "OpenGuard 演示实验室",
    input: "固定合成快照 · 未读取或上传你的仓库/文件",
    createdAt,
    finishedAt: null,
    status: "queued",
    stageIndex: 0,
    stages: [...stages],
    error: null,
    completeness: "full",
    snapshotVersion: "demo-2026-09-03-v2",
    resources: [
      {
        id: "res-1",
        name: "transformers",
        type: "Package",
        version: "4.52.0",
        origin: "requirements.txt",
        license: "Apache-2.0",
        licenseStatus: "review_required",
        evidenceIds: ["ev-1", "ev-2"],
      },
      {
        id: "res-2",
        name: "DemoResearch-8B（虚构模型）",
        type: "Model",
        version: "demo-v1",
        origin: "model.config.json",
        license: null,
        licenseStatus: "unknown",
        evidenceIds: ["ev-3"],
      },
      {
        id: "res-3",
        name: "Demo-Corpus（合成数据）",
        type: "Dataset",
        version: "demo-v1",
        origin: "data/sources.json",
        license: null,
        licenseStatus: "unknown",
        evidenceIds: ["ev-4"],
      },
      {
        id: "res-4",
        name: "fastapi",
        type: "Package",
        version: "0.116.1",
        origin: "requirements.txt",
        license: "MIT",
        licenseStatus: "review_required",
        evidenceIds: ["ev-1"],
      },
      {
        id: "res-5",
        name: "Example Search API（虚构服务）",
        type: "API",
        version: "v1",
        origin: "https://example.com",
        license: "服务条款待复核",
        licenseStatus: "review_required",
        evidenceIds: ["ev-5"],
      },
      {
        id: "res-6",
        name: "Ollama",
        type: "Service",
        version: null,
        origin: "README.md",
        license: null,
        licenseStatus: "unknown",
        evidenceIds: [],
      },
      {
        id: "res-7",
        name: "security-grid.svg",
        type: "Asset",
        version: null,
        origin: "src/assets/security-grid.svg",
        license: null,
        licenseStatus: "unknown",
        evidenceIds: [],
      },
    ],
    risks: [
      {
        id: "RISK-001",
        resourceId: "res-1",
        title: "上游 NOTICE 与分发义务待核对",
        severity: "high",
        handling: "open",
        verification: "unverified",
        fact: "合成项目 requirements.txt 引用了 transformers；快照中的发布文件清单未列出 NOTICE。",
        conclusion:
          "需要核查上游是否附带 NOTICE、实际分发方式及适用条款。不能仅凭 Apache-2.0 名称判定必须新增 NOTICE。",
        remediation:
          "核对锁定版本的上游许可证与 NOTICE；如存在适用声明，按对应要求在发布产物中保留并复扫。",
        ai: {
          status: "ready",
          text: "演示解释：先补齐上游材料，再由负责人确认分发义务；这不是法律意见。",
        },
        evidenceIds: ["ev-1", "ev-2", "ev-6"],
      },
      {
        id: "RISK-002",
        resourceId: "res-2",
        title: "模型许可证字段缺失",
        severity: "high",
        handling: "reviewing",
        verification: "unverified",
        fact: "虚构模型配置中的 license 字段为 null。",
        conclusion: "授权信息不足，保持待确认；不推断模型限制或可商用状态。",
        remediation: "向模型提供方获取原始授权文件，记录版本与来源后复核。",
        ai: { status: "unavailable", text: null },
        evidenceIds: ["ev-3"],
      },
      {
        id: "RISK-003",
        resourceId: "res-3",
        title: "数据集作者与许可信息待补充",
        severity: "medium",
        handling: "open",
        verification: "unverified",
        fact: "合成数据来源记录中 author 与 license 均为空。",
        conclusion: "现有材料不足以确认再利用授权。",
        remediation: "补充数据来源、作者和原始授权材料，不以可下载代替已授权。",
        ai: {
          status: "ready",
          text: "演示解释：保留未知状态，等待负责人核实来源。",
        },
        evidenceIds: ["ev-4"],
      },
      {
        id: "RISK-004",
        resourceId: "res-5",
        title: "服务条款快照版本未登记",
        severity: "low",
        handling: "resolved",
        verification: "unverified",
        fact: "虚构服务记录只有条款 URL，没有条款版本。",
        conclusion: "已处理是人工标记，尚无复扫通过依据。",
        remediation: "记录条款日期与可核验来源，后续通过复扫验证。",
        ai: { status: "unavailable", text: null },
        evidenceIds: ["ev-5"],
      },
    ],
    evidence: [
      {
        id: "ev-1",
        kind: "code",
        label: "Python 依赖清单",
        source: "合成 fixture · 依赖解析",
        path: "requirements.txt",
        startLine: 1,
        highlightLines: [2],
        text: "fastapi==0.116.1\ntransformers==4.52.0",
      },
      {
        id: "ev-2",
        kind: "license",
        label: "许可原文来源待补充",
        source: "合成 fixture · 未抓取许可原文",
        path: "third_party/transformers/LICENSE",
        text: null,
      },
      {
        id: "ev-3",
        kind: "code",
        label: "模型配置",
        source: "合成 fixture · 配置解析",
        path: "model.config.json",
        startLine: 1,
        highlightLines: [3],
        text: '{\n  "model": "DemoResearch-8B",\n  "license": null\n}',
      },
      {
        id: "ev-4",
        kind: "code",
        label: "数据来源记录",
        source: "合成 fixture · 配置解析",
        path: "data/sources.json",
        startLine: 1,
        highlightLines: [3, 4],
        text: '{\n  "dataset": "Demo-Corpus",\n  "author": null,\n  "license": null\n}',
      },
      {
        id: "ev-5",
        kind: "code",
        label: "API 条款记录",
        source: "合成 fixture · 配置解析",
        path: "services.json",
        url: "https://example.com",
        startLine: 1,
        highlightLines: [3],
        text: '{\n  "termsUrl": "https://example.com",\n  "termsVersion": null\n}',
      },
      {
        id: "ev-6",
        kind: "rule",
        label: "判断依据与适用边界",
        source: "合成 fixture · 人工复核提示",
        text: "仅观察到清单引用与发布目录记录；尚未核实上游 NOTICE 内容。状态：需要人工复核。",
      },
    ],
  };
  if (scenario === "clean") scan.risks = [];
  if (scenario === "empty") {
    scan.risks = [];
    scan.resources = [];
    scan.evidence = [];
  }
  if (scenario === "missing") {
    scan.evidence = [];
    scan.risks = scan.risks.map((r) => ({
      ...r,
      ai: { status: "failed", text: null },
    }));
  }
  if (scenario === "partial")
    scan.error = "演示故障：模型来源解析失败；已获得的依赖结果仍可查看。";
  if (scenario === "failed")
    scan.error = "演示故障：获取仓库失败。未生成扫描结果。";
  return scan;
}
