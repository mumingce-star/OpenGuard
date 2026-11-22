import { request } from './scans';

const sources = ['manifest', 'lock', 'sbom', 'unknown'] as const;
const verificationStatuses = ['verified', 'pending', 'not_applicable', 'rejected'] as const;
const evidenceKinds = ['file', 'manifest_field', 'url', 'tool_output', 'license_text', 'metadata'] as const;
const producerTypes = ['parser', 'scanner', 'rule_engine', 'ai', 'human'] as const;
const roleStates = ['observed', 'inferred', 'unknown'] as const;
const conflictStatuses = ['confirmed', 'incomplete', 'ambiguous'] as const;
const ecosystems = ['pypi', 'npm', 'unknown'] as const;
const terminalStatuses = ['completed', 'partial'] as const;
const schema = 'openguard-dependency-evidence/1';
export const REPORT_DEPENDENCY_EVIDENCE_SCHEMA = 'openguard-report-v2-dependency-evidence/1';

export type DependencySource = typeof sources[number];
export type DependencyEvidenceScanRef = {
  scan_id: string;
  revision: string | null;
  facts_hash: string;
  input_hash: string;
  inventory_hash: string | null;
  status: typeof terminalStatuses[number];
  registry_revision: number;
};
type HashValue = { algorithm: 'sha256'; value: string };
export type DependencyEvidenceProducer = {
  type: typeof producerTypes[number];
  name: string;
  version: string;
  config_digest: HashValue | null;
  provider: string | null;
  model_id: string | null;
  prompt_schema_digest: HashValue | null;
};
export type DependencyEvidenceRef = {
  evidence_id: string;
  source: DependencySource;
  file_path: string | null;
  locator: string | null;
  source_sha256: string | null;
  producer: DependencyEvidenceProducer;
  verification_status: typeof verificationStatuses[number];
  kind: typeof evidenceKinds[number];
  start_line: number | null;
  end_line: number | null;
};
export type DependencyConflictSide = {
  resource_id: string;
  version: string;
  evidence: DependencyEvidenceRef[];
  evidence_total: number;
  evidence_returned: number;
  incomplete: boolean;
};
export type DependencyVersionConflict = {
  code: 'lock_version_conflict';
  status: typeof conflictStatuses[number];
  declaration: DependencyConflictSide | null;
  lock: DependencyConflictSide | null;
  gaps: string[];
};
export type DependencyEvidenceItem = {
  resource_id: string;
  name: string;
  version: string | null;
  ecosystem: typeof ecosystems[number];
  role_state: typeof roleStates[number];
  sources: DependencySource[];
  evidence: DependencyEvidenceRef[];
  evidence_total: number;
  evidence_returned: number;
  conflicts: DependencyVersionConflict[];
  conflicts_total: number;
  conflicts_returned: number;
  incomplete: boolean;
  gaps: string[];
};
export type DependencyEvidencePage = {
  schema_version: typeof schema;
  scan_ref: DependencyEvidenceScanRef;
  source: DependencySource | null;
  limit: number;
  total: number;
  returned: number;
  next_cursor: string | null;
  coverage: 'unknown';
  incomplete: boolean;
  items: DependencyEvidenceItem[];
};
export type DependencyEvidenceFeed = Omit<DependencyEvidencePage, 'returned'> & { seenCursors: string[] };
export type ReportDependencyEvidence = {
  schema_version: typeof REPORT_DEPENDENCY_EVIDENCE_SCHEMA;
  scan_ref: DependencyEvidenceScanRef;
  coverage: 'unknown';
  total: number;
  returned: number;
  incomplete: boolean;
  items: DependencyEvidenceItem[];
};
type PageOptions = { source?: DependencySource | null; limit?: number; cursor?: string | null };

