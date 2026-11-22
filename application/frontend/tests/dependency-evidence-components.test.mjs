import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { runtime } from "./runtime.mjs";

const require = createRequire(import.meta.url);
const digest = "a".repeat(64);
const reference = (overrides = {}) => ({
  evidence_id: "evd_test_only_original",
  source: "lock",
  file_path: "deps/sample/uv.lock",
  locator: "deps/sample/uv.lock:/package/0/version",
  source_sha256: digest,
  producer: { name: "openguard.dependency-observations.lock", version: "1.0", type: "parser" },
  verification_status: "pending",
  kind: "manifest_field",
  start_line: 12,
  end_line: 14,
  ...overrides,
});

function dependency({ evidence = [reference()], ...overrides } = {}) {
  return {
    resource_id: "cmp_test_only",
    name: "example-dependency",
    ecosystem: "pypi",
    version: "1.2.3",
    sources: ["lock"],
    role_state: "inferred",
    evidence,
    evidence_total: evidence.length,
    evidence_returned: evidence.length,
    incomplete: false,
    conflicts: [],
    conflicts_total: 0,
    conflicts_returned: 0,
    gaps: [],
    ...overrides,
  };
}

function components(panelStates = []) {
  const callbacks = new Map();
  const copied = [];
  function load(name, imports) {
    const source = readFileSync(new URL("../src/components/" + name, import.meta.url), "utf8");
    const module = { exports: {} };
    vm.runInNewContext(ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
    }).outputText, {
      module,
      exports: module.exports,
      require: specifier => imports[specifier] ?? require(specifier),
    }, { filename: name });
    return module.exports;
  }
  const ui = {
    ActionButton({ kind, children, onClick, ...props }) {
      callbacks.set(children, onClick);
      return React.createElement("button", props, children);
    },
    Panel({ title, caption, action, children }) {
      return React.createElement("section", null, React.createElement("h2", null, title), caption, action, children);
    },
    Empty({ title, detail }) {
      return React.createElement("div", null, title, detail);
    },
    copyText: value => { copied.push(value); },
    useNotice: () => () => {},
  };
  const domain = runtime().load("types/domain.ts");
  const reader = load("EvidenceReader.tsx", {
    "../types/domain": domain,
    "../services/model": { safeUrl: () => null },
    "./ui": ui,
  });
  let stateIndex = 0;
  const panel = load("DependencyEvidencePanel.tsx", {
    "../types/domain": domain,
    "../services/dependencyEvidence": {},
    "../services/scans": {},
    "./EvidenceReader": reader,
    "./DependencyEvidencePanel.css": {},
    "./ui": ui,
    react: { ...React, useState: () => [panelStates[stateIndex++], () => {}] },
  });
  return { ...reader, ...panel, callbacks, copied };
}

test("EvidenceReader renders authoritative reference identities and copies exact values", () => {
  const { EvidenceReader, callbacks, copied } = components();
  const html = renderToStaticMarkup(React.createElement(EvidenceReader, { references: [reference()] }));
  assert.match(html, /原始文件路径/);
  assert.match(html, /deps\/sample\/uv\.lock/);
  assert.match(html, /第 12–14 行/);
  assert.match(html, /openguard\.dependency-observations\.lock/);
  assert.match(html, /核验状态<\/dt><dd>待核验/);
  assert.match(html, /Evidence ID<\/dt><dd><code>evd_test_only_original/);
  assert.match(html, new RegExp(digest));
  assert.doesNotMatch(html, /已核验/);
  callbacks.get("复制 Evidence ID")();
  callbacks.get("复制 SHA-256")();
  assert.deepEqual(copied, ["evd_test_only_original", digest]);
});

test("EvidenceReader preserves missing path and hash as explicit gaps", () => {
  const { EvidenceReader, callbacks } = components();
  const evidence = reference({ file_path: null, locator: null, source_sha256: null });
  const html = renderToStaticMarkup(React.createElement(EvidenceReader, { references: [evidence] }));
  assert.match(html, /原始文件路径<\/dt><dd>未提供/);
  assert.match(html, /未提供原文件哈希/);
  assert.doesNotMatch(html, /记录定位|复制 SHA-256/);
  assert.ok(callbacks.has("复制 Evidence ID"));
});

