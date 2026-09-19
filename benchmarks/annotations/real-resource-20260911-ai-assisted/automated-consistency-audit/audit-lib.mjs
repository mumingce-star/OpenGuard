import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

export const DIMENSIONS = ["resource", "evidence", "license", "risk", "suggestion"];
export const RECORD_IDS = Array.from({ length: 12 }, (_, index) => `R${String(index + 1).padStart(2, "0")}`);
export const INPUT_FILES = [
  "ai-draft.json",
  "source-checks.json",
  "source-reverification.json",
  "second-ai-review.json",
  "human-confirmation.json",
  "human-amendment-r05.json",
  "real-source-recall-v1.json",
  "manifest.json"
];

const ALLOWED = {
  resource: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  evidence: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  license: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  risk: new Set(["accept", "revise", "reject", "uncertain", "not_applicable"]),
  suggestion: new Set(["actionable", "too_generic", "incorrect", "uncertain", "not_applicable"])
};

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function add(diagnostics, severity, code, message, recordId = null) {
  diagnostics.push({ severity, code, record_id: recordId, message });
}

function exactRecordIds(records) {
  if (!Array.isArray(records)) return false;
  const ids = records.map((record) => record?.record_id);
  return ids.length === RECORD_IDS.length
    && RECORD_IDS.every((id) => ids.filter((value) => value === id).length === 1);
}

