// Run against a local built preview: node tests/hero-motion-smoke.cjs http://127.0.0.1:4194/
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { existsSync, mkdtempSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { setTimeout: pause } = require('node:timers/promises');

async function main() {
  const chromePath = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const preview = process.argv[2] || 'http://127.0.0.1:4194/';
  const profile = mkdtempSync(join(tmpdir(), 'og-hero-smoke-'));
  const chrome = spawn(chromePath, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore', windowsHide: true });
  try {
    const portFile = join(profile, 'DevToolsActivePort');
    for (let i = 0; !existsSync(portFile) && i < 80; i++) await pause(100);
    assert.ok(existsSync(portFile), 'Chrome debugging port did not start');
    const port = readFileSync(portFile, 'utf8').split('\n')[0];
    const pages = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    const socket = new WebSocket(pages.find(page => page.type === 'page').webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let sequence = 0;
    const pending = new Map();
    socket.onmessage = ({ data }) => {
      const event = JSON.parse(data);
      if (!event.id || !pending.has(event.id)) return;
      const { resolve, reject } = pending.get(event.id);
      pending.delete(event.id);
      event.error ? reject(Error(event.error.message)) : resolve(event.result);
    };
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++sequence;
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
    const evaluate = async expression => (await send('Runtime.evaluate', { expression, returnByValue: true })).result.value;
    await send('Page.enable');
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `
      window.__particleFrames = 0;
      const clear = CanvasRenderingContext2D.prototype.clearRect;
      CanvasRenderingContext2D.prototype.clearRect = function (...args) {
        if (this.canvas.classList.contains('particle-text')) window.__particleFrames++;
        return clear.apply(this, args);
      };
    ` });
    await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await send('Page.navigate', { url: preview });
    await pause(1300);
    assert.equal(await evaluate('document.documentElement.scrollWidth'), 390);
    assert.ok(await evaluate('window.__particleFrames') > 0);
    const settled = await evaluate('window.__particleFrames');
    await pause(300);
    assert.equal(await evaluate('window.__particleFrames'), settled, 'particle canvas kept drawing after settling');
    await send('Emulation.setDeviceMetricsOverride', { width: 400, height: 844, deviceScaleFactor: 1, mobile: true });
    await pause(350);
    const afterResize = await evaluate('window.__particleFrames');
    assert.ok(afterResize > settled, 'resize did not redraw the brand');
    await pause(300);
    assert.equal(await evaluate('window.__particleFrames'), afterResize, 'resize restarted the animation');

    await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await send('Page.reload');
    await pause(1000);
    await evaluate("document.querySelector('.evidence-scene').dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerType:'mouse',clientX:250,clientY:420}))");
    const beforePause = await evaluate("document.querySelector('.evidence-scene').style.getPropertyValue('--glass-tilt-y')");
    assert.ok(beforePause, 'mouse tilt did not respond while playing');
    await evaluate("document.querySelector('.evidence-scene-toggle').click()");
    await evaluate("document.querySelector('.evidence-scene').dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerType:'mouse',clientX:20,clientY:420}))");
    assert.equal(await evaluate("document.querySelector('.evidence-scene').style.getPropertyValue('--glass-tilt-y')"), beforePause, 'paused scene still tilted');

    await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
    await pause(100);
    assert.equal(await evaluate("document.querySelector('.evidence-scene').style.getPropertyValue('--glass-tilt-y')"), '', 'reduced motion kept the previous tilt');
    assert.equal(await evaluate("document.querySelector('.evidence-scene-toggle')"), null, 'reduced motion kept the play control');
    socket.close();
    process.stdout.write('hero motion smoke passed\n');
  } finally { chrome.kill(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
