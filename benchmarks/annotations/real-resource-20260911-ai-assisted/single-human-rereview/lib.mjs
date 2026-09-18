import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

export const DIMENSIONS = ["resource", "evidence", "license", "risk", "suggestion"];
export const EXPECTED_RECORD_IDS = Array.from({ length: 12 }, (_, index) => `R${String(index + 1).padStart(2, "0")}`);
export const ALLOWED = {
  resource: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  evidence: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  license: new Set(["correct", "partially_correct", "incorrect", "uncertain", "not_applicable"]),
  risk: new Set(["accept", "revise", "reject", "uncertain", "not_applicable"]),
  suggestion: new Set(["actionable", "too_generic", "incorrect", "uncertain", "not_applicable"])
};

export function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) throw new Error(`无效参数：${key ?? "<empty>"}`);
    args[key.slice(2)] = value;
  }
  return args;
}

export async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export async function hashFile(path) {
  return sha256(await readFile(path));
}

export async function writeJsonExclusive(path, value) {
  const destination = resolve(path);
  const text = `${JSON.stringify(value, null, 2)}\n`;
  await writeFile(destination, text, { encoding: "utf8", flag: "wx" });
  return { destination, sha256: sha256(text) };
}

export function recordSetErrors(records, label = "records") {
  if (!Array.isArray(records)) return [`${label} 必须是数组。`];
  const ids = records.map((record) => record?.record_id);
  const exact = ids.length === EXPECTED_RECORD_IDS.length
    && EXPECTED_RECORD_IDS.every((id) => ids.filter((value) => value === id).length === 1);
  return exact ? [] : [`${label} 必须恰好包含 R01-R12，且不得重复或缺失。`];
}

function parseTimestamp(value, field, errors) {
  if (typeof value !== "string" || !value.trim()) {
    errors.push(`${field} 必须是非空 ISO-8601 时间。`);
    return null;
  }
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) errors.push(`${field} 不是有效时间。`);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function meaningfulText(value) {
  if (typeof value !== "string" || value.trim().length < 8) return false;
  return !/(todo|待填|占位|placeholder|xxx)/i.test(value);
}

export function validatePacket(packet) {
  const errors = [];
  if (packet?.schema_version !== "openguard-single-human-rereview-packet/0.1") errors.push("盲化包 schema_version 不受支持。");
  if (packet?.batch_id !== "real-resource-20260911-ai-assisted") errors.push("盲化包 batch_id 不匹配。");
  if (packet?.purpose !== "output_review") errors.push("本工作包只允许 output_review；benchmark_gold 必须使用不暴露预测的独立流程。");
  errors.push(...recordSetErrors(packet?.records, "盲化包 records"));
  for (const record of packet?.records ?? []) {
    if ("judgments" in record || "human_review_status" in record || "issue_codes" in record) errors.push(`${record.record_id} 泄露了旧标签或旧复核状态。`);
    if (!record?.source?.source_revision || !record?.source?.reported_source_sha256) errors.push(`${record.record_id} 缺少固定 revision 或来源 SHA-256。`);
  }
  return errors;
}

