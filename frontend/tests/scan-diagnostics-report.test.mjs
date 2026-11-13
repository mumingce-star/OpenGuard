import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

// Real Report and diagnostic presentation rendered by React. Only unrelated
// download/UI/statistics dependencies are isolated; no transport is available.
const require = createRequire(import.meta.url);
function load(relative, dependencies = {}) {
  const module = { exports: {} };
  const source = fs.readFileSync(new URL(relative, import.meta.url), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText, {
    module, exports: module.exports,
    require: name => {
      if (Object.hasOwn(dependencies, name)) return dependencies[name];
      if (['react', 'react-dom', 'react/jsx-runtime'].includes(name)) return require(name);
      throw new Error('Unapproved test module: ' + name);
    },
  });
  return module.exports;
}
const presentation = load('../src/services/assessmentPresentation.ts');
const { Report } = load('../src/pages/Report.tsx', {
  '../services/assessmentPresentation': presentation,
  '../services/scans': { reportDownloadUrl: (id, format) => `/api/v1/scans/${id}/report?format=${format}&download=true` },
  '../types/domain': { statusLabels: { completed: '扫描完成', partial: '扫描部分完成', failed: '失败' }, severityLabels: {} },
  '../services/model': {
    summarize: scan => ({ resources: scan.resources.length, risks: scan.risks.length }),
    groupRisks: () => [], riskCounts: () => ({ resources: 0, counts: {} }), reportPayload: () => ({}),
  },
  '../components/ui': {
    Header: ({ title }) => React.createElement('header', {}, title),
    DownloadGlyph: () => null, useNotice: () => () => {},
  },
});
function scan(overrides = {}) {
  return { id: 'scn_SYNTHETIC_TEST_ONLY', project: 'SYNTHETIC_TEST_ONLY', mode: 'api',
    status: 'partial', createdAt: '2026-10-24T00:00:00Z', finishedAt: '2026-10-24T00:01:00Z',
    risks: [], resources: [], evidence: [], reportFormats: [], snapshotVersion: '1.0', diagnostics: [], ...overrides };
}
const render = value => renderToStaticMarkup(React.createElement(Report, { scan: value }));
function section(html, id) { return html.match(new RegExp(`<section id="${id}"[\\s\\S]*?</section>`))?.[0] ?? ''; }

for (const [code, title, detail] of [
  ['pipeline_stage_failed', '扫描阶段执行失败', '不能据此判断未处理部分没有风险'],
  ['zip_ingestion_failed', 'ZIP 输入读取失败', '不是许可证不允许使用'],
  ['report_publish_failed', '报告生成或保存失败', '不会重新提交扫描'],
]) test('known failure has a precise explanation: ' + code, () => {
  const shown = presentation.presentDiagnostic({ code, message: 'saved original', stage: 'scan' });
  assert.equal(shown.title, title);
  assert.ok(shown.detail.includes(detail), shown.detail);
});

test('partial report distinguishes incomplete scanning from a successful license check', () => {
  const html = render(scan());
  const summary = section(html, 'report-0');
  assert.match(summary, /扫描仅部分完成/);
  assert.match(summary, /未覆盖项/);
  assert.match(summary, /不计入许可证风险数量/);
});

test('failed report does not imply zero findings proves safety', () => {
  const summary = section(render(scan({ status: 'failed', diagnostics: [{ code: 'pipeline_stage_failed', stage: 'scan', message: 'Stage failed.', recoverable: false }] })), 'report-0');
  assert.match(summary, /扫描失败/);
  assert.match(summary, /零发现不能解释为没有风险/);
});

test('completed report explains process completion without asserting license approval', () => {
  const summary = section(render(scan({ status: 'completed' })), 'report-0');
  assert.match(summary, /扫描流程已完成/);
  assert.match(summary, /不代表许可证适用性已获确认/);
});

test('coverage diagnosis retains original fields and resolves only exact Evidence IDs', () => {
  const diagnostics = [{ code: 'git_scan_coverage_partial', stage: 'inventory', tool: 'git', message: '仓库共 4 个条目，本次读取 2 个文件；2 个条目未扫描', recoverable: true, evidence_ids: ['evd_path', 'evd_missing'] }];
  const html = render(scan({ diagnostics, evidence: [{ id: 'evd_path', label: 'src/omitted.ts', path: 'src/omitted.ts', text: 'oversize', source: 'parser' }, { id: 'evd_other', label: 'wrong.ts', path: 'wrong.ts', source: 'parser' }] }));
  const appendix = section(html, 'report-5');
  for (const literal of ['git_scan_coverage_partial', 'inventory', 'git', diagnostics[0].message, 'evd_path', 'src/omitted.ts', 'evd_missing', '当前快照未包含该证据']) assert.ok(appendix.includes(literal), literal);
  assert.match(appendix, /可恢复标记：是/);
  assert.doesNotMatch(appendix, /wrong\.ts/);
  assert.match(section(html, 'report-0'), /0 条发现/);
});

test('unknown diagnoses keep original message and are not falsely classified as coverage gaps', () => {
  const shown = presentation.presentDiagnostic({ code: 'new_tool_error', message: 'unknown original', stage: 'normalize' });
  assert.equal(shown.title, '扫描执行诊断');
  const appendix = section(render(scan({ diagnostics: [{ code: 'new_tool_error', message: 'unknown original', stage: 'normalize', recoverable: false }] })), 'report-5');
  assert.match(appendix, /new_tool_error/);
  assert.match(appendix, /unknown original/);
  assert.match(appendix, /可恢复标记：否/);
});

test('all diagnoses are present outside details even before printing, with no 25-row limit', () => {
  const diagnostics = Array.from({ length: 31 }, (_, i) => ({ code: 'synthetic_' + i, message: 'message_' + i, stage: 'scan', recoverable: false }));
  const appendix = section(render(scan({ diagnostics })), 'report-5');
  assert.match(appendix, /运行状态、覆盖范围与未完成项/);
  const visible = appendix.slice(appendix.indexOf('运行状态、覆盖范围与未完成项'));
  assert.doesNotMatch(visible, /<details/);
  for (const diagnostic of diagnostics) assert.ok(visible.includes(diagnostic.message), diagnostic.message);
});

test('diagnostic HTML and malicious Evidence locators remain escaped text, never active markup or links', () => {
  const marker = '<img src=x onerror="alert(1)">';
  const appendix = section(render(scan({ diagnostics: [{ code: 'unsafe_message', stage: 'scan', tool: marker, message: marker, evidence_ids: ['evd_x'] }], evidence: [{ id: 'evd_x', label: marker, path: 'javascript:alert(1)', source: 'test' }] })), 'report-5');
  assert.match(appendix, /&lt;img/);
  assert.doesNotMatch(appendix, /<img|onerror="|href="javascript:/);
  assert.ok(appendix.includes('javascript:alert(1)'));
});

test('legacy error without structured diagnosis is not silently lost from report', () => {
  const appendix = section(render(scan({ status: 'failed', error: 'legacy failure', diagnostics: [] })), 'report-5');
  assert.match(appendix, /legacy failure/);
});

test('absence of diagnosis is not presented as proof of full coverage', () => {
  const appendix = section(render(scan({ status: 'completed' })), 'report-5');
  assert.match(appendix, /当前快照未提供结构化诊断/);
  assert.match(appendix, /不代表整个仓库已核验/);
});
