const SHA256 = /^[a-f0-9]{64}$/;
const ID = /^[a-z][a-z0-9_.:-]{2,127}$/;

export function validateControlledReceipt(receipt) {
  const errors = [];
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return ['receipt must be an object'];
  if (receipt.schema !== 'openguard.controlled-pipeline-receipt/1') errors.push('schema');
  if (receipt.execution_mode !== 'controlled' || receipt.production_scan_started !== false) errors.push('execution_mode');
  for (const key of ['receipt_id', 'run_id']) if (!ID.test(receipt[key] ?? '')) errors.push(key);
  const source = receipt.source;
  if (!source || typeof source !== 'object' || !ID.test(source.source_id ?? '') || !/^[a-f0-9]{40}$/.test(source.commit ?? '') || !SHA256.test(source.source_sha256 ?? '')) errors.push('source');
  const artifacts = receipt.artifacts;
  if (!artifacts || typeof artifacts !== 'object' || !SHA256.test(artifacts.input_sha256 ?? '') || !SHA256.test(artifacts.config_sha256 ?? '') || !SHA256.test(artifacts.result_sha256 ?? '')) errors.push('artifacts');
  if (!receipt.environment || typeof receipt.environment !== 'object' || Array.isArray(receipt.environment)) errors.push('environment');
  if (!Number.isFinite(receipt.total_duration_ms) || receipt.total_duration_ms < 0) errors.push('total_duration_ms');
  if (!Array.isArray(receipt.stages) || !receipt.stages.length || receipt.stages.some((stage) => !ID.test(stage?.name ?? '') || !Number.isFinite(stage.duration_ms) || stage.duration_ms < 0)) errors.push('stages');
  if (!['success', 'failure'].includes(receipt.status)) errors.push('status');
  return errors;
}