export function validateReview(packetText, packet, review, minimumCoolingHours = 72) {
  const errors = [...validatePacket(packet)];
  const warnings = [];
  if (review?.schema_version !== "openguard-single-human-rereview/0.1") errors.push("复标回执 schema_version 不受支持。");
  if (review?.status !== "submitted") errors.push("复标回执 status 必须为 submitted。");
  if (review?.batch_id !== packet?.batch_id) errors.push("复标回执 batch_id 与盲化包不一致。");
  if (review?.review_cycle !== 2) errors.push("review_cycle 必须为 2。");
  if (review?.first_round_confirmation_id !== "hrv_20260911_user_01") errors.push("首轮确认 ID 不匹配。");
  if (review?.blind_packet_sha256 !== sha256(packetText)) errors.push("blind_packet_sha256 与实际盲化包不一致。");
  if (review?.reviewer?.type !== "human" || !String(review?.reviewer?.reviewer_id ?? "").trim()) errors.push("必须填写匿名 reviewer_id，并声明 type=human。");
  if (review?.reviewer?.identity_mode !== "self_reported_single_human") errors.push("identity_mode 必须为 self_reported_single_human。");
  for (const key of ["same_human_as_first_review", "prior_ai_and_system_exposure_disclosed", "previous_labels_not_accessed_during_rereview", "review_completed_without_ai_label_suggestions", "understands_not_independent_second_human"]) {
    if (review?.reviewer?.attestation?.[key] !== true) errors.push(`声明 ${key} 必须为 true。`);
  }
  const generatedAt = parseTimestamp(packet?.generated_at, "packet.generated_at", errors);
  const startedAt = parseTimestamp(review?.rereview_started_at, "rereview_started_at", errors);
  const submittedAt = parseTimestamp(review?.submitted_at, "submitted_at", errors);
  if (generatedAt !== null && startedAt !== null) {
    const hours = (startedAt - generatedAt) / 3_600_000;
    if (hours < minimumCoolingHours) errors.push(`冷却期不足：实际 ${hours.toFixed(2)} 小时，至少需要 ${minimumCoolingHours} 小时。`);
  }
  if (startedAt !== null && submittedAt !== null && submittedAt < startedAt) errors.push("submitted_at 不能早于 rereview_started_at。");
  const latestAllowed = Date.now() + 300_000;
  if (startedAt !== null && startedAt > latestAllowed) errors.push("rereview_started_at 不能是未来时间。");
  if (submittedAt !== null && submittedAt > latestAllowed) errors.push("submitted_at 不能是未来时间。");
  errors.push(...recordSetErrors(review?.records, "复标回执 records"));
  for (const record of review?.records ?? []) {
    for (const dimension of DIMENSIONS) {
      if (!ALLOWED[dimension].has(record?.judgments?.[dimension])) errors.push(`${record.record_id}.${dimension} 标签非法或缺失。`);
      if (!meaningfulText(record?.rationales?.[dimension])) errors.push(`${record.record_id}.${dimension} 必须填写至少8字符的具体理由，不能使用占位文本。`);
    }
    if (!Array.isArray(record?.evidence_locators) || record.evidence_locators.length === 0 || record.evidence_locators.some((value) => !meaningfulText(value))) errors.push(`${record.record_id} 至少需要一个具体证据定位或明确的无法定位说明。`);
  }
  if (errors.length === 0 && minimumCoolingHours < 72) warnings.push("测试覆盖使用了低于正式流程的冷却期。");
  return { errors, warnings };
}

export async function loadFirstRoundEffective(baseDirectory) {
  const draftPath = resolve(baseDirectory, "ai-draft.json");
  const confirmationPath = resolve(baseDirectory, "human-confirmation.json");
  const amendmentPath = resolve(baseDirectory, "human-amendment-r05.json");
  const [draft, confirmation, amendment] = await Promise.all([readJson(draftPath), readJson(confirmationPath), readJson(amendmentPath)]);
  const errors = [];
  if (confirmation.confirmation_id !== "hrv_20260911_user_01" || confirmation.decision !== "confirm_ai_draft_without_changes") errors.push("首轮真人确认状态不符合预期。");
  errors.push(...recordSetErrors(draft.records, "AI初稿 records"));
  errors.push(...recordSetErrors(confirmation.records, "首轮确认 records"));
  if (amendment.record_id !== "R05" || amendment.decision !== "confirm_amendment") errors.push("R05补充确认状态不符合预期。");
  if (errors.length) throw new Error(errors.join("\n"));
  const values = Object.fromEntries(draft.records.map((record) => [record.record_id, Object.fromEntries(DIMENSIONS.map((dimension) => [dimension, record.judgments[dimension].value]))]));
  values.R05 = { ...values.R05, ...amendment.judgments };
  return {
    values,
    hashes: {
      ai_draft_sha256: await hashFile(draftPath),
      human_confirmation_sha256: await hashFile(confirmationPath),
      human_amendment_r05_sha256: await hashFile(amendmentPath)
    }
  };
}

