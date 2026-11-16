/** Yarn Classic lockfile v1 entries and exact descriptor relationships. */
import { createHash } from 'node:crypto';

const MAX_BYTES = 2 * 1024 * 1024;
const MAX_ENTRIES = 4096;
const MAX_REFS = 16384;
const DESCRIPTOR = /^((?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*)@(.+)$/;
const VERSION = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?$/;

function tokens(text, separator) {
  const values = [];
  let rest = text.trim();
  while (rest) {
    const match = /^("(?:[^"\\]|\\.)*"|[^\s,"]+)/.exec(rest);
    if (!match) throw new Error('invalid_yarn_lock_token');
    const word = match[0];
    const decoded = word.startsWith('"') ? JSON.parse(word) : word;
    if (typeof decoded !== 'string' || decoded.length > 4096 || /[\x00-\x1f\x7f]/.test(decoded))
      throw new Error('invalid_yarn_lock_token');
    values.push(decoded);
    rest = rest.slice(word.length);
    if (!rest.trim()) break;
    if (separator === ',') {
      rest = rest.trimStart();
      if (!rest.startsWith(',') || !rest.slice(1).trim()) throw new Error('invalid_yarn_descriptor_list');
      rest = rest.slice(1).trimStart();
    } else {
      if (!/^ +/.test(rest)) throw new Error('invalid_yarn_field');
      rest = rest.trimStart();
    }
  }
  return values;
}

export function parseYarnClassicLock(raw, { path = 'yarn.lock' } = {}) {
  if (!Buffer.isBuffer(raw) || raw.length > MAX_BYTES) throw new Error('input_limit_exceeded');
  if (typeof path !== 'string' || path.length > 1024 || /[\\:\x00-\x1f\x7f]/.test(path) ||
      path.split('/').some(part => !part || part === '.' || part === '..')) throw new Error('unsafe_source_path');
  const lines = new TextDecoder('utf-8', { fatal: true }).decode(raw).split(/\r?\n/);
  if (!lines.slice(0, 8).includes('# yarn lockfile v1')) throw new Error('unsupported_yarn_lock_version');
  const entries = [], gaps = [], descriptors = new Map();
  let current = null, section = null, refs = 0;
  const locator = line => `${path}#L${line}`;
  const gap = (code, line) => gaps.push({ code, locator: locator(line) });
  for (const [index, line] of lines.entries()) {
    const number = index + 1;
    if (line.length > 8192 || number > 131072) throw new Error('lock_structure_limit_exceeded');
    if (!line.trim() || line.startsWith('#')) continue;
    if (/^[^\s].*:$/.test(line)) {
      const selectors = tokens(line.slice(0, -1), ',');
      if (!selectors.length) throw new Error('invalid_yarn_descriptor_list');
      const names = new Set(selectors.map(selector => DESCRIPTOR.exec(selector)?.[1]));
      current = { id: `yarn:${number}`, line: number, fields: new Map(), sections: new Set(), refs: new Map(), name: [...names][0] };
      if (names.size !== 1 || !current.name || selectors.some(s => DESCRIPTOR.exec(s)[2].startsWith('npm:')))
        current.name = null;
      entries.push(current);
      if (entries.length > MAX_ENTRIES) throw new Error('graph_limit_exceeded');
      for (const selector of selectors) {
        if (descriptors.has(selector)) throw new Error('duplicate_yarn_descriptor');
        descriptors.set(selector, current);
      }
      section = null;
    } else if (current && /^  (dependencies|optionalDependencies):$/.test(line)) {
      section = line.trim().slice(0, -1);
      if (current.sections.has(section)) throw new Error('duplicate_yarn_field');
      current.sections.add(section);
    } else if (current && /^  [^\s]/.test(line)) {
      const [key, value, ...other] = tokens(line.trim(), ' ');
      if (!key || !value || other.length || current.fields.has(key)) throw new Error('invalid_or_duplicate_yarn_field');
      current.fields.set(key, value);
      if (key === 'version') current.versionLine = number;
      section = null;
    } else if (current && section && /^    [^\s]/.test(line)) {
      if (++refs > MAX_REFS) throw new Error('graph_limit_exceeded');
      const [name, range, ...other] = tokens(line.trim(), ' ');
      const key = `${section}/${name}`;
      if (!name || !range || other.length || current.refs.has(key)) throw new Error('invalid_or_duplicate_yarn_dependency');
      current.refs.set(key, { descriptor: `${name}@${range}`, kind: section, line: number, range });
    } else throw new Error('invalid_yarn_lock_structure');
  }
  const nodes = [], edges = [], valid = new Map();
  for (const entry of entries) {
    if (!entry.name) { gap('ambiguous_or_alias_descriptor', entry.line); continue; }
    const version = entry.fields.get('version');
    if (version === undefined || !VERSION.test(version)) { gap('version_missing_or_unsupported', entry.line); continue; }
    valid.set(entry.id, version);
    nodes.push({ instanceId: entry.id, name: entry.name, version,
      purl: `pkg:npm/${entry.name.replace(/^@/, '%40')}@${encodeURIComponent(version)}`,
      locator: locator(entry.line), versionLocator: locator(entry.versionLine) });
  }
  for (const entry of entries) {
    if (!valid.has(entry.id)) continue;
    for (const ref of entry.refs.values()) {
      const target = descriptors.get(ref.descriptor);
      if (!target || !valid.has(target.id)) { gap('dependency_unresolved', ref.line); continue; }
      if (VERSION.test(ref.range) && valid.get(target.id) !== ref.range) { gap('dependency_version_conflict', ref.line); continue; }
      edges.push({ from: entry.id, to: target.id, kind: ref.kind, locator: locator(ref.line) });
    }
  }
  return { format: 'yarn-classic-lock/1', path, sourceSha256: createHash('sha256').update(raw).digest('hex'),
    status: gaps.length ? 'partial' : 'complete', nodes, edges, gaps, semantics: 'parsed_observation_not_installation_or_authorization' };
}
