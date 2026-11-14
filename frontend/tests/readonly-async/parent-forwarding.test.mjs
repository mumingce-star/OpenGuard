// NOT_RUN. Source AST assertion only; not ReactDOM or live receiver evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

test('TEST4: P2Workbench forwards readOnly independently of ordinary disabled', () => {
  const source = fs.readFileSync(new URL('../../src/components/P2Workbench.tsx', import.meta.url), 'utf8');
  const file = ts.createSourceFile('P2Workbench.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const editors = [];
  const visit = node => {
    if (ts.isJsxSelfClosingElement(node) && node.tagName.getText(file) === 'ProjectUsageEditor') editors.push(node);
    ts.forEachChild(node, visit);
  };
  visit(file);
  assert.equal(editors.length, 1, 'Expected one ProjectUsageEditor call site');
  const attrs = editors[0].attributes.properties;
  const attribute = name => attrs.find(node => ts.isJsxAttribute(node) && node.name.getText(file) === name);
  const readOnly = attribute('readOnly');
  assert.ok(readOnly?.initializer && ts.isJsxExpression(readOnly.initializer));
  const expression = readOnly.initializer.expression;
  assert.ok(expression && ts.isIdentifier(expression) && expression.text === 'readOnly', 'Forward exact readOnly capability');
  assert.ok(attribute('disabled'), 'Keep ordinary disabled as a distinct prop');
});
