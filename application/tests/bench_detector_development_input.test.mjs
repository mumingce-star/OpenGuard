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
  assert.equal(manifest.evaluations[0].requested_tier, 'smoke');
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

test('B05 run preparation fails closed before human Gold freeze', () => {
  const artifact = (id) => manifest.artifacts.find((item) => item.artifact_id === id);
  const payload = (id) => JSON.parse(readFileSync(join(fixture, artifact(id).path), 'utf8'));
  const detector = payload('art_detector');
  const input = payload('art_detector_input');
  const config = payload('art_config');
  const prediction = payload('art_prediction');
  const result = payload('art_result');
  const gold = payload('art_gold');

  assert.equal(manifest.governance.freeze.status, 'draft');
  assert.equal(gold.human_gold_frozen, false);
  assert.equal(config.gold_gate, 'not_frozen');
  assert.equal(config.metrics, 'not_computed_before_gold_freeze');
  assert.equal(detector.required_input_artifact_id, 'art_detector_input');
  assert.equal(input.detector_artifact_id, 'art_detector');
  assert.equal(input.run_config_artifact_id, 'art_config');
  assert.equal(prediction.input_artifact_id, 'art_detector_input');
  assert.equal(prediction.run_config_artifact_id, 'art_config');
  assert.equal(result.artifact_hash_verification, 'not_run');
  assert.equal(result.metrics_visibility, 'blocked_until_human_gold_freeze');
  assert.deepEqual(result.error_classification, {
    entrypoint: 'run_preparation', status: 'not_observed', errors: [],
  });
  assert.deepEqual(config.error_classification.allowed_codes, [
    'artifact_hash_mismatch', 'input_validation_failed', 'detector_unavailable',
    'detector_execution_failed', 'result_validation_failed', 'gold_not_frozen',
  ]);

  const forbiddenMetricKeys = new Set(['precision', 'recall', 'f1']);
  const assertNoFormalMetric = (value) => {
    if (Array.isArray(value)) value.forEach(assertNoFormalMetric);
    else if (value && typeof value === 'object') {
      for (const [key, nested] of Object.entries(value)) {
        assert.equal(forbiddenMetricKeys.has(key.toLowerCase()), false, key);
        assertNoFormalMetric(nested);
      }
    }
  };
  [detector, input, config, prediction, result, gold].forEach(assertNoFormalMetric);
});
