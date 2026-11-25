import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { runtime } from './runtime.mjs';

const require = createRequire(import.meta.url);
const scanId = 'scn_' + '0'.repeat(26);
const hash = ch => ch.repeat(64);

function validReport(overrides = {}) {
  return {
    schema_version: 'openguard-license-compatibility/1',
    rule_version: 'license-compatibility-matrix/1',
    scan_ref: {
      scan_id: scanId,
      revision: null,
      facts_hash: hash('a'),
      input_hash: hash('b'),
      inventory_hash: hash('c'),
      status: 'completed',
      registry_revision: 1,
    },
    supported_targets: ['PROPRIETARY', 'Apache-2.0', 'GPL-2.0-only', 'MIT'],
    target: {
      license: 'MIT',
      source: 'root_package',
      status: 'RESOLVED',
      root_component_id: 'cmp_' + '1'.repeat(26),
      gaps: [],
    },
    usage: {
      commercial: true,
      distributed: true,
      modified: false,
      network_service: false,
    },
    summary: {
      overall_status: 'INCOMPATIBLE',
      dependency_count: 2,
      unique_license_count: 2,
      target_counts: { COMPATIBLE: 1, CONDITIONAL: 0, REVIEW_REQUIRED: 0, INCOMPATIBLE: 1, UNKNOWN: 0 },
      pairwise_counts: { COMPATIBLE: 0, CONDITIONAL: 0, REVIEW_REQUIRED: 0, INCOMPATIBLE: 1, UNKNOWN: 0 },
      compatible_count: 1,
      conditional_count: 0,
      review_required_count: 0,
      incompatible_count: 2,
      unknown_count: 0,
    },
    target_assessments: [
      {
        resource_id: 'cmp_' + '2'.repeat(26),
        name: 'apache-dep',
        version: '1.0.0',
        ecosystem: 'npm',
        evidence_ids: ['evd_' + '1'.repeat(26)],
        declared_license: 'Apache-2.0',
        status: 'COMPATIBLE',
        rule_id: 'COMPAT-APACHE2-INBOUND',
        rationale: 'Apache-2.0 与目标许可证 MIT 兼容。',
        obligations: ['保留 Apache-2.0 全文与 NOTICE'],
        chosen_branch: null,
      },
      {
        resource_id: 'cmp_' + '3'.repeat(26),
        name: 'gpl2-dep',
        version: '2.0.0',
        ecosystem: 'cargo',
        evidence_ids: ['evd_' + '2'.repeat(26)],
        declared_license: 'GPL-2.0-only',
        status: 'INCOMPATIBLE',
        rule_id: 'COMPAT-STRONG-COPYLEFT-PROPAGATION',
        rationale: '强传染许可证 GPL-2.0-only 与 MIT 对外分发冲突。',
        obligations: ['替换强 Copyleft 依赖'],
        chosen_branch: null,
      },
    ],
    pairwise_conflicts: [
      {
        license_a: 'Apache-2.0',
        license_b: 'GPL-2.0-only',
        status: 'INCOMPATIBLE',
        rule_id: 'PAIR-GPL2-ONLY-APACHE2',
        rationale: 'GPL-2.0-only 与 Apache-2.0 在对外分发作品中公认互斥。',
        components_a: [{ resource_id: 'cmp_' + '2'.repeat(26), name: 'apache-dep', version: '1.0.0', ecosystem: 'npm', evidence_ids: [] }],
        components_b: [{ resource_id: 'cmp_' + '3'.repeat(26), name: 'gpl2-dep', version: '2.0.0', ecosystem: 'cargo', evidence_ids: [] }],
      },
    ],
    matrix: {
      licenses: ['Apache-2.0', 'GPL-2.0-only'],
      truncated: false,
      cells: [
        { row: 0, col: 0, status: 'COMPATIBLE', rule_id: 'PAIR-SAME-LICENSE' },
        { row: 0, col: 1, status: 'INCOMPATIBLE', rule_id: 'PAIR-GPL2-ONLY-APACHE2' },
        { row: 1, col: 0, status: 'INCOMPATIBLE', rule_id: 'PAIR-GPL2-ONLY-APACHE2' },
        { row: 1, col: 1, status: 'COMPATIBLE', rule_id: 'PAIR-SAME-LICENSE' },
      ],
    },
    formal_effect: 'none',
    model_calls: 0,
    limitations: ['本引擎输出不构成正式法律签认。'],
    ...overrides,
  };
}

function loadPanel() {
  const app = runtime();
  const domain = app.load('types/domain.ts');
  const compatService = app.load('services/licenseCompatibility.ts');
  const ui = {
    Panel({ title, caption, action, children }) {
      return React.createElement('section', null, React.createElement('h2', null, title), caption, action, children);
    },
    Empty({ title, detail }) {
      return React.createElement('div', null, title, detail);
    },
  };
  const source = readFileSync(new URL('../src/components/LicenseCompatibilityPanel.tsx', import.meta.url), 'utf8');
  const module = { exports: {} };
  vm.runInNewContext(
    ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    {
      module,
      exports: module.exports,
      require: (specifier) => {
        if (specifier === '../types/domain') return domain;
        if (specifier === '../services/licenseCompatibility') return compatService;
        if (specifier === '../services/scans') return { ApiError: class ApiError extends Error {} };
        if (specifier === './ui') return ui;
        if (specifier === './LicenseCompatibilityPanel.css') return {};
        return require(specifier);
      },
    },
    { filename: 'LicenseCompatibilityPanel.tsx' },
  );
  return { validateLicenseCompatibility: compatService.validateLicenseCompatibility, ...module.exports };
}

