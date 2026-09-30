const SHA256 = /^[a-f0-9]{64}$/;
const ID = /^[a-z][a-z0-9_.:-]{2,127}$/;
export const REQUIRED_STAGES = Object.freeze(['unpack', 'scancode', 'syft', 'static_detector', 'rule_consolidation']);
const ERROR_CODES = new Set(['input_validation_failed', 'unpack_failed', 'scancode_unavailable', 'scancode_failed', 'syft_unavailable', 'syft_failed', 'static_detector_failed', 'rule_consolidation_failed', 'artifact_hash_mismatch', 'environment_mismatch', 'resource_limit_exceeded', 'internal_error']);
const text = (value, max = 256) => typeof value === 'string' && value.length > 0 && value.length <= max;
const positiveInteger = (value) => Number.isInteger(value) && value > 0;

export function validateControlledReceipt(receipt) {
  const errors = [];
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return ['receipt must be an object'];
  if (receipt.schema !== 'openguard.controlled-pipeline-receipt/2') errors.push('schema');
  if (receipt.execution_mode !== 'controlled_linux' || receipt.production_scan_started !== false) errors.push('execution_mode');
  if (!['cold', 'warm'].includes(receipt.startup_mode)) errors.push('startup_mode');
  for (const key of ['receipt_id', 'run_id']) if (!ID.test(receipt[key] ?? '')) errors.push(key);
  const source = receipt.source;
  if (!source || typeof source !== 'object' || !ID.test(source.source_id ?? '') || !/^[a-f0-9]{40}$/.test(source.commit ?? '') || !SHA256.test(source.source_sha256 ?? '')) errors.push('source');
  const artifacts = receipt.artifacts;
  if (!artifacts || typeof artifacts !== 'object' || !SHA256.test(artifacts.input_sha256 ?? '') || !SHA256.test(artifacts.config_sha256 ?? '') || !SHA256.test(artifacts.result_sha256 ?? '')) errors.push('artifacts');
  const environment = receipt.environment;
  const os = environment?.os, cpu = environment?.cpu, memory = environment?.memory, tools = environment?.tools;
  if (!environment || typeof environment !== 'object' || Array.isArray(environment)
      || !text(os?.family) || os.family !== 'linux' || !text(os?.kernel) || !text(os?.image_digest, 128)
      || !/^sha256:[a-f0-9]{64}$/.test(os.image_digest) || !text(cpu?.model) || !positiveInteger(cpu?.logical_cores)
      || !positiveInteger(memory?.limit_bytes) || !positiveInteger(memory?.observed_peak_bytes)
      || memory.observed_peak_bytes > memory.limit_bytes || !text(tools?.scancode) || !text(tools?.syft)
      || !text(tools?.static_detector) || !text(tools?.rule_version)) errors.push('environment');
  if (!Number.isFinite(receipt.total_duration_ms) || receipt.total_duration_ms < 0) errors.push('total_duration_ms');
  if (!Array.isArray(receipt.stages) || receipt.stages.length !== REQUIRED_STAGES.length
      || receipt.stages.map((stage) => stage?.name).join('|') !== REQUIRED_STAGES.join('|')
      || receipt.stages.some((stage) => !Number.isFinite(stage?.duration_ms) || stage.duration_ms < 0
          || !['completed', 'failed', 'not_run'].includes(stage?.status)
          || (stage.status === 'not_run' && stage.duration_ms !== 0)
          || (stage.status !== 'failed' && stage.failure_reason !== null)
          || (stage.status === 'failed' && !ERROR_CODES.has(stage.failure_reason)))) errors.push('stages');
  if (!['success', 'failure'].includes(receipt.status)) errors.push('status');
  const classification = receipt.error_classification;
  if (!classification || typeof classification !== 'object' || Array.isArray(classification)
      || !['not_observed', 'observed'].includes(classification.status) || !Array.isArray(classification.errors)
      || classification.errors.some((code) => !ERROR_CODES.has(code))
      || (receipt.status === 'success' && (classification.status !== 'not_observed' || classification.errors.length))
      || (receipt.status === 'failure' && (classification.status !== 'observed' || !classification.errors.length))) errors.push('error_classification');
  return errors;
}