const scanRefKeys = ['scan_id', 'revision', 'facts_hash', 'input_hash', 'inventory_hash', 'status', 'registry_revision'] as const;
const id = /^(?:scn|cmp|evd)_(?:[0-9a-hjkmnp-tv-z]{26}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/;
const sha256 = /^[0-9a-f]{64}$/;
const cursorPattern = /^[A-Za-z0-9_-]{1,2048}$/;
const unsafeLocation = /[\\\p{Cc}\p{Cf}\p{Cs}]/u;

function assertDto(condition: unknown): asserts condition {
  if (!condition) throw new Error('依赖证据响应不符合接口约定，或与当前扫描不匹配。');
}
function fields<K extends string>(value: unknown, expected: readonly K[]): Record<K, unknown> {
  assertDto(value !== null && typeof value === 'object' && !Array.isArray(value));
  assertDto(Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key)));
  return value as Record<K, unknown>;
}
function boundedText(value: unknown, maximum: number, minimum = 1): value is string {
  if (typeof value !== 'string' || value.length > maximum * 2) return false;
  const length = Array.from(value).length;
  return length >= minimum && length <= maximum;
}
function validId(value: unknown, prefix: 'scn_' | 'cmp_' | 'evd_'): value is string {
  return typeof value === 'string' && value.startsWith(prefix) && id.test(value);
}
function isHash(value: unknown): value is string {
  return typeof value === 'string' && sha256.test(value);
}
function count(value: unknown, minimum = 0): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum;
}
function isEnum<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === 'string' && values.includes(value as T);
}
function array<T>(value: unknown, maximum: number, decode: (entry: unknown) => T): T[] {
  assertDto(Array.isArray(value) && value.length <= maximum);
  return value.map(decode);
}
function unique(values: readonly string[]): boolean {
  return new Set(values).size === values.length;
}
function gaps(value: unknown): string[] {
  assertDto(Array.isArray(value) && value.every(code => typeof code === 'string' && /^[a-z][a-z0-9_]{0,99}$/.test(code)) && unique(value));
  return value;
}
function validateHashValue(value: unknown): void {
  if (value === null) return;
  const source = fields(value, ['algorithm', 'value']);
  assertDto(source.algorithm === 'sha256' && isHash(source.value));
}
export function validateDependencyEvidenceScanRef(value: unknown, scanId: string): DependencyEvidenceScanRef {
  const ref = fields(value, scanRefKeys);
  assertDto(validId(ref.scan_id, 'scn_') && ref.scan_id === scanId &&
    (ref.revision === null || (typeof ref.revision === 'string' && ref.revision.length > 0)) &&
    isHash(ref.facts_hash) && isHash(ref.input_hash) &&
    (ref.inventory_hash === null || isHash(ref.inventory_hash)) &&
    isEnum(ref.status, terminalStatuses) && count(ref.registry_revision, 1));
  return ref as DependencyEvidenceScanRef;
}
function producer(value: unknown): DependencyEvidenceProducer {
  const item = fields(value, ['type', 'name', 'version', 'config_digest', 'provider', 'model_id', 'prompt_schema_digest']);
  assertDto(isEnum(item.type, producerTypes) && boundedText(item.name, 200) && boundedText(item.version, 100));
  validateHashValue(item.config_digest);
  validateHashValue(item.prompt_schema_digest);
  assertDto(item.type === 'ai'
    ? boundedText(item.provider, 200) && item.provider.trim().length > 0 &&
      boundedText(item.model_id, 300) && item.model_id.trim().length > 0 && item.prompt_schema_digest !== null
    : item.provider === null && item.model_id === null && item.prompt_schema_digest === null);
  return item as DependencyEvidenceProducer;
}
function relativePath(value: unknown): value is string {
  return boundedText(value, 2048) && !unsafeLocation.test(value) && !/^[A-Za-z]:/.test(value) &&
    value.split('/').every(part => part !== '' && part !== '.' && part !== '..');
}
function evidenceRef(value: unknown): DependencyEvidenceRef {
  const item = fields(value, [
    'evidence_id', 'source', 'file_path', 'locator', 'source_sha256',
    'producer', 'verification_status', 'kind', 'start_line', 'end_line',
  ]);
  assertDto(validId(item.evidence_id, 'evd_') && isEnum(item.source, sources) &&
    isEnum(item.verification_status, verificationStatuses) && isEnum(item.kind, evidenceKinds) &&
    ((item.start_line === null && item.end_line === null) ||
      (count(item.start_line, 1) && count(item.end_line, item.start_line))));
  assertDto(item.file_path === null
    ? item.locator === null && item.source_sha256 === null
    : item.source !== 'unknown' && relativePath(item.file_path) &&
      boundedText(item.locator, 2048) && !unsafeLocation.test(item.locator) &&
      (item.source_sha256 === null || isHash(item.source_sha256)));
  producer(item.producer);
  return item as DependencyEvidenceRef;
}
function evidenceList(value: unknown, maximum: number): DependencyEvidenceRef[] {
  const items = array(value, maximum, evidenceRef);
  assertDto(unique(items.map(item => item.evidence_id)));
  return items;
}
function conflictSide(value: unknown, source: 'manifest' | 'lock'): DependencyConflictSide | null {
  if (value === null) return null;
  const item = fields(value, ['resource_id', 'version', 'evidence', 'evidence_total', 'evidence_returned', 'incomplete']);
  const evidence = evidenceList(item.evidence, 8);
  assertDto(validId(item.resource_id, 'cmp_') && boundedText(item.version, 200) &&
    count(item.evidence_total, 1) && evidence.length === Math.min(item.evidence_total, 8) &&
    item.evidence_returned === evidence.length && item.incomplete === (evidence.length < item.evidence_total) &&
    evidence.every(ref => ref.source === source && ref.file_path !== null && ref.source_sha256 !== null &&
      ref.verification_status !== 'rejected'));
  return item as DependencyConflictSide;
}
function versionConflict(value: unknown): DependencyVersionConflict {
  const item = fields(value, ['code', 'status', 'declaration', 'lock', 'gaps']);
  const declaration = conflictSide(item.declaration, 'manifest'), lock = conflictSide(item.lock, 'lock');
  const reasons = gaps(item.gaps);
  const ambiguous = reasons.includes('conflict_ambiguous');
  assertDto(item.code === 'lock_version_conflict' && isEnum(item.status, conflictStatuses) &&
    item.status === (ambiguous ? 'ambiguous' : reasons.length ? 'incomplete' : 'confirmed') &&
    reasons.includes('declaration_side_unavailable') === (declaration === null) &&
    reasons.includes('lock_side_unavailable') === (lock === null) &&
    reasons.includes('conflict_side_evidence_limit_exceeded') === Boolean(declaration?.incomplete || lock?.incomplete) &&
    (declaration === null || lock === null ||
      (declaration.resource_id !== lock.resource_id && declaration.version !== lock.version)));
  return item as DependencyVersionConflict;
}
function dependencyItem(value: unknown): DependencyEvidenceItem {
  const item = fields(value, [
    'resource_id', 'name', 'version', 'ecosystem', 'role_state', 'sources',
    'evidence', 'evidence_total', 'evidence_returned',
    'conflicts', 'conflicts_total', 'conflicts_returned', 'incomplete', 'gaps',
  ]);
  const evidence = evidenceList(item.evidence, 50), conflicts = array(item.conflicts, 8, versionConflict);
  const reasons = gaps(item.gaps);
  assertDto(validId(item.resource_id, 'cmp_') && boundedText(item.name, 200) &&
    (item.version === null || boundedText(item.version, 200, 0)) &&
    isEnum(item.ecosystem, ecosystems) && isEnum(item.role_state, roleStates) &&
    Array.isArray(item.sources) && item.sources.length > 0 &&
    item.sources.every(source => isEnum(source, sources)) && unique(item.sources));
  const actualSources = item.sources as DependencySource[];
  assertDto(count(item.evidence_total, 1) && item.evidence_returned === evidence.length &&
    evidence.length <= item.evidence_total && evidence.every(ref => actualSources.includes(ref.source)) &&
    (evidence.length !== item.evidence_total ||
      actualSources.every(source => evidence.some(ref => ref.source === source))) &&
    (item.role_state !== 'observed' || actualSources.includes('manifest')) &&
    (item.role_state !== 'inferred' || actualSources.some(source => source === 'lock' || source === 'sbom')) &&
    count(item.conflicts_total) && conflicts.length === Math.min(item.conflicts_total, 8) &&
    item.conflicts_returned === conflicts.length && (item.conflicts_total === 0 || item.role_state === 'unknown') &&
    item.incomplete === (reasons.length > 0) &&
    (evidence.length === item.evidence_total || item.incomplete) &&
    (conflicts.length === item.conflicts_total || reasons.includes('conflict_limit_exceeded')) &&
    conflicts.every(conflict => conflict.gaps.every(gap => reasons.includes(gap))));
  return item as DependencyEvidenceItem;
}