test('TASK58 validateLicenseCompatibility accepts valid report and rejects tampered fields', () => {
  const { validateLicenseCompatibility } = loadPanel();
  const report = validateLicenseCompatibility(validReport(), scanId);
  assert.equal(report.target.license, 'MIT');
  assert.equal(report.summary.incompatible_count, 2);

  assert.throws(() => validateLicenseCompatibility(validReport({ schema_version: 'wrong/0' }), scanId));
  assert.throws(() => validateLicenseCompatibility(validReport({ formal_effect: 'binding' }), scanId));
  assert.throws(() => validateLicenseCompatibility(validReport({ model_calls: 1 }), scanId));
  assert.throws(() => validateLicenseCompatibility({ ...validReport(), extra_unexpected: true }, scanId));
});

test('TASK58 LicenseCompatibilityView renders target resolution, pairwise conflict, N×N matrix and conservative limits', () => {
  const { LicenseCompatibilityView } = loadPanel();
  const html = renderToStaticMarkup(React.createElement(LicenseCompatibilityView, {
    report: validReport(),
    loading: false,
    error: null,
    targetChoice: '',
    statusFilter: '',
    onTargetChange: () => {},
    onStatusFilterChange: () => {},
    onRetry: () => {},
  }));
  assert.match(html, /项目级许可证兼容矩阵/);
  assert.match(html, /根包自动推导/);
  assert.match(html, /gpl2-dep/);
  assert.match(html, /PAIR-GPL2-ONLY-APACHE2/);
  assert.match(html, /Apache-2\.0.*GPL-2\.0-only/);
  assert.match(html, /不构成正式法律签认/);
});

test('TASK58 validateLicenseCompatibility accepts canonical SPDX expressions longer than 200 chars', () => {
  const { validateLicenseCompatibility } = loadPanel();
  const longExpr = Array.from({ length: 22 }, () => 'Apache-2.0').slice(0, 1).concat([
    'BSD-2-Clause', 'BSD-3-Clause', 'CC0-1.0', 'EPL-2.0', 'GPL-2.0-only',
    'GPL-2.0-or-later', 'GPL-3.0-only', 'GPL-3.0-or-later', 'ISC',
    'LGPL-2.1-only', 'LGPL-2.1-or-later', 'LGPL-3.0-only', 'LGPL-3.0-or-later', 'MIT', 'MPL-2.0',
  ]).join(' OR ');
  assert.ok(longExpr.length > 200 && longExpr.length <= 500, `Expected >200 chars, got ${longExpr.length}`);

  const base = validReport();
  base.target_assessments[0].declared_license = longExpr;
  base.pairwise_conflicts[0].license_a = longExpr;
  base.matrix.licenses = [longExpr, 'GPL-2.0-only'];

  const parsed = validateLicenseCompatibility(base, scanId);
  assert.equal(parsed.target_assessments[0].declared_license, longExpr);
  assert.equal(parsed.pairwise_conflicts[0].license_a, longExpr);
  assert.deepEqual(parsed.matrix.licenses, [longExpr, 'GPL-2.0-only']);
});

test('TASK58 compatPanel state transitions clear stale report on target switch and failure', () => {
  const {
    LicenseCompatibilityView,
    initialCompatibilityPanelState,
    compatLoadStarted,
    compatLoadSucceeded,
    compatLoadFailed,
  } = loadPanel();

  const firstReport = validReport({ target: { license: 'MIT', source: 'explicit', status: 'RESOLVED', root_component_id: null, gaps: [] } });
  let state = compatLoadSucceeded(initialCompatibilityPanelState, firstReport);
  assert.equal(state.loading, false);
  assert.equal(state.report.target.license, 'MIT');

  // Switching target must immediately discard the previous target report while loading.
  state = compatLoadStarted(state);
  assert.equal(state.loading, true);
  assert.equal(state.report, null);
  assert.equal(state.error, null);
  const loadingHtml = renderToStaticMarkup(React.createElement(LicenseCompatibilityView, {
    report: state.report,
    supportedTargets: state.supportedTargets,
    loading: state.loading,
    error: state.error,
    targetChoice: 'PROPRIETARY',
    statusFilter: '',
    onTargetChange: () => {},
    onStatusFilterChange: () => {},
    onRetry: () => {},
  }));
  assert.match(loadingHtml, /正在计算许可证兼容矩阵/);
  assert.doesNotMatch(loadingHtml, /gpl2-dep/);
  assert.doesNotMatch(loadingHtml, /PAIR-GPL2-ONLY-APACHE2/);

  // A failed reload must keep report cleared so stale target verdict is never displayed behind an error alert.
  state = compatLoadFailed(state, '请求失败');
  assert.equal(state.loading, false);
  assert.equal(state.report, null);
  assert.equal(state.error, '请求失败');
  const failedHtml = renderToStaticMarkup(React.createElement(LicenseCompatibilityView, {
    report: state.report,
    supportedTargets: state.supportedTargets,
    loading: state.loading,
    error: state.error,
    targetChoice: 'PROPRIETARY',
    statusFilter: '',
    onTargetChange: () => {},
    onStatusFilterChange: () => {},
    onRetry: () => {},
  }));
  assert.match(failedHtml, /请求失败/);
  assert.doesNotMatch(failedHtml, /gpl2-dep/);
  assert.doesNotMatch(failedHtml, /PAIR-GPL2-ONLY-APACHE2/);
});
