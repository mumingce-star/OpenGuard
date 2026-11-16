import type { Scan } from '../types/domain';

// Deployment disclosure only. The server independently binds and verifies the
// snapshot; these public build values grant no trust or permission.
const source = import.meta.env.VITE_FIXED_GIT_SOURCE;
const revision = import.meta.env.VITE_FIXED_GIT_REVISION;
export const fixedSourceNotice = typeof source === 'string' &&
  /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(source) &&
  typeof revision === 'string' && /^[0-9a-f]{40}$/.test(revision)
  ? { source, revision } : null;

export function isFixedSourceScan(scan: Scan | null | undefined): boolean {
  return scan?.mode === 'api' && scan.evidence.some(item =>
    item.sourceKind === 'metadata' && item.path === 'source-snapshot/git') || false;
}
