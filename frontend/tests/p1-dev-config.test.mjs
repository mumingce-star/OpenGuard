import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { loadConfigFromFile } from 'vite';

const root = fileURLToPath(new URL('../', import.meta.url));
const configPath = fileURLToPath(new URL('../vite.p1-dev.config.ts', import.meta.url));
async function config(values = {}, filename = configPath) {
  const names = ['OPENGUARD_P1_API_PORT', 'OPENGUARD_P1_WEB_PORT'];
  const before = Object.fromEntries(names.map(name => [name, process.env[name]]));
  try {
    for (const name of names) {
      if (values[name] === undefined) delete process.env[name];
      else process.env[name] = values[name];
    }
    const result = await loadConfigFromFile({ command: 'serve', mode: 'development' }, filename, root, 'silent');
    assert.ok(result);
    return result.config;
  } finally {
    for (const name of names) {
      if (before[name] === undefined) delete process.env[name];
      else process.env[name] = before[name];
    }
  }
}

test('P1 opt-in proxy preserves Origin and is strict loopback with the correct API base', async () => {
  const value = await config();
  for (const side of [value.server, value.preview]) {
    assert.equal(side.host, '127.0.0.1');
    assert.equal(side.port, 15174);
    assert.equal(side.strictPort, true);
    assert.equal(side.cors, false);
    assert.deepEqual(side.allowedHosts, ['127.0.0.1', 'localhost']);
    assert.equal(side.proxy['/api'].target, 'http://127.0.0.1:18011');
    assert.equal(side.proxy['/api'].changeOrigin, false);
  }
  assert.equal(value.define['import.meta.env.VITE_API_BASE_URL'], '"/api/v1"');
  assert.ok(value.plugins.flat().some(plugin => plugin.name === 'openguard-browser-licenses'));
});
test('the original Vite proxy stays at 8000 when P1 config is not selected', async () => {
  const value = await config({}, fileURLToPath(new URL('../vite.config.ts', import.meta.url)));
  assert.equal(value.server.proxy['/api'].target, 'http://127.0.0.1:8000');
  assert.equal(value.preview.proxy['/api'].target, 'http://127.0.0.1:8000');
  assert.equal(value.define?.['import.meta.env.VITE_API_BASE_URL'], undefined);
});
test('explicit alternative dev ports are supported without accepting an external URL', async () => {
  const value = await config({ OPENGUARD_P1_API_PORT: '18012', OPENGUARD_P1_WEB_PORT: '15175' });
  assert.equal(value.server.proxy['/api'].target, 'http://127.0.0.1:18012');
  assert.equal(value.server.port, 15175);
  await assert.rejects(config({ OPENGUARD_P1_API_PORT: 'https://example.com' }));
});
test('invalid, reserved and colliding ports fail instead of silently changing targets', async () => {
  for (const name of ['OPENGUARD_P1_API_PORT', 'OPENGUARD_P1_WEB_PORT']) {
    for (const bad of ['', '0', '1023', '65536', '1.5', ' 18011', '5174', '8000', '8011', '8080']) {
      await assert.rejects(config({ [name]: bad }));
    }
  }
  await assert.rejects(config({ OPENGUARD_P1_API_PORT: '18011', OPENGUARD_P1_WEB_PORT: '18011' }));
});
