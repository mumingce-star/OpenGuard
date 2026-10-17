// Identify an uncommitted frontend without pretending HEAD represents its full contents.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
const output = process.argv[2];
if (!output) throw new Error('Provide a NEW output JSON path outside frontend');
const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
if (path.resolve(output).startsWith(path.join(root, 'frontend') + path.sep)) throw new Error('Manifest must be outside frontend');
const paths = [...new Set(execFileSync('git', ['ls-files', '-z', '-c', '-o', '--exclude-standard', '--', 'frontend'], { cwd: root, encoding: 'utf8' }).split('\0').filter(Boolean))].sort();
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const files = [];
for (const file of paths) {
  if (/\/(\.env(?!\.example)|node_modules|dist)(\/|$)/.test(file)) throw new Error('Unexpected sensitive/generated path: ' + file);
  const bytes = await fs.readFile(path.join(root, file));
  files.push({ path: file, bytes: bytes.length, sha256: sha(bytes) });
}
const manifest = { schema_version: 'openguard-local-frontend-identity/1', generated_at: new Date().toISOString(),
  base_commit_not_complete_worktree: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
  algorithm: 'ordinal path sort; lowercase sha256 + two spaces + path + LF; UTF-8; SHA256',
  aggregate_sha256: sha(files.map(file => file.sha256 + '  ' + file.path + '\n').join('')), files };
await fs.writeFile(output, JSON.stringify(manifest, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ files: files.length, aggregate_sha256: manifest.aggregate_sha256, output }));
