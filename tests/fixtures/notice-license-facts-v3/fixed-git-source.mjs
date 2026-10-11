import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';

// 仅读取本机已存在的固定 commit；禁用缺失对象的自动远程获取。
export function readFixedGitSource(root, revision, path) {
  if (!/^[a-f0-9]{40}$/.test(revision)
      || typeof path !== 'string' || !path || path.startsWith('/') || path.includes('\\')
      || path.split('/').some(part => !part || part === '.' || part === '..')
      || /[\x00-\x1f\x7f:]/.test(path)) throw new Error('fixed_source_identity_invalid');
  const options = { cwd: root, env: { ...process.env, GIT_NO_LAZY_FETCH: '1', GIT_NO_REPLACE_OBJECTS: '1' },
    timeout: 10_000, maxBuffer: 2 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] };
  if (execFileSync('git', ['cat-file', '-t', revision], options).toString('utf8').trim() !== 'commit') {
    throw new Error('fixed_source_not_commit');
  }
  const entry = execFileSync('git', ['ls-tree', '-z', revision, '--', path], options).toString('utf8');
  const match = /^100644 blob ([a-f0-9]{40})\t([^\x00]+)\x00$/.exec(entry);
  if (!match || match[2] !== path) throw new Error('fixed_source_not_regular_blob');
  const bytes = execFileSync('git', ['cat-file', 'blob', match[1]], options);
  const actual = createHash('sha1').update(`blob ${bytes.length}\0`).update(bytes).digest('hex');
  if (actual !== match[1]) throw new Error('fixed_source_blob_mismatch');
  return bytes;
}
