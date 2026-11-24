import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {test} from 'node:test';

const root = new URL('../../../', import.meta.url);
const read = path => readFileSync(new URL(path, root), 'utf8');
const packageJson = process.env.OPENGUARD_TEST_YAML_PACKAGE_JSON;
assert.ok(packageJson, 'Set OPENGUARD_TEST_YAML_PACKAGE_JSON to the pinned yaml package');
const load = createRequire(packageJson);
assert.equal(load('./package.json').version, '2.9.0');
const {parse} = load('yaml');

test('Docker image pins Python, keeps runtime private and serves as non-root', () => {
  const file = read('Dockerfile');
  assert.match(file, /^FROM python:3\.12-slim\b/m);
  assert.match(file, /deployment\/requirements\.lock/);
  assert.match(file, /apt-get[^\n]*install[^\n]*--no-install-recommends[^\n]*\bgit\b/);
  assert.match(file, /\/var\/lib\/apt\/lists/);
  assert.match(file, /\/opt\/openguard-venv\/bin\/python/);
  assert.match(file, /\b0700\b[^\n]*\/app\/runtime/);
  assert.match(file, /^USER openguard\s*$/m);
  assert.match(file, /^HEALTHCHECK[^\n]*127\.0\.0\.1:8000\/healthz/m);
  assert.match(file, /^CMD \["\/opt\/openguard-venv\/bin\/python", "-B", "openguard\.py", "serve", "--host", "0\.0\.0\.0", "--port", "8000"\]\s*$/m);
});

test('Compose only publishes loopback and caps privileges', () => {
  const model = parse(read('docker-compose.yml'));
  const app = model.services.openguard;
  const hostPort = '${OPENGUARD_HOST_PORT:-8000}';
  assert.equal(app.build, '.');
  assert.deepEqual(app.ports, [`127.0.0.1:${hostPort}:8000`]);
  assert.deepEqual(app.volumes, ['openguard_runtime:/app/runtime']);
  assert.equal(app.environment.OPENGUARD_CONTAINER_MODE, '1');
  assert.equal(app.environment.OPENGUARD_PUBLIC_PORT, hostPort);
  assert.equal(app.environment.OPENGUARD_OLLAMA_DOCKER_HOST, '${OPENGUARD_OLLAMA_DOCKER_HOST:-0}');
  assert.deepEqual(app.extra_hosts, ['host.docker.internal:host-gateway']);
  assert.equal(app.init, true);
  assert.deepEqual(app.security_opt, ['no-new-privileges:true']);
  assert.equal(app.restart, 'unless-stopped');
  assert.ok(!('privileged' in app) && !('network_mode' in app));
  assert.ok(Object.hasOwn(model.volumes, 'openguard_runtime'));
});

test('Container context excludes private override and runtime files', () => {
  const ignores = read('.dockerignore').split(/\r?\n/);
  for (const path of [
    '.git', 'runtime', 'tmp-data', '**/__pycache__', '**/*.pyc', '**/.pytest_cache',
    'application/frontend/node_modules', '**/.DS_Store', '**/.env',
  ]) assert.ok(ignores.includes(path), path);
  assert.ok(!ignores.includes('web'));
});

test('CI has read-only permissions and runs the three requested paths', () => {
  const input = read('.github/workflows/openguard-ci.yml');
  const workflow = parse(input);
  assert.deepEqual(workflow.permissions, {contents: 'read'});
  assert.deepEqual(workflow.on.push.branches, ['feat/**', 'release/**', 'main']);
  assert.ok(Object.hasOwn(workflow.on, 'pull_request') && Object.hasOwn(workflow.on, 'workflow_dispatch'));
  assert.ok(!Object.hasOwn(workflow.on, 'pull_request_target'));
  assert.doesNotMatch(input, /secrets\s*\.|ghp_[A-Za-z0-9]+|BEGIN [A-Z ]*PRIVATE KEY/);
  const python = workflow.jobs['cross-platform-python-and-selftest'];
  assert.deepEqual(python.strategy.matrix.os, ['ubuntu-latest', 'macos-latest']);
  assert.equal(python['runs-on'], '${{ matrix.os }}');
  const run = job => job.steps.map(step => step.run ?? '').join('\n');
  assert.match(run(python), /openguard\.py check/);
  assert.match(run(python), /openguard\.py self-test/);
  assert.match(run(python), /pytest/);
  const front = run(workflow.jobs['frontend-node-and-build']);
  for (const command of ['pnpm install --frozen-lockfile', 'tsc', 'test', 'vite build']) assert.ok(front.includes(command), command);
  const dockerJob = workflow.jobs['docker-build-and-smoke'];
  const docker = run(dockerJob);
  for (const command of ['docker build', 'id -u', 'openguard.py self-test', '127.0.0.1:18000', '/healthz', 'docker stop', 'State.ExitCode']) assert.ok(docker.includes(command), command);
  const smoke = dockerJob.steps.find(step => step.name === 'Check the mapped HTTP endpoints and graceful stop');
  assert.ok(smoke);
  const script = smoke.run.replace(/\\\r?\n\s*/g, ' ');
  assert.match(script, /docker run[^)\n]* -e OPENGUARD_PUBLIC_PORT=18000\s+--publish 127\.0\.0\.1:18000:8000/);
  assert.match(script, /status=\$\(curl --noproxy '\*' --silent --max-time 5 -H 'Host: evil\.example:18000' --output \/dev\/null --write-out '%\{http_code\}' http:\/\/127\.0\.0\.1:18000\/healthz\)\s+test "\$status" = 403/);
});
