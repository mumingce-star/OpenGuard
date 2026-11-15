// Only immutable identity travels between pages; page-specific filters stay local.
export const contextKeys = ['assessment_id', 'assessment_version', 'p2_result_id', 'p2_revision', 'snapshot_id'] as const;
export function versionContext(query: URLSearchParams) {
  const out = new URLSearchParams();
  for (const key of contextKeys) if (query.has(key)) out.set(key, query.get(key)!);
  return out;
}
export function selectAssessment(query: URLSearchParams, id: string, version?: number) {
  const out = new URLSearchParams(query);
  if (out.get('assessment_id') !== id) {
    for (const key of contextKeys) out.delete(key);
  }
  out.set('assessment_id', id);
  if (version !== undefined) out.set('assessment_version', String(version));
  return out;
}
export function checkAssessmentVersion(query: URLSearchParams, version: number) {
  const selected = query.get('assessment_version');
  if (selected !== null && (!/^[1-9]\d*$/.test(selected) || Number(selected) !== version))
    throw new Error('固定链接的评估版本与服务器对象不一致，请核对链接；不会改选最新版本。');
}

export function selectedAssessment<T extends { id: string; scan_id: string; version: number }>(items: T[], scanId: string, query: URLSearchParams): T | undefined {
  const id = query.get('assessment_id');
  const candidate = id ? items.find(item => item.id === id) : items[0];
  if (!candidate || candidate.scan_id !== scanId) return undefined;
  const version = query.get('assessment_version');
  return version === null || version === String(candidate.version) ? candidate : undefined;
}

export function navigationContext(current: URLSearchParams, requested: URLSearchParams) {
  // Explicit assessment selection already cleared any stale downstream identity.
  if (requested.has('assessment_id')) return requested;
  const merged = versionContext(current);
  requested.forEach((value,key) => merged.set(key,value));
  return merged;
}
