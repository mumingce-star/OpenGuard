import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const required = name => {
  const value = process.env[name];
  assert.ok(value, `${name} is required`);
  return value;
};

const baseUrl = new URL(required('P2_LIVE_BASE_URL'));
assert.ok(['127.0.0.1', 'localhost'].includes(baseUrl.hostname), 'live acceptance is restricted to loopback');
const scanId = required('P2_LIVE_SCAN_ID');
const assessmentId = required('P2_LIVE_ASSESSMENT_ID');
const assessmentVersion = Number(required('P2_LIVE_ASSESSMENT_VERSION'));
const outputPath = path.resolve(required('P2_LIVE_OUTPUT'));
const mode = process.env.P2_LIVE_MODE ?? 'write';
assert.ok(['write', 'verify'].includes(mode), 'P2_LIVE_MODE must be write or verify');
assert.ok(Number.isSafeInteger(assessmentVersion) && assessmentVersion > 0);

const origin = process.env.P2_LIVE_ORIGIN ?? 'http://127.0.0.1:4184';
const root = new URL(
  `/api/v1/scans/${encodeURIComponent(scanId)}/assessments/${encodeURIComponent(assessmentId)}/p2/`,
  baseUrl,
);
const url = (suffix, query = {}) => {
  const target = new URL(suffix, root);
  target.searchParams.set('assessment_version', String(assessmentVersion));
  for (const [key, value] of Object.entries(query)) target.searchParams.set(key, String(value));
  return target;
};

