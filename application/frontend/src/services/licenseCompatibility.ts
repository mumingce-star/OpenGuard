import { request } from './scans';
import { validateDependencyEvidenceScanRef, type DependencyEvidenceScanRef } from './dependencyEvidence';

export const COMPATIBILITY_SCHEMA = 'openguard-license-compatibility/1';
export const COMPATIBILITY_RULE_VERSION = 'license-compatibility-matrix/1';

export const compatibilityStatuses = ['INCOMPATIBLE', 'REVIEW_REQUIRED', 'UNKNOWN', 'CONDITIONAL', 'COMPATIBLE'] as const;
export const pairwiseConflictStatuses = ['INCOMPATIBLE', 'REVIEW_REQUIRED', 'CONDITIONAL'] as const;
export const targetSources = ['explicit', 'root_package', 'root_conflict', 'ambiguous_roots', 'undeclared'] as const;
export const ecosystems = ['pypi', 'npm', 'golang', 'cargo', 'maven', 'unknown'] as const;

export type CompatibilityStatus = typeof compatibilityStatuses[number];
export type PairwiseConflictStatus = typeof pairwiseConflictStatuses[number];
export type TargetSource = typeof targetSources[number];

export type TargetLicenseResolution = {
  license: string | null;
  source: TargetSource;
  status: 'RESOLVED' | 'UNKNOWN';
  root_component_id: string | null;
  gaps: string[];
};

export type CompatibilityUsageSummary = {
  commercial: boolean;
  distributed: boolean;
  modified: boolean;
  network_service: boolean;
};

export type CompatibilityCounts = Record<CompatibilityStatus, number>;

export type CompatibilitySummary = {
  overall_status: CompatibilityStatus;
  dependency_count: number;
  unique_license_count: number;
  target_counts: CompatibilityCounts;
  pairwise_counts: CompatibilityCounts;
  compatible_count: number;
  conditional_count: number;
  review_required_count: number;
  incompatible_count: number;
  unknown_count: number;
};

export type CompatibilityComponentRef = {
  resource_id: string;
  name: string;
  version: string | null;
  ecosystem: typeof ecosystems[number];
  evidence_ids: string[];
};

export type TargetAssessment = CompatibilityComponentRef & {
  declared_license: string | null;
  status: CompatibilityStatus;
  rule_id: string;
  rationale: string;
  obligations: string[];
  chosen_branch: string | null;
};

export type PairwiseConflict = {
  license_a: string;
  license_b: string;
  status: PairwiseConflictStatus;
  rule_id: string;
  rationale: string;
  components_a: CompatibilityComponentRef[];
  components_b: CompatibilityComponentRef[];
};

export type CompatibilityMatrixCell = {
  row: number;
  col: number;
  status: CompatibilityStatus;
  rule_id: string;
};

export type CompatibilityMatrix = {
  licenses: string[];
  truncated: boolean;
  cells: CompatibilityMatrixCell[];
};

export type LicenseCompatibilityReport = {
  schema_version: typeof COMPATIBILITY_SCHEMA;
  rule_version: typeof COMPATIBILITY_RULE_VERSION;
  scan_ref: DependencyEvidenceScanRef;
  supported_targets: string[];
  target: TargetLicenseResolution;
  usage: CompatibilityUsageSummary;
  summary: CompatibilitySummary;
  target_assessments: TargetAssessment[];
  pairwise_conflicts: PairwiseConflict[];
  matrix: CompatibilityMatrix;
  formal_effect: 'none';
  model_calls: 0;
  limitations: string[];
};

export const compatibilityStatusLabels: Record<CompatibilityStatus, string> = {
  COMPATIBLE: '兼容',
  CONDITIONAL: '条件兼容',
  REVIEW_REQUIRED: '需人工复核',
  INCOMPATIBLE: '不兼容',
  UNKNOWN: '未知',
};

