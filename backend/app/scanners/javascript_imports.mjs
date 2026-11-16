/** Private AST observations. The caller supplies trusted TypeScript 5.9.2.
 * Source bytes are never executed, transpiled, resolved, or loaded as modules.
 */
import { createHash } from 'node:crypto';

const MAX_BYTES = 256 * 1024;
const MAX_NODES = 50000;
const MAX_IMPORTS = 4096;
const safePath = p => typeof p === 'string' && p.length <= 1024 &&
  !/[\\:\x00-\x1f\x7f]/.test(p) && p.split('/').every(x => x && x !== '.' && x !== '..');
const packageRoot = specifier => {
  if (!/^(?:@[a-z0-9._-]+\/)?[a-z0-9][a-z0-9._-]*(?:\/[a-zA-Z0-9._/-]+)?$/.test(specifier)) return null;
  if (specifier.split('/').some(x => x === '.' || x === '..')) return null;
  return specifier.startsWith('@') ? specifier.split('/').slice(0, 2).join('/') : specifier.split('/')[0];
};

export function parseJavascriptImports(raw, { ts, path, reviewedBindings = new Map() }) {
  if (ts?.version !== '5.9.2') throw new Error('unsupported_typescript_version');
  if (!Buffer.isBuffer(raw) || raw.length > MAX_BYTES) throw new Error('source_limit_exceeded');
  if (!safePath(path) || !/\.(js|jsx|ts|tsx|mjs|cjs|mts|cts)$/.test(path)) throw new Error('unsupported_source_path');
  if (!(reviewedBindings instanceof Map)) throw new Error('invalid_reviewed_bindings');
  const text = new TextDecoder('utf-8', { fatal: true }).decode(raw);
  const kind = /\.(tsx|jsx)$/.test(path) ? ts.ScriptKind.TSX : /\.(ts|mts|cts)$/.test(path) ? ts.ScriptKind.TS : ts.ScriptKind.JS;
  const source = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, kind);
  const sourceSha256 = createHash('sha256').update(raw).digest('hex');
  if (source.parseDiagnostics.length) return {
    parser: 'typescript/5.9.2', path, sourceSha256, status: 'partial', observations: [],
    gaps: source.parseDiagnostics.map(d => ({ code: 'syntax_invalid', line: source.getLineAndCharacterOfPosition(d.start ?? 0).line + 1 })),
  };
  const nodes = [], stack = [source];
  while (stack.length) {
    const node = stack.pop();
    nodes.push(node);
    if (nodes.length > MAX_NODES) throw new Error('ast_limit_exceeded');
    ts.forEachChild(node, child => { stack.push(child); });
  }
  // Conservative whole-file shadowing: do not claim any require call is Node's
  // loader if the source binds or assigns that name anywhere, including patterns.
  const bindsRequire = node => {
    if (!node) return false;
    if (ts.isIdentifier(node)) return node.text === 'require';
    if (ts.isObjectBindingPattern(node) || ts.isArrayBindingPattern(node))
      return node.elements.some(e => ts.isBindingElement(e) && bindsRequire(e.name));
    return false;
  };
  const shadowed = nodes.some(n => ts.isWithStatement(n) ||
    (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === 'eval') || (
    (ts.isVariableDeclaration(n) || ts.isParameter(n) || ts.isFunctionDeclaration(n) || ts.isClassDeclaration(n) ||
     ts.isImportClause(n) || ts.isImportSpecifier(n) || ts.isNamespaceImport(n) || ts.isImportEqualsDeclaration(n)) && bindsRequire(n.name)
  ) || (ts.isBinaryExpression(n) && ts.isIdentifier(n.left) && n.left.text === 'require'));
  const observations = [], gaps = [];
  function add(node, argument, kind, typeOnly = false) {
    if (observations.length >= MAX_IMPORTS) throw new Error('import_limit_exceeded');
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
    const endLine = source.getLineAndCharacterOfPosition(node.getEnd()).line + 1;
    const literal = argument && (ts.isStringLiteral(argument) || ts.isNoSubstitutionTemplateLiteral(argument));
    const safeSpecifier = literal && argument.text.length <= 512 &&
      /^(?:node:[a-z_][a-z_/]*|[a-zA-Z0-9_./@#-]+)$/.test(argument.text);
    const specifier = safeSpecifier ? argument.text : null;
    let referenceKind = specifier === null ? 'dynamic_unknown' : specifier.startsWith('.') ? 'relative' : 'package';
    const root = specifier === null ? null : packageRoot(specifier);
    let gap = null, target = null;
    if (specifier === null) gap = literal ? 'unsupported_module_specifier' : 'nonliteral_module_unknown';
    else if (kind === 'require' && shadowed) gap = 'require_binding_ambiguous';
    else if (referenceKind === 'relative') gap = 'relative_module_not_resolved';
    else {
      const binding = reviewedBindings.get(specifier) ?? (root ? reviewedBindings.get(root) : undefined);
      if (binding && typeof binding.resourceId === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(binding.resourceId) &&
          typeof binding.version === 'string' && binding.version.length > 0 && binding.version.length <= 200 &&
          !/[\x00-\x1f\x7f]/.test(binding.version)) {
        target = { resourceId: binding.resourceId, version: binding.version };
        referenceKind = root ? 'package' : 'reviewed_alias';
      } else gap = root ? 'package_binding_missing' : 'alias_or_builtin_unknown';
    }
    if (gap) gaps.push({ code: gap, line });
    observations.push({ kind, specifier, packageName: root, referenceKind, typeOnly, target, line, endLine,
      status: target ? 'observed_reference_not_runtime' : 'unknown' });
  }
  for (const node of nodes.sort((a, b) => a.pos - b.pos || a.end - b.end)) {
    if (ts.isImportDeclaration(node)) {
      const bindings = node.importClause?.namedBindings;
      const allTypes = bindings && ts.isNamedImports(bindings) && bindings.elements.length > 0 &&
        bindings.elements.every(e => e.isTypeOnly) && !node.importClause?.name;
      add(node, node.moduleSpecifier, 'import', Boolean(node.importClause?.isTypeOnly || allTypes));
    } else if (ts.isExportDeclaration(node) && node.moduleSpecifier) {
      const allTypes = node.exportClause && ts.isNamedExports(node.exportClause) && node.exportClause.elements.length > 0 &&
        node.exportClause.elements.every(e => e.isTypeOnly);
      add(node, node.moduleSpecifier, 'export-from', Boolean(node.isTypeOnly || allTypes));
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      add(node, node.moduleReference.expression, 'import-equals', Boolean(node.isTypeOnly));
    } else if (ts.isImportTypeNode(node)) {
      add(node, ts.isLiteralTypeNode(node.argument) ? node.argument.literal : null, 'import-type', true);
    } else if (ts.isCallExpression(node)) {
      if (node.expression.kind === ts.SyntaxKind.ImportKeyword)
        add(node, node.arguments.length === 1 ? node.arguments[0] : null, 'dynamic-import');
      else if (ts.isIdentifier(node.expression) && node.expression.text === 'require')
        add(node, node.arguments.length === 1 ? node.arguments[0] : null, 'require');
    }
  }
  return { parser: 'typescript/5.9.2', path, sourceSha256, status: gaps.length ? 'partial' : 'complete', observations, gaps };
}