export function validateComparison(comparison) {
  const errors = [];
  if (comparison?.schema_version !== "openguard-single-human-rereview-comparison/0.1") errors.push("comparison schema_version 不受支持。");
  if (comparison?.batch_id !== "real-resource-20260911-ai-assisted") errors.push("comparison batch_id 不匹配。");
  errors.push(...recordSetErrors(comparison?.records, "comparison records"));
  const counts = Object.fromEntries(DIMENSIONS.map((dimension) => [dimension, { agreements: 0, disagreements: 0 }]));
  let agreements = 0;
  let disagreements = 0;
  for (const record of comparison?.records ?? []) {
    const names = Array.isArray(record.dimensions) ? record.dimensions.map((item) => item.dimension) : [];
    if (names.length !== DIMENSIONS.length || DIMENSIONS.some((dimension) => names.filter((name) => name === dimension).length !== 1)) {
      errors.push(`${record.record_id} 必须恰好包含五个比较维度。`);
      continue;
    }
    for (const item of record.dimensions) {
      if (!ALLOWED[item.dimension].has(item.first_round) || !ALLOWED[item.dimension].has(item.second_round)) errors.push(`${record.record_id}:${item.dimension} 比较值非法。`);
      if (item.agree !== (item.first_round === item.second_round)) errors.push(`${record.record_id}:${item.dimension} agree 与两轮值不一致。`);
      counts[item.dimension][item.agree ? "agreements" : "disagreements"] += 1;
      if (item.agree) agreements += 1; else disagreements += 1;
    }
    if (record.needs_resolution !== record.dimensions.some((item) => !item.agree)) errors.push(`${record.record_id} needs_resolution 不一致。`);
  }
  if (comparison?.summary?.total_dimensions !== agreements + disagreements || comparison?.summary?.agreements !== agreements || comparison?.summary?.disagreements !== disagreements) errors.push("comparison 汇总计数不一致。");
  const expectedRate = agreements + disagreements ? agreements / (agreements + disagreements) : 0;
  if (comparison?.summary?.exact_agreement_rate !== expectedRate) errors.push("comparison 一致率不一致。");
  for (const dimension of DIMENSIONS) {
    if (comparison?.summary?.per_dimension?.[dimension]?.agreements !== counts[dimension].agreements || comparison?.summary?.per_dimension?.[dimension]?.disagreements !== counts[dimension].disagreements) errors.push(`comparison ${dimension} 分维度计数不一致。`);
  }
  return errors;
}

export function validateResolution(comparisonText, comparison, resolution) {
  const errors = [...validateComparison(comparison)];
  if (resolution?.schema_version !== "openguard-single-human-rereview-resolution/0.1") errors.push("冲突复核 schema_version 不受支持。");
  if (resolution?.status !== "submitted") errors.push("冲突复核 status 必须为 submitted。");
  if (resolution?.batch_id !== comparison?.batch_id) errors.push("冲突复核 batch_id 不匹配。");
  if (resolution?.comparison_sha256 !== sha256(comparisonText)) errors.push("comparison_sha256 与实际比较文件不一致。");
  if (!String(resolution?.reviewer_id ?? "").trim()) errors.push("冲突复核必须填写 reviewer_id。");
  for (const key of ["reopened_primary_sources", "did_not_optimize_for_detector_metrics", "unresolved_defaults_to_uncertain", "understands_same_human_resolution"]) {
    if (resolution?.attestation?.[key] !== true) errors.push(`冲突复核声明 ${key} 必须为 true。`);
  }
  const expected = (comparison?.records ?? []).flatMap((record) => record.dimensions.filter((item) => !item.agree).map((item) => ({ record_id: record.record_id, ...item })));
  const actual = Array.isArray(resolution?.records) ? resolution.records : [];
  const actualKeys = actual.map((item) => `${item.record_id}:${item.dimension}`);
  const expectedKeys = expected.map((item) => `${item.record_id}:${item.dimension}`);
  if (actualKeys.length !== expectedKeys.length || expectedKeys.some((key) => actualKeys.filter((value) => value === key).length !== 1)) errors.push("冲突复核必须与 comparison 中的全部分歧一一对应。未发生分歧时 records 必须为空数组。");
  const expectedByKey = Object.fromEntries(expected.map((item) => [`${item.record_id}:${item.dimension}`, item]));
  for (const item of actual) {
    const expectedItem = expectedByKey[`${item.record_id}:${item.dimension}`];
    if (expectedItem && (item.first_round !== expectedItem.first_round || item.second_round !== expectedItem.second_round)) errors.push(`${item.record_id}:${item.dimension} 的两轮原值与 comparison 不一致。`);
    if (!DIMENSIONS.includes(item.dimension) || !ALLOWED[item.dimension]?.has(item.final_judgment)) errors.push(`${item.record_id}:${item.dimension} 最终标签非法。`);
    if (!meaningfulText(item.decision_basis)) errors.push(`${item.record_id}:${item.dimension} 必须填写具体冲突处理依据。`);
    if (!Array.isArray(item.evidence_locators) || item.evidence_locators.length === 0 || item.evidence_locators.some((value) => !meaningfulText(value))) errors.push(`${item.record_id}:${item.dimension} 至少需要一个证据定位或无法定位说明。`);
  }
  const comparisonCreatedAt = parseTimestamp(comparison?.created_at, "comparison.created_at", errors);
  const resolutionSubmittedAt = parseTimestamp(resolution?.submitted_at, "resolution.submitted_at", errors);
  if (comparisonCreatedAt !== null && resolutionSubmittedAt !== null && resolutionSubmittedAt < comparisonCreatedAt) errors.push("冲突复核时间不能早于比较文件生成时间。");
  if (resolutionSubmittedAt !== null && resolutionSubmittedAt > Date.now() + 300_000) errors.push("冲突复核时间不能是未来时间。");
  return errors;
}