export const targetSourceLabels: Record<TargetSource, string> = {
  explicit: '显式指定',
  root_package: '根包自动推导',
  root_conflict: '根许可证存在冲突',
  ambiguous_roots: '多根包声明不一致',
  undeclared: '根许可证未声明',
};

const scanIdPattern = /^scn_(?:[0-9a-hjkmnp-tv-z]{26}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/;
const topFields = [
  'schema_version', 'rule_version', 'scan_ref', 'supported_targets', 'target', 'usage',
  'summary', 'target_assessments', 'pairwise_conflicts', 'matrix', 'formal_effect',
  'model_calls', 'limitations',
] as const;

function assertCompatDto(condition: unknown): asserts condition {
  if (!condition) throw new Error('许可证兼容性矩阵响应不符合接口约定。');
}

function recordFields<K extends string>(value: unknown, expected: readonly K[]): Record<K, unknown> {
  assertCompatDto(value !== null && typeof value === 'object' && !Array.isArray(value));
  assertCompatDto(Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key)));
  return value as Record<K, unknown>;
}

function isEnum<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === 'string' && values.includes(value as T);
}

function isNonNegInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

function nonEmptyText(value: unknown, maxLength = 2000): value is string {
  return typeof value === 'string' && value.length >= 1 && value.length <= maxLength;
}

function stringList(value: unknown, maxItems: number, maxLength = 500): string[] {
  assertCompatDto(Array.isArray(value) && value.length <= maxItems);
  for (const item of value) assertCompatDto(nonEmptyText(item, maxLength));
  return value as string[];
}

function parseCounts(value: unknown): CompatibilityCounts {
  const counts = recordFields(value, compatibilityStatuses);
  for (const status of compatibilityStatuses) assertCompatDto(isNonNegInt(counts[status]));
  return counts as CompatibilityCounts;
}

function parseComponentRef(value: unknown, expectedKeys: readonly string[] = ['resource_id', 'name', 'version', 'ecosystem', 'evidence_ids']): Record<string, unknown> {
  const ref = recordFields(value, expectedKeys);
  assertCompatDto(nonEmptyText(ref.resource_id, 200) && nonEmptyText(ref.name, 500));
  assertCompatDto(ref.version === null || nonEmptyText(ref.version, 200));
  assertCompatDto(isEnum(ref.ecosystem, ecosystems));
  stringList(ref.evidence_ids, 2000, 200);
  return ref;
}

