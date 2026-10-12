// 只读采证入口：不扫描、不联网、不执行来源代码；输出必须为不存在的新文件。
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.argv[2];
if (!output || existsSync(resolve(output))) throw new Error('必须提供尚不存在的新回执路径');
const sha = raw => createHash('sha256').update(raw).digest('hex');
const raw = path => readFileSync(join(root, path));
const load = path => JSON.parse(raw(path));
const sorted = value => Array.isArray(value) ? value.map(sorted) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, sorted(value[key])])) : value;
const canonical = value => sha(JSON.stringify(sorted(value)));
const git = args => execFileSync('git', args, { cwd: root, timeout: 20_000, maxBuffer: 16 * 1024 * 1024,
  env: { ...process.env, GIT_NO_LAZY_FETCH: '1', GIT_NO_REPLACE_OBJECTS: '1' } });
const utf8 = bytes => new TextDecoder('utf-8', { fatal: true }).decode(bytes);
const pointer = (object, path) => path.split('/').slice(1).reduce((v, token) => v[token.replaceAll('~1', '/').replaceAll('~0', '~')], object);
const checks = [], commands = [], sections = {};
const check = (name, valid) => checks.push({ name, status: valid ? 'PASS' : 'FAIL' });
const section = (name, action) => { try { sections[name] = action(); } catch (e) { checks.push({ name, status: 'FAIL', error: e.message }); } };
const command = (path, args = []) => {
  try { const stdout = execFileSync(process.execPath, [join(root, path), ...args], { cwd: root, timeout: 60_000, encoding: 'utf8' });
    commands.push({ command: ['node', path, ...args], exit_code: 0, stdout: stdout.trim() });
  } catch (e) { commands.push({ command: ['node', path, ...args], exit_code: e.status, status: 'FAIL' }); check(path, false); }
};
const base = 'tests/fixtures/notice-license-facts-v3';
const revision = `${base}/revisions/source-binding-r2`;
const historical = 'docs/p1/p1-b-offline-audit-20261011.json';
const protectedPaths = [historical, `${base}/facts.json`, `${revision}/facts.json`, `${revision}/amendment.json`, `${revision}/manifest.json`];
const before = Object.fromEntries(protectedPaths.map(path => [path, sha(raw(path))]));
const audit = load(historical);

section('git', () => ({ head: utf8(git(['rev-parse', 'HEAD'])).trim(),
  branch: utf8(git(['branch', '--show-current'])).trim(),
  cached_refs: Object.fromEntries(['origin/codex/scan-reliability-integration', 'origin/integration/p1', 'main', 'origin/main']
    .map(ref => [ref, utf8(git(['rev-parse', ref])).trim()])),
  containing_refs: Object.fromEntries(['09c61cb', '8f9db3c'].map(commit => [utf8(git(['rev-parse', commit])).trim(),
    utf8(git(['branch', '-a', '--contains', commit])).trim().split('\n').map(v => v.trim().replace(/^\* /, ''))])),
  remote_verified_this_run: false }));