test("conflict sides and gaps preserve incomplete and ambiguous states", () => {
  const { DependencyEvidenceDetails } = components();
  const declared = {
    resource_id: "cmp_manifest",
    version: "0.1.0",
    evidence: [reference({ source: "manifest", file_path: "pyproject.toml", evidence_id: "evd_declaration" })],
    evidence_total: 1,
    evidence_returned: 1,
    incomplete: false,
  };
  const locked = {
    resource_id: "cmp_test_only",
    version: "1.2.3",
    evidence: [reference({ evidence_id: "evd_lock" })],
    evidence_total: 2,
    evidence_returned: 1,
    incomplete: true,
  };
  const conflict = {
    code: "lock_version_conflict",
    status: "incomplete",
    declaration: declared,
    lock: locked,
    gaps: ["conflict_side_evidence_limit_exceeded"],
  };
  const item = dependency({ incomplete: true, conflicts: [conflict], conflicts_total: 1, conflicts_returned: 1, gaps: conflict.gaps });
  const html = renderToStaticMarkup(React.createElement(DependencyEvidenceDetails, { item, id: "test-detail" }));
  assert.match(html, /data-conflict-status="incomplete"/);
  assert.match(html, /冲突证据不完整/);
  assert.match(html, /声明版本 <strong>0\.1\.0/);
  assert.match(html, /锁文件版本 <strong>1\.2\.3/);
  assert.match(html, /pyproject\.toml/);
  assert.match(html, /evd_declaration/);
  assert.match(html, /evd_lock/);
  assert.match(html, /证据不完整 · 1\/2 条证据/);
  assert.equal((html.match(/data-gap="conflict_side_evidence_limit_exceeded"/g) ?? []).length, 1);
  assert.doesNotMatch(html, /冲突已确认/);

  const ambiguous = { ...conflict, status: "ambiguous", lock: null, gaps: ["lock_side_unavailable", "conflict_ambiguous"] };
  const ambiguousHtml = renderToStaticMarkup(React.createElement(DependencyEvidenceDetails, {
    item: { ...item, conflicts: [ambiguous], gaps: ambiguous.gaps },
    id: "test-ambiguous",
  }));
  assert.match(ambiguousHtml, /data-conflict-status="ambiguous"/);
  assert.match(ambiguousHtml, /锁文件版本 <strong>无法确定/);
  assert.match(ambiguousHtml, /证据关联不唯一/);
  assert.match(ambiguousHtml, /锁文件侧无法确定/);
  assert.doesNotMatch(ambiguousHtml, /冲突已确认/);
});

test("resource row presents inferred evidence, partial scan, and cursor continuation", () => {
  const item = dependency();
  const feed = { items: [item], total: 2, incomplete: true, next_cursor: "signed-cursor" };
  const { DependencyEvidencePanel } = components(["", { feed, loading: false, error: null }, null]);
  const html = renderToStaticMarkup(React.createElement(DependencyEvidencePanel, {
    scan: { id: "scn_test_only", mode: "api", status: "partial", revision: null, finishedAt: null },
  }));
  assert.match(html, /data-dependency-scan-status="partial"/);
  assert.match(html, /扫描部分完成/);
  assert.match(html, /example-dependency/);
  assert.match(html, /1\.2\.3/);
  assert.match(html, /推断发现/);
  assert.match(html, /待核验/);
  assert.match(html, /查看证据详情/);
  assert.match(html, /加载更多依赖/);
  assert.doesNotMatch(html, /已核验|已观察|冲突已确认/);
});

test("legacy EvidenceReader still renders the original excerpt from scan evidence", () => {
  const { EvidenceReader } = components();
  const scan = { id: "scn_original", evidence: [{
    id: "original-source", kind: "code", label: "项目代码", source: "manifest",
    path: "example.py", text: "imports", startLine: 7,
  }] };
  const html = renderToStaticMarkup(React.createElement(EvidenceReader, { scan, ids: ["original-source"] }));
  assert.match(html, /证据原文/);
  assert.match(html, /imports/);
  assert.match(html, /example\.py/);
  assert.match(html, /复制引用/);
});