export function validateLicenseCompatibility(raw: unknown, scanId: string): LicenseCompatibilityReport {
  const root = recordFields(raw, topFields);
  assertCompatDto(
    root.schema_version === COMPATIBILITY_SCHEMA &&
    root.rule_version === COMPATIBILITY_RULE_VERSION &&
    root.formal_effect === 'none' &&
    root.model_calls === 0,
  );
  const scanRef = validateDependencyEvidenceScanRef(root.scan_ref, scanId);
  stringList(root.supported_targets, 200, 100);

  const target = recordFields(root.target, ['license', 'source', 'status', 'root_component_id', 'gaps']);
  assertCompatDto(
    (target.license === null || nonEmptyText(target.license, 100)) &&
    isEnum(target.source, targetSources) &&
    (target.status === 'RESOLVED' || target.status === 'UNKNOWN') &&
    (target.root_component_id === null || nonEmptyText(target.root_component_id, 200)),
  );
  stringList(target.gaps, 50, 200);

  const usage = recordFields(root.usage, ['commercial', 'distributed', 'modified', 'network_service']);
  assertCompatDto(
    typeof usage.commercial === 'boolean' &&
    typeof usage.distributed === 'boolean' &&
    typeof usage.modified === 'boolean' &&
    typeof usage.network_service === 'boolean',
  );

  const summary = recordFields(root.summary, [
    'overall_status', 'dependency_count', 'unique_license_count', 'target_counts', 'pairwise_counts',
    'compatible_count', 'conditional_count', 'review_required_count', 'incompatible_count', 'unknown_count',
  ]);
  assertCompatDto(
    isEnum(summary.overall_status, compatibilityStatuses) &&
    isNonNegInt(summary.dependency_count) &&
    isNonNegInt(summary.unique_license_count) &&
    isNonNegInt(summary.compatible_count) &&
    isNonNegInt(summary.conditional_count) &&
    isNonNegInt(summary.review_required_count) &&
    isNonNegInt(summary.incompatible_count) &&
    isNonNegInt(summary.unknown_count),
  );
  parseCounts(summary.target_counts);
  parseCounts(summary.pairwise_counts);

  assertCompatDto(Array.isArray(root.target_assessments) && root.target_assessments.length <= 20_000);
  for (const item of root.target_assessments) {
    const row = parseComponentRef(item, [
      'resource_id', 'name', 'version', 'ecosystem', 'evidence_ids',
      'declared_license', 'status', 'rule_id', 'rationale', 'obligations', 'chosen_branch',
    ]);
    assertCompatDto(
      (row.declared_license === null || nonEmptyText(row.declared_license, 200)) &&
      isEnum(row.status, compatibilityStatuses) &&
      nonEmptyText(row.rule_id, 200) &&
      nonEmptyText(row.rationale, 2000) &&
      (row.chosen_branch === null || nonEmptyText(row.chosen_branch, 100)),
    );
    stringList(row.obligations, 50, 500);
  }

  assertCompatDto(Array.isArray(root.pairwise_conflicts) && root.pairwise_conflicts.length <= 5_000);
  for (const item of root.pairwise_conflicts) {
    const pair = recordFields(item, ['license_a', 'license_b', 'status', 'rule_id', 'rationale', 'components_a', 'components_b']);
    assertCompatDto(
      nonEmptyText(pair.license_a, 200) &&
      nonEmptyText(pair.license_b, 200) &&
      isEnum(pair.status, pairwiseConflictStatuses) &&
      nonEmptyText(pair.rule_id, 200) &&
      nonEmptyText(pair.rationale, 2000) &&
      Array.isArray(pair.components_a) &&
      Array.isArray(pair.components_b),
    );
    for (const c of pair.components_a) parseComponentRef(c);
    for (const c of pair.components_b) parseComponentRef(c);
  }

  const matrix = recordFields(root.matrix, ['licenses', 'truncated', 'cells']);
  const licenses = stringList(matrix.licenses, 30, 200);
  assertCompatDto(typeof matrix.truncated === 'boolean' && Array.isArray(matrix.cells) && matrix.cells.length <= 900);
  for (const cellRaw of matrix.cells) {
    const cell = recordFields(cellRaw, ['row', 'col', 'status', 'rule_id']);
    assertCompatDto(
      isNonNegInt(cell.row) && cell.row < licenses.length &&
      isNonNegInt(cell.col) && cell.col < licenses.length &&
      isEnum(cell.status, compatibilityStatuses) &&
      nonEmptyText(cell.rule_id, 200),
    );
  }

  stringList(root.limitations, 20, 500);
  return { ...(root as LicenseCompatibilityReport), scan_ref: scanRef };
}

export async function readLicenseCompatibility(
  scanId: string,
  options: { targetLicense?: string | null; signal?: AbortSignal } = {},
): Promise<LicenseCompatibilityReport> {
  assertCompatDto(scanIdPattern.test(scanId));
  const query = new URLSearchParams();
  if (options.targetLicense && options.targetLicense.trim()) {
    query.set('target_license', options.targetLicense.trim());
  }
  const suffix = query.toString() ? `?${query}` : '';
  const raw = await request(
    `/scans/${encodeURIComponent(scanId)}/license-compatibility${suffix}`,
    { method: 'GET', cache: 'no-store' },
    options.signal,
    200,
  );
  if (options.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  return validateLicenseCompatibility(raw, scanId);
}