command(`${base}/generate.mjs`, ['--check']);
section('b03', () => {
  const manifest = load(`${revision}/manifest.json`), amendment = load(`${revision}/amendment.json`);
  const current = load(`${revision}/facts.json`), old = load(`${base}/facts.json`);
  const sourceBytes = new Map(), sources = [];
  check('source_commit为固定commit', /^[a-f0-9]{40}$/.test(manifest.source_commit) && utf8(git(['cat-file', '-t', manifest.source_commit])).trim() === 'commit');
  for (const source of manifest.sources) {
    if (!/^[a-zA-Z0-9_./-]+$/.test(source.path) || source.path.split('/').includes('..')) throw new Error('不安全来源路径');
    const entry = utf8(git(['ls-tree', '-z', source.source_commit, '--', source.path]));
    const bytes = git(['show', `${source.source_commit}:${source.path}`]);
    const valid = /^100(?:644|755) blob /.test(entry) && bytes.length === source.size_bytes && sha(bytes) === source.sha256;
    check(`Git来源:${source.path}`, valid);
    sourceBytes.set(source.path, bytes);
    sources.push({ ...source, actual_file_sha256: sha(bytes), actual_size_bytes: bytes.length, status: valid ? 'PASS' : 'FAIL' });
  }
  for (const path of ['facts.json', 'amendment.json', 'manifest.json']) {
    check(`修订与已发布Git工件字节一致:${path}`, sha(raw(`${revision}/${path}`)) === sha(git(['show', `8f9db3c:${revision}/${path}`])));
  }
  const tag = (block, name) => new RegExp(`<${name}>([^<]*)</${name}>`).exec(block)?.[1] ?? null;
  const evidence = current.evidence.map(item => {
    const bytes = sourceBytes.get(item.source_path); if (!bytes) throw new Error('来源未闭包');
    let selected;
    if (item.content_scope === 'whole_file') selected = bytes;
    else if (item.content_scope === 'json_pointer_value') {
      const value = pointer(JSON.parse(utf8(bytes)), item.selected_json_pointer);
      selected = typeof value === 'string' ? value : JSON.stringify(value);
    } else if (item.content_scope === 'toml_declaration') {
      // 仅复算这些固定fixture中的显式数组，不做一般TOML解析或依赖求解。
      const name = item.evidence_id.split('.').at(-1), text = utf8(bytes);
      const development = item.locator.includes('optional-dependencies');
      const block = development ? text.split('[project.optional-dependencies]')[1]?.split(/\n\[/)[0]
        : text.split('[project]')[1]?.split(/\n\[/)[0];
      const array = new RegExp(`${development ? 'dev' : 'dependencies'}\\s*=\\s*\\[([\\s\\S]*?)\\]`).exec(block)?.[1];
      if (!array) throw new Error('固定TOML数组缺失');
      const values = [...array.matchAll(/"(?:\\.|[^"\\])*"/g)].map(v => JSON.parse(v[0]));
      const matches = values.filter(v => v.split('==')[0] === name);
      if (matches.length !== 1) throw new Error('固定声明不唯一');
      selected = JSON.stringify({ section: development ? 'development' : 'runtime', declaration: matches[0] });
    } else if (item.content_scope === 'xml_dependency') {
      const text = utf8(bytes), name = item.evidence_id.split('.').at(-1);
      const dependencies = /<dependencies>([\s\S]*?)<\/dependencies>/.exec(text)?.[1];
      const matches = [...(dependencies ?? '').matchAll(/<dependency>([\s\S]*?)<\/dependency>/g)].filter(v => tag(v[1], 'artifactId') === name);
      if (matches.length !== 1) throw new Error('固定XML声明不唯一');
      const block = matches[0][1]; let version = tag(block, 'version');
      if (version?.startsWith('${') && version.endsWith('}')) version = tag(/<properties>([\s\S]*?)<\/properties>/.exec(text)?.[1] ?? '', version.slice(2, -1));
      selected = JSON.stringify({ group_id: tag(block, 'groupId'), artifact_id: name, version, scope: tag(block, 'scope') });
    } else throw new Error('不支持的固定hash范围');
    const selectedHash = sha(selected), sourceHash = sha(bytes);
    check(`Evidence来源及选定字段:${item.evidence_id}`, sourceHash === item.source_file_sha256 && selectedHash === item.selected_content_sha256);
    return { ...item, git_blob_revision: manifest.source_commit, actual_source_file_sha256: sourceHash, actual_selected_content_sha256: selectedHash,
      prior_source_file_sha256: old.evidence.find(v => v.evidence_id === item.evidence_id)?.source_file_sha256 };
  });
  const changed = evidence.filter(v => v.prior_source_file_sha256 !== v.source_file_sha256);
  check('8条受影响Evidence与amendment一致', canonical(changed.map(v => v.evidence_id).sort()) === canonical(amendment.affected_evidence.map(v => v.evidence_id).sort()) && changed.length === 8);
  check('31事实及report行语义未改', canonical(old.facts) === canonical(current.facts) && canonical(old.report_v3_rows) === canonical(current.report_v3_rows));
  check('选定内容Hash未改', current.evidence.every(v => old.evidence.find(o => o.evidence_id === v.evidence_id)?.selected_content_sha256 === v.selected_content_sha256));
  for (const [label, packageObject, parent] of [['old', old, amendment.parent], ['r2', current, amendment.replacement]]) {
    check(`${label}:file与canonical独立匹配`, before[parent.artifact] === parent.file_sha256 && canonical(packageObject) === parent.canonical_package_sha256 && parent.file_sha256 !== parent.canonical_package_sha256);
  }
  check('独立审核/真人/A读回保持null', amendment.independent_review === null && amendment.human_approval === null && amendment.a_terminal_readback === null && manifest.independent_review === null && manifest.a_terminal_readback === null);
  const rows = current.facts.map(fact => {
    const ids = [...new Set([...fact.fact_provenance_evidence_ids, ...Object.values(fact.relationships).flatMap(v => v.evidence_ids)])];
    check(`事实引用闭包:${fact.fact_id}`, ids.every(id => evidence.some(e => e.evidence_id === id)) && fact.authorization_status === 'pending' && fact.license_expression_id === null);
    return { fact_id: fact.fact_id, subject: fact.subject, fact_sha256: canonical(fact), package_sha256: canonical(current),
      evidence_ids: ids, relationships: fact.relationships, gaps: fact.gaps, inventory: null, a_terminal: null, assessment: null, notice_bound: null, draft_report: null };
  });
  return { source_commit: manifest.source_commit, sources, evidence, rows, affected_evidence_ids: changed.map(v => v.evidence_id),
    old: amendment.parent, current: amendment.replacement, old_state: 'historical_source_binding_defect',
    current_state: 'offline_machine_verified_pending_independent_review_and_A_admission', independent_review: null, a_terminal_readback: null,
    historical_audit_tool: { path: 'benchmarks/p1_b_offline_audit.py', sha256: sha(raw('benchmarks/p1_b_offline_audit.py')),
      reads_retained_old_v3: true, use: '仅历史缺陷盘点；不是r2当前可信输入入口' } };
});

section('b01_b02', () => {
  const profiles = [];
  for (const [provider, version] of [['huggingface', 'v1'], ['huggingface', 'v2'], ['modelscope', 'v1']]) {
    const directory = `tests/fixtures/${provider}/resource-profile-${version}`, path = `${directory}/manifest.json`, manifest = load(path);
    for (const record of [...manifest.records, ...(manifest.counterexamples ?? [])]) {
      const file = `${directory}/${record.fixture}`, bytes = raw(file), body = JSON.parse(utf8(bytes)), old = audit.profiles.find(v => v.provider === provider && v.fixture_version === version && v.case_id === record.case_id);
      const observed = record.observed;
      const identityValid = !observed || (provider === 'huggingface' ? body.payload.id === observed.canonical_id && (body.payload.sha ?? null) === (observed.revision ?? null)
        : `${body.payload.Data.Namespace}/${body.payload.Data.Name}` === observed.canonical_id);
      check(`Profile:${provider}:${version}:${record.case_id}`, identityValid && sha(bytes) === record.source_file_sha256 && sha(bytes) === old?.source_file_sha256 && sha(raw(path)) === old?.manifest_sha256);
      profiles.push({ ...old, path: file, independent_receipt: null, independent_state: '待签收' });
    }
  }
  const v2Path = 'tests/fixtures/notice-license-facts-v2/facts.json', v2 = load(v2Path), expected = load('tests/fixtures/p1-integration-b-v1/expected.json');
  check('B02仅固定v2 pin', canonical(v2) === expected.source_package_sha256);
  for (const c of audit.fact_chain.candidates) {
    const fact = v2.facts.find(v => v.fact_id === c.fact_id);
    check(`历史候选绑定:${c.candidate_id}`, c.source_package_sha256 === canonical(v2) && c.source_fact_sha256 === canonical(fact)
      && pointer(v2, c.source_fact_pointer) !== undefined && c.authorization_status === 'pending' && c.status === 'review_required' && c.confirmed_violation === false
      && c.evidence_bindings.every(e => pointer(v2, e.evidence_pointer)?.evidence_id === e.evidence_id));
  }
  return { profiles, v2_file_sha256: sha(raw(v2Path)), v2_canonical_package_sha256: canonical(v2),
    candidate_count: audit.fact_chain.candidates.length, obligation_count: audit.fact_chain.v2_obligations,
    zero_candidate_fact_ids: audit.fact_chain.rows.filter(v => v.version === 'v2' && !v.candidate_ids.length).map(v => v.fact_id),
    candidate_detector_executed_this_run: false, mode: '复核已保存候选引用和hash，不代替Python检测器执行', v3_as_v2: false, notice_source_as_v3: false };
});

section('b05_b06', () => {
  const directory = 'benchmarks/results/local/auto-static-20261006-r7', run = 'baseline_v5_audit';
  const freeze = load(`${directory}/freeze.json`), receipt = load(`${directory}/runs/${run}.json`), queue = load(`${directory}/review-train-dev-v1.json`);
  const hashes = Object.fromEntries(['catalog.json', 'freeze.json', `runs/${run}.json`, `metrics/${run}.json`, 'review-train-dev-v1.json'].map(path => [path, sha(raw(`${directory}/${path}`))]));
  check('Bench冻结和历史审计摘要闭包', hashes['catalog.json'] === freeze.catalog_sha256 && hashes['freeze.json'] === receipt.freeze_sha256
    && hashes[`metrics/${run}.json`] === receipt.metrics_sha256 && hashes['review-train-dev-v1.json'] === audit.sources.saved_queue_sha256
    && hashes[`runs/${run}.json`] === audit.sources.receipt_sha256 && hashes[`metrics/${run}.json`] === audit.sources.metrics_sha256);
  let trainDevDuplicateGroups = 0;
  const verified = [];
  for (const sample of freeze.samples) {
    const result = receipt.sample_results.find(v => v.sample_id === sample.sample_id);
    check(`采集台账:${sample.sample_id}`, result?.split === sample.split && result?.input_sha256 === sample.input_sha256);
    if (sample.state === 'failed') {
      check(`失败不删除:${sample.sample_id}`, !!sample.failure && result.status === 'failed' && result.failure === 'collection_failed' && !existsSync(join(root, directory, 'snapshots', `${sample.sample_id}.zip`)));
    } else {
      const path = `${directory}/snapshots/${sample.sample_id}.zip`;
      check(`固定归档:${sample.sample_id}`, sha(raw(path)) === sample.input_sha256);
      // holdout只核整体归档Hash，不解析或解压个案/标签。
      if (sample.split === 'holdout') continue;
      const predictionPath = `${directory}/predictions/${run}/${sample.sample_id}.json`, goldPath = `${directory}/gold/${sample.sample_id}.json`;
      check(`train/dev artifact:${sample.sample_id}`, sha(raw(predictionPath)) === result.prediction_sha256 && sha(raw(goldPath)) === result.gold_sha256);
      const prediction = load(predictionPath), counts = new Map();
      for (const label of prediction.labels) {
        const key = JSON.stringify([label.locator, label.line, label.resource_type, label.provider, label.name, label.evidence_sha256]);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      trainDevDuplicateGroups += [...counts.values()].filter(v => v > 1).length;
      verified.push({ sample_id: sample.sample_id, input_sha256: sample.input_sha256, prediction_sha256: result.prediction_sha256, gold_sha256: result.gold_sha256 });
    }
  }
  check('30来源/25fixed/5失败保留', freeze.samples.length === 30 && freeze.samples.filter(v => v.state === 'fixed').length === 25 && freeze.samples.filter(v => v.state === 'failed').length === 5);
  check('314分歧及14组train/dev重复保留', queue.cases.length === 314 && queue.cases.every(v => ['train', 'dev'].includes(v.split) && v.adjudication === null)
    && trainDevDuplicateGroups === queue.repeated_match_keys.length && trainDevDuplicateGroups === 14
    && audit.sources.cases.every(v => v.human_adjudication === null && v.confirmed_detector_error === false));
  const blindPath = 'docs/p1/p1-b-blind-source-packet-20261011.json', templatePath = 'docs/p1/p1-b-human-review-template-20261011.json';
  const blind = load(blindPath), template = load(templatePath);
  const allowed = new Set(['case_id', 'commit_sha', 'evidence_sha256', 'input_sha256', 'judgment', 'locator', 'source_repository']);
  check('224入口无答案/模板未签', blind.records.length === 224 && blind.records.every(v => Object.keys(v).every(k => allowed.has(k)) && v.judgment === null)
    && template.records.length === 0 && Object.values(template.reviewer).every(v => v === null) && template.submitted_at === null);
  return { hashes, sample_count: 30, fixed_count: 25, failed_count: 5, train_dev_artifacts: verified,
    repeated_train_dev_groups: trainDevDuplicateGroups, historical_all_split_repeated_count: audit.sources.integrity.repeated_match_keys,
    all_split_repeat_count_recomputed_this_run: false, machine_disagreements: 314, machine_kinds: audit.sources.machine_kinds,
    confirmed_detector_errors: 0, adjudication_pending: 314, source_line_check: '复用旧审计逐行核验；本轮固定归档/artifact/queue摘要重新闭包，未重解压或重裁决',
    blind_packet: { path: blindPath, sha256: sha(raw(blindPath)), count: 224 }, template: { path: templatePath, sha256: sha(raw(templatePath)) },
    old_holdout_exposed: true, holdout_cases_parsed_this_run: false, new_holdout: null, formal_gold: false, formal_metrics: null };
});

section('notice_failure', () => {
  const path = 'docs/p2/evidence/baseline-notice-comparison.xml', xml = utf8(raw(path));
  const receipt = load('docs/p2/test-receipt.json'), runtime = load('docs/p2/runtime-receipt.json');
  const testPath = 'tests/unit/test_p1_notice_draft_production_wiring.py', modelPath = 'backend/app/notice_source/models.py';
  check('两条原始JUnit完整摘要', sha(raw(path)) === receipt.baseline_notice.sha256 && receipt.baseline_notice.nodes.length === 2 && xml.includes('excerpt_content_invalid'));
  check('当前夹具与失败父本字节一致', sha(raw(testPath)) === sha(git(['show', `${receipt.baseline}:${testPath}`])));
  check('当前严格内容模型与父本一致', sha(raw(modelPath)) === sha(git(['show', `${receipt.baseline}:${modelPath}`])));
  return { classification: '历史Linux业务校验失败；不是本轮Windows setup错误', baseline_sha: receipt.baseline,
    fixture_introducing_commit: utf8(git(['log', '-1', '--format=%H %P', '--', testPath])).trim(), fixture_path: testPath,
    fixture_sha256: sha(raw(testPath)), model_path: modelPath, model_sha256: sha(raw(modelPath)),
    junit: { path, sha256: sha(raw(path)), nodes: receipt.baseline_notice.nodes, timestamp: /timestamp="([^"]+)"/.exec(xml)?.[1], failure: 'observations.0.content: excerpt_content_invalid; fixture line 179' },
    historical_environment: { image: runtime.container_image, network: runtime.network, rootfs: runtime.rootfs, uid: runtime.uid,
      limits: runtime.limits, python_exact_version: null, kernel: null, environment_note: '未获得完整解释器/内核证明，不能从镜像摘要猜测' },
    fixture_defect: 'excerpt分支未设置excerpt_bytes_sha256；须等于retained_bytes_sha256。whole原始Hash继续保留。',
    owner: 'A生产接线测试维护方；B不覆盖其夹具', fixed_this_run: false, business_test_rerun: false,
    proposed_negative_cases: ['excerpt Hash缺失/错值拒绝', '坏UTF-8/字节范围错配/retained篡改拒绝', '非ASCII合法excerpt与原whole独立Hash通过'],
    owner_accepted_deferred_notes: ['N2=DEFERRED_NONBLOCKING', 'N3=DEFERRED_SECURITY_HARDENING'] };
});

command('benchmarks/taxonomies/validate-b06-fn-fp-taxonomy.mjs', ['benchmarks/taxonomies/b06-fn-fp-taxonomy.json']);
command('benchmarks/taxonomies/validate-b06-rule-improvement-ledger.mjs', ['benchmarks/taxonomies/b06-fn-fp-taxonomy.json', 'benchmarks/taxonomies/b06-rule-improvement-ledger.json']);
for (const path of protectedPaths) check(`历史/修订工件未写:${path}`, before[path] === sha(raw(path)));
const failed = checks.filter(v => v.status === 'FAIL').length;
const result = { schema: 'openguard.p1-b-evidence-followup/1', status: 'PARTIAL', generated_at: new Date().toISOString(),
  verification_kind: 'OFFLINE_MACHINE_SAME_AGENT_NOT_INDEPENDENT_ACCEPTANCE', environment: { platform: process.platform, node: process.version },
  reading_gate: { satisfied: false, reason: '历史日志/进度未完整逐字阅读；仅安全只读盘点及记录，无产品修改' },
  verification_entry: { path: 'docs/p1/p1-b-evidence-followup-20261012.mjs', sha256: sha(raw('docs/p1/p1-b-evidence-followup-20261012.mjs')) },
  source_artifacts_before_sha256: before, checks, commands, sections,
  synthetic_tests: null, new_real_P1_chain: null, independent_acceptance: null, formal_metrics: null, formal_performance: null,
  receipt_checks: { pass: checks.length - failed, fail: failed, not_pytest_counts: true },
  publishing: { authorized: false, committed: false, pushed: false } };
writeFileSync(resolve(output), `${JSON.stringify(result, null, 2)}\n`, { flag: 'wx' });
console.log(JSON.stringify({ output, pass: checks.length - failed, fail: failed, status: result.status }));
process.exitCode = failed ? 1 : 0;
