const FULL_SCAN_ID = /^scn_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA256 = /^[0-9a-f]{64}$/;

export const P0_REPORT_FORMATS = Object.freeze(['html', 'json', 'csv', 'resource_inventory']);

export function p0ReportMetadataPath(scanId, format) {
  return `/api/v1/scans/${encodeURIComponent(scanId)}/report?format=${format}`;
}

export function p0ReportDownloadPath(scanId, format) {
  return `${p0ReportMetadataPath(scanId, format)}&download=true`;
}

export function expectedNotGeneratedPaths(scanId) {
  return P0_REPORT_FORMATS.map(format => p0ReportMetadataPath(scanId, format));
}

export function readP0Scenario(env = process.env, { requireHashes = false } = {}) {
  const kind = env.OPENGUARD_P0_REPORT_SCENARIO;
  if (!['available', 'not_generated'].includes(kind)) {
    throw new Error('OPENGUARD_P0_REPORT_SCENARIO must explicitly be available or not_generated.');
  }
  const scanId = env.OPENGUARD_P0_SCAN_ID;
  if (!FULL_SCAN_ID.test(scanId ?? '')) {
    throw new Error('OPENGUARD_P0_SCAN_ID must be a complete lowercase scn_UUID; abbreviations are forbidden.');
  }
  const declared = kind === 'not_generated' && env.OPENGUARD_P0_NOT_GENERATED_SCAN_IDS
    ? env.OPENGUARD_P0_NOT_GENERATED_SCAN_IDS.split(',').map(value => value.trim()).filter(Boolean)
    : [scanId];
  if (declared.some(value => !FULL_SCAN_ID.test(value)) || !declared.includes(scanId)) {
    throw new Error('OPENGUARD_P0_NOT_GENERATED_SCAN_IDS must contain only complete scan IDs and include OPENGUARD_P0_SCAN_ID.');
  }
  const scenario = { kind, scanId, scanIds: [...new Set(declared)] };
  if (kind === 'available' && requireHashes) {
    const jsonSha256 = env.OPENGUARD_P0_JSON_SHA256;
    const htmlSha256 = env.OPENGUARD_P0_HTML_SHA256;
    if (!SHA256.test(jsonSha256 ?? '') || !SHA256.test(htmlSha256 ?? '')) {
      throw new Error('P0 available acceptance requires exact OPENGUARD_P0_JSON_SHA256 and OPENGUARD_P0_HTML_SHA256.');
    }
    return { ...scenario, jsonSha256, htmlSha256 };
  }
  return scenario;
}

export function isExpectedNotGeneratedFailure(scenario, failure) {
  if (scenario?.kind !== 'not_generated') return false;
  if (failure?.method !== 'GET' || failure?.status !== 409) return false;
  if (!scenario.scanIds.flatMap(expectedNotGeneratedPaths).includes(failure.path)) return false;
  return failure.body?.error?.code === 'report_not_ready'
    && failure.body?.error?.details?.reason === 'not_generated';
}

export function assertExactNotGeneratedCoverage(assert, scenario, failures) {
  if (scenario.kind !== 'not_generated') return;
  const actual = [...new Set(failures
    .filter(failure => isExpectedNotGeneratedFailure(scenario, failure))
    .map(failure => failure.path))]
    .sort();
  const expected = scenario.scanIds.flatMap(expectedNotGeneratedPaths).sort();
  assert.deepEqual(actual, expected,
    'every declared not_generated scan must produce an audited 409 for every P0 metadata format');
}