function evidenceIdentity(ref: DependencyEvidenceRef): string {
  const producer = ref.producer;
  return JSON.stringify([
    ref.source, ref.file_path, ref.locator, ref.source_sha256, ref.kind, ref.verification_status,
    ref.start_line, ref.end_line, producer.type, producer.name, producer.version,
    producer.config_digest?.value ?? null, producer.provider, producer.model_id,
    producer.prompt_schema_digest?.value ?? null,
  ]);
}
function validateBindings(items: readonly DependencyEvidenceItem[]): void {
  const versions = new Map<string, string | null>();
  const evidence = new Map<string, string>();
  function record(resourceId: string, version: string | null, refs: readonly DependencyEvidenceRef[]) {
    assertDto(!versions.has(resourceId) || versions.get(resourceId) === version);
    versions.set(resourceId, version);
    for (const ref of refs) {
      const identity = evidenceIdentity(ref);
      assertDto(!evidence.has(ref.evidence_id) || evidence.get(ref.evidence_id) === identity);
      evidence.set(ref.evidence_id, identity);
    }
  }
  for (const item of items) {
    record(item.resource_id, item.version, item.evidence);
    for (const conflict of item.conflicts) {
      for (const side of [conflict.declaration, conflict.lock]) {
        if (side !== null) record(side.resource_id, side.version, side.evidence);
      }
    }
  }
}