function countValues(valuesByRecord) {
  const counts = Object.fromEntries(DIMENSIONS.map((dimension) => [dimension, {}]));
  for (const values of Object.values(valuesByRecord)) {
    for (const dimension of DIMENSIONS) {
      const value = values[dimension];
      counts[dimension][value] = (counts[dimension][value] ?? 0) + 1;
    }
  }
  return counts;
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function metricCounts(cases) {
  let truePositive = 0;
  let falsePositive = 0;
  let falseNegative = 0;
  for (const item of cases ?? []) {
    const expected = new Set(item.expected ?? []);
    const predicted = new Set(item.predicted ?? []);
    truePositive += [...predicted].filter((value) => expected.has(value)).length;
    falsePositive += [...predicted].filter((value) => !expected.has(value)).length;
    falseNegative += [...expected].filter((value) => !predicted.has(value)).length;
  }
  const precision = truePositive / (truePositive + falsePositive || 1);
  const recall = truePositive / (truePositive + falseNegative || 1);
  const f1 = 2 * precision * recall / (precision + recall || 1);
  return { true_positive: truePositive, false_positive: falsePositive, false_negative: falseNegative, precision, recall, f1 };
}

export async function auditBatch(baseDirectory, generatedAt = new Date().toISOString()) {
  const inputs = {};
  const inputHashes = {};
  for (const filename of INPUT_FILES) {
    const text = await readFile(resolve(baseDirectory, filename), "utf8");
    inputs[filename] = JSON.parse(text);
    inputHashes[filename] = sha256(text);
  }

  const draft = inputs["ai-draft.json"];
  const checks = inputs["source-checks.json"];
  const reverified = inputs["source-reverification.json"];
  const secondAi = inputs["second-ai-review.json"];
  const confirmation = inputs["human-confirmation.json"];
  const amendment = inputs["human-amendment-r05.json"];
  const recall = inputs["real-source-recall-v1.json"];
  const manifest = inputs["manifest.json"];
  const diagnostics = [];

  for (const [label, records] of [
    ["AI 初稿", draft.records],
    ["首次人工确认", confirmation.records],
    ["第二次 AI 审阅", secondAi.records],
    ["初次来源检查", checks.checks]
  ]) {
    if (!exactRecordIds(records)) add(diagnostics, "error", "RECORD_SET_INVALID", `${label}必须恰好包含 R01-R12，且不得重复或缺失。`);
  }

  const batchIds = [draft.batch_id, confirmation.batch_id, amendment.batch_id, manifest.batch_id];
  if (batchIds.some((value) => value !== "real-resource-20260911-ai-assisted")) {
    add(diagnostics, "error", "BATCH_ID_MISMATCH", "输入文件的 batch_id 不一致。" );
  }
  if (manifest.item_count !== 12 || confirmation.record_count !== 12 || confirmation.dimension_count !== 60) {
    add(diagnostics, "error", "DECLARED_COUNTS_INVALID", "声明的记录数或五维判断总数不等于 12/60。" );
  }
  if (confirmation.reviewer?.type !== "human" || confirmation.human_review_count_after_confirmation !== 1) {
    add(diagnostics, "error", "HUMAN_CONFIRMATION_INVALID", "首次人工确认的身份类型或人数声明无效。" );
  }
  if (confirmation.decision !== "confirm_ai_draft_without_changes" || confirmation.status !== "confirmed_single_human_review") {
    add(diagnostics, "error", "HUMAN_CONFIRMATION_STATE_INVALID", "首次人工确认状态与决策不一致。" );
  }
  if (confirmation.exposure?.independent_blind_review !== false || confirmation.second_independent_human_review_required !== true) {
    add(diagnostics, "error", "INDEPENDENCE_DISCLOSURE_INVALID", "首次人工确认必须披露非独立盲审且仍需第二真人。" );
  }
  add(diagnostics, "warning", "NO_SECOND_INDEPENDENT_HUMAN", "当前只有一名真人且看过 AI 初稿；自动审计不能替代第二位独立真人。" );

  const confirmationById = Object.fromEntries((confirmation.records ?? []).map((record) => [record.record_id, record]));
  const secondAiById = Object.fromEntries((secondAi.records ?? []).map((record) => [record.record_id, record]));
  const initialCheckById = Object.fromEntries((checks.checks ?? []).map((record) => [record.record_id, record]));
  const reverifiedById = {};
  for (const file of reverified.files ?? []) {
    for (const recordId of file.records ?? []) {
      if (reverifiedById[recordId]) add(diagnostics, "error", "SOURCE_RECORD_DUPLICATED", "来源复核记录重复映射。", recordId);
      reverifiedById[recordId] = file;
    }
  }
  if (reverified.result !== "verified" || reverified.records_attempted !== 12 || reverified.records_verified !== 12) {
    add(diagnostics, "error", "SOURCE_REVERIFICATION_INCOMPLETE", "固定提交来源复核未达到 12/12 verified。" );
  }

  const effectiveValues = {};
  const seenNames = new Set();
  const uniqueFields = ["resource_id", "risk_id", "primary_evidence_id", "remediation_id"];
  const seenIdentifiers = Object.fromEntries(uniqueFields.map((field) => [field, new Set()]));

  for (const record of draft.records ?? []) {
    const id = record.record_id;
    if (!RECORD_IDS.includes(id)) continue;
    const values = {};
    if (seenNames.has(record.name)) add(diagnostics, "error", "RESOURCE_NAME_DUPLICATED", "资源名称重复。", id);
    seenNames.add(record.name);
    for (const dimension of DIMENSIONS) {
      const judgment = record.judgments?.[dimension];
      values[dimension] = judgment?.value;
      if (!ALLOWED[dimension].has(judgment?.value)) add(diagnostics, "error", "LABEL_INVALID", `${dimension} 标签非法。`, id);
      if (typeof judgment?.reason !== "string" || judgment.reason.trim().length < 8) add(diagnostics, "error", "RATIONALE_MISSING", `${dimension} 缺少具体理由。`, id);
    }
    effectiveValues[id] = values;

    if (confirmationById[id]?.decision !== "confirmed_without_changes") {
      add(diagnostics, "error", "HUMAN_RECORD_NOT_CONFIRMED", "首次人工确认缺失或决策异常。", id);
    }
    for (const field of uniqueFields) {
      const value = record.source?.[field];
      if (!value || seenIdentifiers[field].has(value)) add(diagnostics, "error", "SOURCE_IDENTIFIER_INVALID", `${field} 缺失或重复。`, id);
      if (value) seenIdentifiers[field].add(value);
    }
    if (!record.source?.source_revision || !record.source?.source_url?.includes(record.source.source_revision)) {
      add(diagnostics, "error", "SOURCE_NOT_COMMIT_PINNED", "来源 URL 未绑定记录中的固定提交。", id);
    }
    if (!record.source?.primary_locator || !record.source?.reported_source_sha256?.match(/^[0-9a-f]{64}$/)) {
      add(diagnostics, "error", "SOURCE_LOCATOR_OR_HASH_INVALID", "主证据定位或来源 SHA-256 无效。", id);
    }
    const oldCheck = initialCheckById[id];
    if (!oldCheck || oldCheck.expected_sha256 !== record.source?.reported_source_sha256) {
      add(diagnostics, "error", "INITIAL_SOURCE_CHECK_MISMATCH", "初次来源检查与标签记录的来源摘要不一致。", id);
    }
    const verifiedFile = reverifiedById[id];
    if (!verifiedFile || verifiedFile.sha256 !== record.source?.reported_source_sha256 || verifiedFile.matches_review_table !== true) {
      add(diagnostics, "error", "SOURCE_HASH_MISMATCH", "固定提交来源复核摘要与标签记录不一致。", id);
    }
    if (record.source?.complete_report_reviewed !== false) {
      add(diagnostics, "error", "COMPLETE_REPORT_FLAG_INVALID", "完整报告复核状态必须保持保守披露。", id);
    } else {
      add(diagnostics, "warning", "COMPLETE_REPORT_NOT_REVIEWED", "仅复核了固定原文，未直接复核完整旧扫描报告。", id);
    }
    if (record.source?.additional_ai_evidence_support !== "uncertain") {
      add(diagnostics, "error", "ADDITIONAL_EVIDENCE_BOUNDARY_INVALID", "额外 AI Evidence 的支持状态必须保持 uncertain。", id);
    }
    if (!Array.isArray(record.uncertainties) || record.uncertainties.length === 0 || !record.recommended_action) {
      add(diagnostics, "error", "UNCERTAINTY_OR_ACTION_MISSING", "不确定项或后续操作缺失。", id);
    }
    if (values.license === "uncertain") {
      if (record.system_snapshot?.license_expression !== "NOASSERTION" || record.system_snapshot?.outcome !== "review_required") {
        add(diagnostics, "error", "LICENSE_GATE_CONTRADICTION", "license=uncertain 必须与 NOASSERTION/review_required 一致。", id);
      }
    } else if (record.system_snapshot?.license_expression === "NOASSERTION" || record.system_snapshot?.outcome === "review_required") {
      add(diagnostics, "error", "LICENSE_GATE_CONTRADICTION", "已确定的许可标签不得继续绑定 NOASSERTION/review_required。", id);
    }
    if (values.suggestion === "too_generic" && !record.issue_codes?.includes("suggestion_problem")) {
      add(diagnostics, "error", "SUGGESTION_ISSUE_MISSING", "too_generic 未绑定 suggestion_problem。", id);
    }
  }

  if (amendment.record_id !== "R05" || amendment.decision !== "confirm_amendment" || amendment.status !== "confirmed_by_existing_human_reviewer") {
    add(diagnostics, "error", "R05_AMENDMENT_INVALID", "R05 人工修订确认状态无效。", "R05");
  } else {
    effectiveValues.R05 = { ...effectiveValues.R05, ...amendment.judgments };
    add(diagnostics, "warning", "R05_HUMAN_AMENDMENT_APPLIED", "已应用第一位真人确认的 R05 后续修订。", "R05");
  }
  if (amendment.human_review_count_after_confirmation !== 1 || amendment.second_independent_human_review_required !== true) {
    add(diagnostics, "error", "R05_REVIEWER_COUNT_INVALID", "R05 修订不得增加真人计数或关闭第二真人门禁。", "R05");
  }

  for (const id of RECORD_IDS) {
    const review = secondAiById[id];
    if (!review || typeof review.reason !== "string" || review.reason.trim().length < 8) {
      add(diagnostics, "error", "SECOND_AI_REVIEW_MISSING", "第二次 AI 对抗式审阅缺失。", id);
      continue;
    }
    if (id === "R05") {
      if (review.decision !== "revise_resource_and_evidence_to_partially_correct"
        || effectiveValues[id]?.resource !== "partially_correct"
        || effectiveValues[id]?.evidence !== "partially_correct"
        || effectiveValues[id]?.risk !== "revise") {
        add(diagnostics, "error", "R05_ADJUDICATION_MISMATCH", "R05 的 AI 修订、人工确认和有效标签不一致。", id);
      }
    } else if (!review.decision?.startsWith("confirm")) {
      add(diagnostics, "error", "SECOND_AI_DECISION_UNRESOLVED", "第二次 AI 审阅存在未解释的修订。", id);
    }
  }

  for (const id of ["R05", "R08", "R11", "R12"]) {
    const values = effectiveValues[id];
    if (values?.risk !== "revise") add(diagnostics, "error", "HIGH_RISK_REVISION_LOST", "已确认的风险修订未保留。", id);
  }
  for (const id of ["R05", "R11", "R12"]) {
    const values = effectiveValues[id];
    if (values?.resource !== "partially_correct" || values?.evidence !== "partially_correct") {
      add(diagnostics, "error", "PARTIAL_SUPPORT_BOUNDARY_LOST", "部分支持边界未保留。", id);
    }
  }

  const effectiveCounts = countValues(effectiveValues);
  if (!sameJson(effectiveCounts, manifest.adjudicated_judgment_counts)) {
    add(diagnostics, "error", "MANIFEST_COUNTS_MISMATCH", "manifest 的最终标签分布与有效标签不一致。" );
  }
  if (manifest.human_reviews_received !== 1 || manifest.human_review?.independent_blind_review !== false
    || manifest.human_review?.second_independent_review_pending !== true) {
    add(diagnostics, "error", "MANIFEST_REVIEW_DISCLOSURE_INVALID", "manifest 的真人数量或独立性披露不正确。" );
  }
  if (manifest.original_attachment_audit?.attachments_recovered !== 0
    || manifest.original_attachment_audit?.direct_evidence_objects_reverified !== 0) {
    add(diagnostics, "error", "ATTACHMENT_DISCLOSURE_INVALID", "旧附件或额外 Evidence 不得被虚报为已恢复复核。" );
  }
  add(diagnostics, "warning", "ORIGINAL_ATTACHMENTS_UNAVAILABLE", "三份旧扫描附件及额外 Evidence 对象尚未直接恢复复核。" );

  const measured = metricCounts(recall.cases);
  const reported = recall.reported_metrics ?? {};
  for (const key of ["true_positive", "false_positive", "false_negative", "precision", "recall", "f1"]) {
    if (Math.abs((reported[key] ?? Number.NaN) - measured[key]) > 1e-12) {
      add(diagnostics, "error", "RECALL_METRIC_MISMATCH", `召回率数据中的 ${key} 无法由 case 重算得到。` );
    }
  }
  if (manifest.recall_benchmark?.gold_reviewers?.human !== 0) {
    add(diagnostics, "error", "RECALL_GOLD_HUMAN_COUNT_INVALID", "召回率 gold 不得虚报真人审阅。" );
  }
  add(diagnostics, "warning", "RECALL_GOLD_AI_ONLY", "召回率 gold 当前为 AI 构建、0 名真人复核。" );

  diagnostics.sort((left, right) => [left.severity, left.record_id ?? "", left.code, left.message]
    .join("|").localeCompare([right.severity, right.record_id ?? "", right.code, right.message].join("|")));
  const records = RECORD_IDS.map((id) => {
    const errors = diagnostics.filter((item) => item.record_id === id && item.severity === "error");
    const warnings = diagnostics.filter((item) => item.record_id === id && item.severity === "warning");
    return {
      record_id: id,
      status: errors.length ? "needs_future_human_review" : "automated_audit_pass_with_known_limitations",
      effective_judgments: effectiveValues[id] ?? null,
      error_codes: errors.map((item) => item.code),
      warning_codes: warnings.map((item) => item.code)
    };
  });
  const errorCount = diagnostics.filter((item) => item.severity === "error").length;
  const warningCount = diagnostics.filter((item) => item.severity === "warning").length;
  const quarantined = records.filter((record) => record.status === "needs_future_human_review").length;

  return {
    schema_version: "openguard-automated-label-consistency-audit/0.1",
    batch_id: "real-resource-20260911-ai-assisted",
    generated_at: generatedAt,
    status: errorCount ? "failed_with_quarantined_records" : "human_labels_with_automated_consistency_audit",
    audit_type: "deterministic_evidence_consistency_plus_existing_ai_adversarial_review",
    human_review_claim: {
      reviewer_count: 1,
      independent_second_human: false,
      automated_audit_is_human_review: false
    },
    input_sha256: Object.fromEntries(Object.entries(inputHashes).sort(([left], [right]) => left.localeCompare(right))),
    summary: {
      records: 12,
      dimensions: 60,
      automated_pass_with_known_limitations: 12 - quarantined,
      needs_future_human_review: quarantined,
      errors: errorCount,
      warnings: warningCount,
      effective_judgment_counts: effectiveCounts,
      recall_metrics_recomputed: measured
    },
    records,
    diagnostics,
    disclosure: "原人工标签已经过自动化证据一致性审计；该审计不等同于第二位真人独立核验，不能用于计算观察者间一致性，也不能单独证明语义真值。"
  };
}
