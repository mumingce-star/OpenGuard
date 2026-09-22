import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const fixture = join(root, 'benchmarks', 'examples', 'v2', 'development-detector-v1');
const manifest = JSON.parse(readFileSync(join(fixture, 'development.json'), 'utf8'));
const digest = (value) => createHash('sha256').update(value).digest('hex');

test('B05 development input artifacts are fixed and source-index bound', () => {
  assert.equal(manifest.schema_version, 'openguard-bench-manifest/2.0');
  assert.equal(manifest.evaluations[0].requested_tier, 'development');
  for (const artifact of manifest.artifacts) {
    const bytes = readFileSync(join(fixture, artifact.path));
    assert.equal(bytes.length, artifact.size_bytes, artifact.artifact_id);
    assert.equal(digest(bytes), artifact.sha256, artifact.artifact_id);
    const payload = JSON.parse(bytes);
    const provenance = payload.provenance ?? payload;
    assert.equal(provenance.source_commit, 'a34c29f', artifact.artifact_id);
    assert.equal(provenance.split, 'dev', artifact.artifact_id);
    if (artifact.artifact_id !== 'art_source_index') {
      assert.equal(provenance.source_index_artifact_id, 'art_source_index', artifact.artifact_id);
      assert.match(provenance.source_sha256, /^[a-f0-9]{64}$/);
    }
  }
});

test('prediction and result are format-valid development placeholders, not metrics', () => {
  const artifact = (id) => manifest.artifacts.find((item) => item.artifact_id === id);
  const prediction = JSON.parse(readFileSync(join(fixture, artifact('art_prediction').path), 'utf8'));
  const result = JSON.parse(readFileSync(join(fixture, artifact('art_result').path), 'utf8'));
  assert.equal(prediction.schema, 'openguard.b05.prediction/1');
  assert.equal(prediction.execution_status, 'not_executed');
  assert.deepEqual(prediction.predictions, []);
  assert.equal(prediction.formal_metrics_claimed, false);
  assert.equal(result.schema, 'openguard.b05.result/1');
  assert.equal(result.result_status, 'not_executed');
  assert.equal(result.metrics, null);
  assert.equal(result.formal_metrics_claimed, false);
  assert.equal(result.declared_tier, 'development');
});