export function validateReportDependencyEvidence(raw: unknown, boundScan: DependencyEvidenceScanRef): ReportDependencyEvidence {
  const report = fields(raw, ['schema_version', 'scan_ref', 'coverage', 'total', 'returned', 'incomplete', 'items']);
  const ref = validateDependencyEvidenceScanRef(report.scan_ref, boundScan.scan_id);
  assertDto(report.schema_version === REPORT_DEPENDENCY_EVIDENCE_SCHEMA && report.coverage === 'unknown' &&
    scanRefKeys.every(key => ref[key] === boundScan[key]) && count(report.total) && report.total <= 20_000);
  const items = array(report.items, report.total, dependencyItem);
  assertDto(report.returned === items.length && report.total === items.length &&
    items.every((item, index) => index === 0 || items[index - 1].resource_id < item.resource_id) &&
    report.incomplete === (ref.status === 'partial' || items.some(item => item.incomplete)));
  validateBindings(items);
  return report as ReportDependencyEvidence;
}

export function validateDependencyEvidencePage(raw: unknown, scanId: string, options: PageOptions = {}): DependencyEvidencePage {
  const page = fields(raw, [
    'schema_version', 'scan_ref', 'source', 'limit', 'total', 'returned',
    'next_cursor', 'coverage', 'incomplete', 'items',
  ]);
  const ref = validateDependencyEvidenceScanRef(page.scan_ref, scanId);
  const limit = options.limit ?? 50, source = options.source ?? null;
  assertDto(page.schema_version === schema && page.coverage === 'unknown' &&
    count(limit, 1) && limit <= 100 && page.limit === limit &&
    (source === null || isEnum(source, sources)) && page.source === source &&
    count(page.total) && (page.next_cursor === null ||
      (typeof page.next_cursor === 'string' && cursorPattern.test(page.next_cursor))));
  const items = array(page.items, limit, dependencyItem);
  assertDto(page.returned === items.length && items.length <= page.total &&
    items.every((item, index) =>
      (index === 0 || items[index - 1].resource_id < item.resource_id) &&
      (source === null || item.sources.includes(source))) &&
    page.incomplete === (ref.status === 'partial' || items.some(item => item.incomplete)) &&
    (page.next_cursor === null || (items.length === limit && items.length < page.total)));
  if (options.cursor == null) {
    assertDto(items.length === Math.min(limit, page.total) &&
      (page.next_cursor !== null) === (items.length < page.total));
  } else {
    assertDto(items.length > 0 && page.next_cursor !== options.cursor);
  }
  validateBindings(items);
  return page as DependencyEvidencePage;
}

export async function readDependencyEvidencePage(
  scanId: string,
  options: PageOptions & { signal?: AbortSignal } = {},
): Promise<DependencyEvidencePage> {
  const limit = options.limit ?? 50;
  assertDto(validId(scanId, 'scn_') && count(limit, 1) && limit <= 100 &&
    (options.source == null || isEnum(options.source, sources)) &&
    (options.cursor == null || cursorPattern.test(options.cursor)));
  const query = new URLSearchParams({ limit: String(limit) });
  if (options.source != null) query.set('source', options.source);
  if (options.cursor != null) query.set('cursor', options.cursor);
  const raw = await request(
    `/scans/${encodeURIComponent(scanId)}/dependency-evidence?${query}`,
    { method: 'GET', cache: 'no-store' },
    options.signal,
    200,
  );
  if (options.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  return validateDependencyEvidencePage(raw, scanId, options);
}

export function appendDependencyEvidencePage(
  current: DependencyEvidenceFeed | null,
  page: DependencyEvidencePage,
  requestedCursor: string | null = current?.next_cursor ?? null,
): DependencyEvidenceFeed {
  const { returned, ...next } = page;
  if (!current) {
    assertDto(requestedCursor === null && returned === Math.min(page.limit, page.total) &&
      (page.next_cursor !== null) === (returned < page.total));
    return { ...next, seenCursors: [] };
  }
  assertDto(requestedCursor !== null && current.next_cursor === requestedCursor &&
    !current.seenCursors.includes(requestedCursor) &&
    current.source === page.source && current.limit === page.limit && current.total === page.total &&
    scanRefKeys.every(key => current.scan_ref[key] === page.scan_ref[key]));
  const previousId = current.items.at(-1)?.resource_id;
  assertDto(previousId !== undefined && returned > 0 && page.items[0].resource_id > previousId &&
    returned === Math.min(page.limit, page.total - current.items.length));
  const seenCursors = [...current.seenCursors, requestedCursor];
  const items = [...current.items, ...page.items];
  assertDto((page.next_cursor !== null) === (items.length < page.total) &&
    (page.next_cursor === null || !seenCursors.includes(page.next_cursor)));
  validateBindings(items);
  return { ...next, items, seenCursors, incomplete: current.incomplete || page.incomplete };
}
