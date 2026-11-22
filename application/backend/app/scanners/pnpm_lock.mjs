/** Offline pnpm 9.0 adapter. Supply the trusted yaml 2.9.0 parser from the host. */
import { createHash } from 'node:crypto';

const MAX_BYTES = 2 * 1024 * 1024;
const MAX_NODES = 4096;
const MAX_REFS = 16384;
const SCOPES = ['dependencies', 'devDependencies', 'optionalDependencies'];
const NAME = /^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$/;
const VERSION = '(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)\\.(?:0|[1-9]\\d*)(?:-[a-zA-Z0-9.-]+)?(?:\\+[a-zA-Z0-9.-]+)?';
const EXACT = new RegExp(`^${VERSION}$`);
const PACKAGE = new RegExp(`^((?:@[a-z0-9][a-z0-9._-]*\\/)?[a-z0-9][a-z0-9._-]*)@(${VERSION})(\\([a-zA-Z0-9._@+/:()-]+\\))?$`);
const pointer = x => String(x).replaceAll('~', '~0').replaceAll('/', '~1');
const canonicalPath = p => typeof p === 'string' && p.length <= 1024 &&
  !/[\\:\x00-\x1f\x7f]/.test(p) && p.split('/').every(part => part && part !== '.' && part !== '..');

function linkTarget(importer, relative) {
  if (!relative || relative.startsWith('/') || /[\\:\x00-\x1f\x7f]/.test(relative)) return null;
  const parts = importer === '.' ? [] : importer.split('/');
  for (const part of relative.split('/')) {
    if (!part) return null;
    if (part === '.') continue;
    if (part === '..') {
      if (!parts.length) return null;
      parts.pop();
    } else parts.push(part);
  }
  return parts.join('/') || '.';
}

function map(value, code) {
  if (!(value instanceof Map) || [...value.keys()].some(key => typeof key !== 'string' || key.length > 2048))
    throw new Error(code);
  return value;
}

