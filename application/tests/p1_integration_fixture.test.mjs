import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import {execFileSync} from 'node:child_process';

const ROOT = process.cwd();
const FIXTURE = path.join(ROOT, 'tests/fixtures/p1-integration-v1');
const load = name => JSON.parse(fs.readFileSync(path.join(FIXTURE, name), 'utf8'));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

test('fixed package reproduces and binds source/artifact hashes', () => {
  execFileSync('node', [path.join(FIXTURE, 'generate.mjs'), '--check'], {cwd: ROOT});
  const manifest = load('manifest.json');
  for (const row of manifest.sources) {
    assert.equal(sha(fs.readFileSync(path.join(ROOT, row.path))), row.sha256);
    assert.equal(sha(execFileSync('git', ['show', `${row.fixed_commit}:${row.path}`], {cwd: ROOT})), row.commit_blob_sha256);
  }
  for (const row of manifest.artifacts) {
    assert.equal(sha(fs.readFileSync(path.join(FIXTURE, row.path))), row.sha256);
    assert.deepEqual(row.source_commits, manifest.revisions.map(item => item.commit));
  }
});

test('acceptance cardinalities and lineage are fixed', () => {
  const scans = load('scans.json');
  const assessment = load('assessment.json');
  const upstream = load('remediation-input.json');
  const task = load('remediation-task.json');
  const history = load('history.json');
  assert.deepEqual(scans.items.map(item => item.status), ['partial', 'completed']);
  assert.equal(history.count, 205);
  assert.equal(new Set(history.items.map(item => item.scan_id)).size, 205);
  assert.equal(scans.items[1].findings[0].id, assessment.finding_ids[0]);
  assert.equal(assessment.obligations[0].rule_id, 'LIC-APACHE-2.0-NOTICE');
  assert.equal(assessment.obligations[0].fulfillment, 'pending');
  assert.equal(upstream.eligible_origins[0].source_hash, task.origin.source_hash);
  for (const size of [100, 300, 500]) {
    const graph = load(`graph-${size}.json`);
    const ids = new Set(graph.nodes.map(node => node.id));
    assert.equal(ids.size, size);
    assert.equal(graph.coverage.node_count, size);
    assert.ok(graph.edges.every(edge => ids.has(edge.source) && ids.has(edge.target)));
  }
});

test('Report V2 input preserves evidence gaps and non-authorization', () => {
  const value = load('report-v2-input.json');
  assert.equal(value.status, 'draft_input_only');
  assert.equal(value.resource_profile.authorization_status, 'pending');
  assert.equal(value.resource_profile.license_expression_id, null);
  assert.equal(value.policy.license_expression_autofill, false);
  assert.equal(value.expected_consumer_result.notice_fact_count, 5);
  assert.equal(value.expected_consumer_result.gap_count, 7);
  assert.equal(value.expected_consumer_result.report_snapshot_created, false);
  assert.equal(fs.existsSync(path.join(FIXTURE, 'report-v2-snapshot.json')), false);
});