const requestLog = [];
async function call(method, target, body) {
  const response = await fetch(target, {
    method,
    headers: {
      Accept: 'application/json',
      Origin: origin,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  requestLog.push({ method, url: target.toString(), status: response.status, payload });
  return { response, payload };
}

const getOk = async (suffix, query) => {
  const { response, payload } = await call('GET', url(suffix, query));
  assert.equal(response.status, 200, `${suffix} must return 200`);
  return payload;
};

const post = async (suffix, body) => call('POST', url(suffix), body);
const findResource = (result, subject) => result.resources.find(item =>
  item.subject.resource_id === subject.resource_id && item.subject.version === subject.version);

async function verifyPersisted(receipt) {
  const index = await getOk('results');
  assert.equal(index.head_result_id, receipt.final.result_id);
  assert.equal(index.head_revision, receipt.final.revision);
  const result = await getOk(`results/${encodeURIComponent(receipt.final.result_id)}`, { revision: receipt.final.revision });
  assert.equal(result.result_sha256, receipt.final.result_sha256);
  assert.equal(result.data_scope, 'TEST_ONLY');
  assert.equal(result.formal_effect, 'none');
  const summary = await getOk(`results/${encodeURIComponent(result.result_id)}/summary`);
  assert.equal(summary.result_id, result.result_id);
  assert.equal(summary.result_revision, result.revision);
  assert.equal(summary.result_sha256, result.result_sha256);
  assert.equal(summary.formal_effect, 'none');
  assert.equal(summary.report_kind, 'P2_COMPANION_NOT_FORMAL_REPORT');
  const answer = await getOk(`answers/${encodeURIComponent(receipt.answer.answer_id)}`);
  assert.equal(answer.answer_id, receipt.answer.answer_id);
  assert.equal(answer.formal_effect, 'none');
  assert.equal(answer.provenance, 'USER_ASSERTED');
  const material = await getOk(`materials/${encodeURIComponent(receipt.material.material_id)}`);
  assert.equal(material.material_id, receipt.material.material_id);
  assert.equal(material.source_sha256, receipt.material.source_sha256);
  assert.equal(material.verification_state, 'pending');
  assert.equal(material.adoption_status, 'adopted_as_unverified_observation');
  assert.equal(material.formal_effect, 'none');
  return { index, result, summary, answer, material };
}

if (mode === 'verify') {
  const receipt = JSON.parse(await fs.readFile(outputPath, 'utf8'));
  const persisted = await verifyPersisted(receipt);
  receipt.restart_verification = {
    verified_at: new Date().toISOString(),
    checks: [
      'same head result and revision',
      'same result sha256',
      'same answer',
      'same pending material',
      'same-revision companion summary remains non-formal',
    ],
    observed: persisted,
    requests: requestLog,
  };
  await fs.writeFile(outputPath, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8');
  console.log(`P2_LIVE_RESTART_VERIFY_PASS result=${persisted.result.result_id} revision=${persisted.result.revision}`);
} else {

const binding = await getOk('binding');
assert.equal(binding.scan_id, scanId);
assert.equal(binding.assessment_id, assessmentId);
assert.equal(binding.assessment_version, assessmentVersion);
const initialIndex = await getOk('results');
assert.ok(initialIndex.head_result_id && initialIndex.head_revision > 0, 'an existing fixed TEST_ONLY result is required');
const initial = await getOk(`results/${encodeURIComponent(initialIndex.head_result_id)}`, { revision: initialIndex.head_revision });
assert.equal(initial.data_scope, 'TEST_ONLY', 'writes are allowed only on the private TEST_ONLY copy');
assert.equal(initial.formal_effect, 'none');
assert.deepEqual(initial.binding, binding);

const question = initial.questions.find(item => item.question_code === 'DELIVERY_SCOPE_FOR_RESOURCES');
assert.ok(question?.subjects?.length, 'server-provided delivery scope question is required');
const subject = question.subjects[0];
const resource = findResource(initial, subject);
assert.ok(resource, 'question subject must belong to the current result');
const currentAnswerCode = resource.user_assertions?.[question.question_code];
const answerCode = question.options.find(code => code !== currentAnswerCode);
assert.ok(answerCode, 'a server-provided option different from the current saved value is required');
const nonce = `${Date.now()}_${crypto.randomBytes(6).toString('hex')}`;
const answerRequest = {
  binding,
  expected_revision: initial.revision,
  parent_result_id: initial.result_id,
  idempotency_key: `xzb_live_answer_${nonce}`,
  question_id: question.question_id,
  question_code: question.question_code,
  answer_code: answerCode,
  subjects: [subject],
  evidence_ids: [],
};
const answerCreated = await post('answers', answerRequest);
assert.equal(answerCreated.response.status, 201);
assert.equal(answerCreated.payload.result.revision, initial.revision + 1);
assert.equal(answerCreated.payload.result.previous_result_id, initial.result_id);
assert.equal(answerCreated.payload.result.formal_effect, 'none');
assert.equal(answerCreated.payload.answer.provenance, 'USER_ASSERTED');
assert.equal(answerCreated.payload.answer.formal_effect, 'none');

const answerReplay = await post('answers', answerRequest);
assert.equal(answerReplay.response.status, 201);
assert.equal(answerReplay.payload.result.result_id, answerCreated.payload.result.result_id);
assert.equal(answerReplay.payload.answer.answer_id, answerCreated.payload.answer.answer_id);

const staleRequest = {
  ...answerRequest,
  idempotency_key: `xzb_live_stale_${nonce}`,
  answer_code: question.options.find(code => code !== answerCode) ?? answerCode,
};
const stale = await post('answers', staleRequest);
assert.equal(stale.response.status, 409);
assert.equal(stale.payload?.error?.code, 'p2_revision_conflict');
assert.equal(stale.payload?.error?.details?.reason, 'p2_revision_conflict');
assert.equal(stale.payload?.error?.details?.current_revision, answerCreated.payload.result.revision);
assert.equal(stale.payload?.error?.details?.current_result_id, answerCreated.payload.result.result_id);

const currentAfterConflict = await getOk('results');
assert.equal(currentAfterConflict.head_result_id, answerCreated.payload.result.result_id);
assert.equal(currentAfterConflict.head_revision, answerCreated.payload.result.revision);

const materialText = `P2 TEST_ONLY receiver acceptance excerpt\nnonce=${nonce}\n`;
const materialBytes = Buffer.from(materialText, 'utf8');
const materialSha = crypto.createHash('sha256').update(materialBytes).digest('hex');
const currentResource = findResource(answerCreated.payload.result, subject);
assert.ok(currentResource?.evidence_ids?.length, 'server-provided resource Evidence is required');
const materialRequest = {
  binding,
  expected_revision: answerCreated.payload.result.revision,
  parent_result_id: answerCreated.payload.result.result_id,
  idempotency_key: `xzb_live_material_${nonce}`,
  subject,
  evidence_ids: [currentResource.evidence_ids[0]],
  filename: 'LICENSE.txt',
  content_base64: materialBytes.toString('base64'),
  source_sha256: materialSha,
  source_description: 'xzb loopback TEST_ONLY receiver acceptance; not a verified license conclusion',
  completeness: 'EXCERPT',
};
const materialCreated = await post('materials', materialRequest);
assert.equal(materialCreated.response.status, 201);
assert.equal(materialCreated.payload.result.revision, answerCreated.payload.result.revision + 1);
assert.equal(materialCreated.payload.result.previous_result_id, answerCreated.payload.result.result_id);
assert.equal(materialCreated.payload.result.formal_effect, 'none');
assert.equal(materialCreated.payload.material.verification_state, 'pending');
assert.equal(materialCreated.payload.material.adoption_status, 'adopted_as_unverified_observation');
assert.equal(materialCreated.payload.material.source_sha256, materialSha);
assert.equal(materialCreated.payload.material.formal_effect, 'none');

const materialReplay = await post('materials', materialRequest);
assert.equal(materialReplay.response.status, 201);
assert.equal(materialReplay.payload.result.result_id, materialCreated.payload.result.result_id);
assert.equal(materialReplay.payload.material.material_id, materialCreated.payload.material.material_id);

const receipt = {
  grade: 'LOOPBACK_TEST_ONLY_LIVE_WRITE_ACCEPTANCE',
  generated_at: new Date().toISOString(),
  base_url: baseUrl.toString(),
  binding,
  initial: {
    result_id: initial.result_id,
    revision: initial.revision,
    result_sha256: initial.result_sha256,
  },
  answer: answerCreated.payload.answer,
  conflict: stale.payload,
  material: materialCreated.payload.material,
  final: {
    result_id: materialCreated.payload.result.result_id,
    revision: materialCreated.payload.result.revision,
    result_sha256: materialCreated.payload.result.result_sha256,
    previous_result_id: materialCreated.payload.result.previous_result_id,
  },
  checks: [
    'answer 201',
    'answer same-key replay returned the same objects',
    'stale revision returned exact 409 conflict',
    'conflict was followed by a current-head reread',
    'material 201',
    'material same-key replay returned the same objects',
    'material remains pending and unverified',
    'all created objects have formal_effect none',
  ],
  requests: requestLog,
};
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8');
console.log(`P2_LIVE_WRITE_PASS initial_revision=${initial.revision} final_revision=${receipt.final.revision}`);
console.log(`P2_LIVE_RECEIPT=${outputPath}`);
}