export function parsePnpmLock(raw, { yaml, yamlVersion, path = 'pnpm-lock.yaml' }) {
  if (yamlVersion !== '2.9.0' || typeof yaml?.parseDocument !== 'function') throw new Error('unsupported_yaml_parser');
  if (!Buffer.isBuffer(raw) || raw.length > MAX_BYTES) throw new Error('input_limit_exceeded');
  if (!canonicalPath(path)) throw new Error('unsafe_source_path');
  const text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
  const doc = yaml.parseDocument(text, { version: '1.2', schema: 'failsafe', uniqueKeys: true });
  if (doc.errors.length || doc.warnings.length) throw new Error('invalid_lock_yaml');
  const pending = [[doc.contents, 0]];
  let count = 0;
  while (pending.length) {
    const [node, depth] = pending.pop();
    if (!node) continue;
    if (++count > 131072 || depth > 48) throw new Error('yaml_structure_limit_exceeded');
    if (yaml.isAlias(node) || node.anchor || node.tag) throw new Error('yaml_indirection_unsupported');
    if (yaml.isPair(node)) pending.push([node.key, depth + 1], [node.value, depth + 1]);
    else if (yaml.isCollection(node)) for (const child of node.items) pending.push([child, depth + 1]);
  }
  const data = map(doc.toJS({ mapAsMap: true, maxAliasCount: 0 }), 'invalid_lock_root');
  if (data.get('lockfileVersion') !== '9.0') throw new Error('unsupported_pnpm_lock_version');
  const importers = map(data.get('importers'), 'invalid_lock_importers');
  const packages = map(data.get('packages') ?? new Map(), 'invalid_lock_packages');
  const snapshots = map(data.get('snapshots') ?? new Map(), 'invalid_lock_snapshots');
  if (importers.size + packages.size + snapshots.size > MAX_NODES) throw new Error('graph_limit_exceeded');
  const nodes = [], edges = [], gaps = [], known = new Set(), referencedPackages = new Set();
  const loc = (...parts) => `${path}:/${parts.map(pointer).join('/')}`;
  const gap = (code, locator) => gaps.push({ code, locator });
  for (const key of importers.keys()) {
    if (key !== '.' && !canonicalPath(key)) throw new Error('unsafe_importer_path');
    nodes.push({ instanceId: `importer:${key}`, kind: 'workspace', name: key, version: null, locator: loc('importers', key) });
  }
  for (const key of snapshots.keys()) {
    const match = PACKAGE.exec(key);
    if (!match) { gap('snapshot_reference_unsupported', loc('snapshots', key)); continue; }
    const [, name, version] = match;
    const packageKey = `${name}@${version}`;
    if (!packages.has(packageKey) || !(packages.get(packageKey) instanceof Map)) {
      gap('package_metadata_missing', loc('snapshots', key)); continue;
    }
    referencedPackages.add(packageKey);
    known.add(key);
    nodes.push({ instanceId: `snapshot:${key}`, kind: 'lock', name, version, locator: loc('snapshots', key),
      versionLocator: loc('packages', packageKey), purl: `pkg:npm/${name.replace(/^@/, '%40')}@${encodeURIComponent(version)}` });
  }
  for (const key of packages.keys()) if (!referencedPackages.has(key)) gap('package_without_snapshot', loc('packages', key));
  let refCount = 0;
  function visit(section, key, value) {
    for (const scope of section === 'importers' ? SCOPES : ['dependencies', 'optionalDependencies']) {
      const rows = map(value.get(scope) ?? new Map(), 'invalid_lock_dependencies');
      for (const [name, record] of rows) {
        if (++refCount > MAX_REFS) throw new Error('graph_limit_exceeded');
        const locator = loc(section, key, scope, name);
        if (!NAME.test(name) || (section === 'importers' && !(record instanceof Map))) {
          gap('dependency_invalid', locator); continue;
        }
        const ref = section === 'importers' ? record.get('version') : record;
        const specifier = section === 'importers' ? record.get('specifier') : undefined;
        if (section === 'importers' && typeof specifier !== 'string') { gap('specifier_missing', locator); continue; }
        if (typeof ref !== 'string' || ref.length > 2048) { gap('dependency_reference_missing', locator); continue; }
        const from = `${section === 'importers' ? 'importer' : 'snapshot'}:${key}`;
        if (ref.startsWith('link:')) {
          if (section !== 'importers') { gap('workspace_link_context_missing', locator); continue; }
          const target = linkTarget(key, ref.slice(5));
          if (target === null) { gap('workspace_path_unsafe', locator); continue; }
          if (!importers.has(target)) { gap('workspace_target_missing', locator); continue; }
          if (EXACT.test(specifier)) { gap('dependency_version_conflict', locator); continue; }
          edges.push({ from, to: `importer:${target}`, scope, locator });
          continue;
        }
        const explicit = PACKAGE.exec(ref);
        const target = explicit ? ref : `${name}@${ref}`;
        if (!known.has(target)) { gap('dependency_unresolved', locator); continue; }
        const [, actualName, version] = PACKAGE.exec(target);
        if (actualName !== name && section === 'importers' && !specifier.startsWith(`npm:${actualName}@`)) {
          gap('alias_binding_unverified', locator); continue;
        }
        if (specifier && EXACT.test(specifier) && specifier !== version) {
          gap('dependency_version_conflict', locator); continue;
        }
        edges.push({ from, to: `snapshot:${target}`, scope, locator });
      }
    }
  }
  for (const [key, value] of importers) visit('importers', key, map(value, 'invalid_lock_importer'));
  for (const [key, value] of snapshots) if (known.has(key)) visit('snapshots', key, map(value, 'invalid_lock_snapshot'));
  return { format: 'pnpm-lock/9.0', parser: 'yaml/2.9.0', path, sourceSha256: createHash('sha256').update(raw).digest('hex'),
    status: gaps.length ? 'partial' : 'complete', nodes, edges, gaps, semantics: 'parsed_observation_not_installation_or_authorization' };
}
