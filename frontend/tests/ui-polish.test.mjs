import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');

test('search polish stays attached to real URL-backed filters', () => {
  for (const page of ['pages/History.tsx', 'pages/Resources.tsx', 'pages/Graph.tsx']) {
    const text = source(page);
    assert.match(text, /og-search-control/);
    assert.match(text, /type="search"/);
  }
  assert.match(source('pages/History.tsx'), /historySearch\(next\)/);
  assert.match(source('pages/Resources.tsx'), /filter\("q", e\.target\.value\)/);
  assert.match(source('pages/Graph.tsx'), /filter\("graph_q", event\.target\.value\)/);
});

test('upload card keeps browser preflight boundary and never reads archive content', () => {
  const text = source('pages/NewScan.tsx');
  assert.match(text, /accept="\.zip,application\/zip"/);
  assert.match(text, /只做格式与大小预检，不在浏览器解压或执行项目/);
  assert.doesNotMatch(text, /FileReader|JSZip|arrayBuffer\(/);
  assert.match(text, /is-dragging/);
});

test('download, loader and brand treatments preserve explicit semantics', () => {
  const ui = source('components/ui.tsx');
  const report = source('pages/ReportV2.tsx');
  const legacyReport = source('pages/Report.tsx');
  const resources = source('pages/Resources.tsx');
  const landing = source('pages/Landing.tsx');
  const css = source('styles/workspace.css');
  assert.match(ui, /role="status"/);
  assert.match(report, /附件由后端 GET 返回/);
  assert.match(report, /DownloadControl/);
  assert.match(legacyReport, /DownloadControl/);
  assert.match(resources, /DownloadControl/);
  assert.match(css, /\.og-app \.og-download-button,[\s\S]*border-radius: 999px/);
  assert.match(css, /\.og-download-button \.og-ui-glyph \{[\s\S]*border-radius: 50%/);
  assert.match(css, /border: 2px solid #655cff/);
  assert.match(landing, /未知仍是未知，待核验不会被包装成已核验/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /og-loading-dots-visual i \{ animation: none/);
});
