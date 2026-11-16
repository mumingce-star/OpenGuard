// Run against a local built preview: node tests/hero-motion-smoke.cjs http://127.0.0.1:4194/
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { existsSync, mkdtempSync, readFileSync, writeFileSync } = require('node:fs');
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
    const capture = async name => {
      if (!process.env.HERO_REVIEW_DIR) return;
      const result = await send('Page.captureScreenshot', { format: 'png' });
      writeFileSync(join(process.env.HERO_REVIEW_DIR, name), Buffer.from(result.data, 'base64'));
    };
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
    await capture('home-390.png');
    assert.ok(await evaluate('window.__particleFrames') > 0);
    const settled = await evaluate('window.__particleFrames');
    await pause(300);
    assert.ok(await evaluate('window.__particleFrames') > settled, 'brand animation stopped unexpectedly');
    await evaluate(`(() => {
      const canvas = document.querySelector('.particle-text');
      window.__brandBaseline = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      const rect = canvas.getBoundingClientRect();
      canvas.dispatchEvent(new PointerEvent('pointermove', {
        bubbles: true, pointerType: 'mouse',
        clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2,
      }));
    })()`);
    await pause(350);
    const hoverDifference = await evaluate(`(() => {
      const canvas = document.querySelector('.particle-text');
      const current = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let difference = 0;
      for (let i = 0; i < current.length; i++) difference += Math.abs(current[i] - window.__brandBaseline[i]);
      return difference;
    })()`);
    assert.ok(hoverDifference > 1000, `brand did not respond to pointer: ${hoverDifference}`);
    await evaluate("document.querySelector('.particle-text').dispatchEvent(new PointerEvent('pointerleave',{pointerType:'mouse'}))");
    await pause(800);
    const leaveDifference = await evaluate(`(() => {
      const canvas = document.querySelector('.particle-text');
      const current = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      let difference = 0;
      for (let i = 0; i < current.length; i++) difference += Math.abs(current[i] - window.__brandBaseline[i]);
      return difference;
    })()`);
    assert.ok(leaveDifference < hoverDifference, 'brand particles did not return after pointer leave');
    const checkCtas = async width => {
      const layout = await evaluate(`(() => {
        const buttons = [...document.querySelectorAll('.landing-home .hero-actions .hero-cta')];
        const rects = buttons.map(button => button.getBoundingClientRect());
        return { count: buttons.length, widths: rects.map(rect => rect.width),
          tops: rects.map(rect => rect.top), scrollWidth: document.documentElement.scrollWidth };
      })()`);
      assert.equal(layout.count, 2, 'homepage should show two CTAs');
      assert.equal(layout.scrollWidth, width, `${width}px homepage overflowed`);
      assert.ok(Math.abs(layout.tops[0] - layout.tops[1]) < 2, `${width}px CTAs are not side by side`);
      assert.ok(layout.widths.every(value => value < 200), `${width}px CTAs are too wide`);
    };
    const checkBrandMargins = async width => {
      const margins = await evaluate(`(() => {
        const canvas = document.querySelector('.particle-text');
        const { width, height } = canvas;
        const pixels = canvas.getContext('2d').getImageData(0, 0, width, height).data;
        let left = width, right = 0, top = height, bottom = 0;
        for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
          if (pixels[(y * width + x) * 4 + 3] < 32) continue;
          left = Math.min(left, x); right = Math.max(right, x);
          top = Math.min(top, y); bottom = Math.max(bottom, y);
        }
        return { left, right: width - 1 - right, top, bottom: height - 1 - bottom };
      })()`);
      assert.ok(Object.values(margins).every(value => value >= 4), `${width}px brand touched canvas edge: ${JSON.stringify(margins)}`);
    };
    await checkCtas(390);
    await checkBrandMargins(390);
    await send('DOM.enable');
    await send('CSS.enable');
    const root = (await send('DOM.getDocument')).root.nodeId;
    for (const selector of ['.hero-cta-primary', '.hero-cta-secondary']) {
      const nodeId = (await send('DOM.querySelector', { nodeId: root, selector })).nodeId;
      const initial = await evaluate(`(() => {
        const button = document.querySelector('${selector}');
        const circle = button.querySelector('.circle');
        const arrow = button.querySelector('.icon.arrow');
        return { buttonWidth: button.getBoundingClientRect().width,
          circleWidth: circle.getBoundingClientRect().width,
          circleColor: getComputedStyle(circle).backgroundColor,
          arrowColor: getComputedStyle(arrow).backgroundColor,
          chevron: getComputedStyle(arrow, '::before').borderTopWidth,
          textColor: getComputedStyle(button.querySelector('.button-text')).color };
      })()`);
      assert.ok(Math.abs(initial.circleWidth - 44) < 1, `${selector} circle has wrong default size`);
      assert.equal(parseFloat(initial.chevron), 2, `${selector} chevron is missing`);
      assert.equal(initial.arrowColor, 'rgba(0, 0, 0, 0)', `${selector} should start as a chevron`);
      assert.ok((initial.circleColor.match(/\d+/g) || []).slice(0, 3).every(value => Number(value) > 190), `${selector} circle is too dark`);
      await send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: ['hover'] });
      await pause(550);
      const hovered = await evaluate(`(() => {
        const button = document.querySelector('${selector}');
        const circle = button.querySelector('.circle');
        const arrow = button.querySelector('.icon.arrow');
        return { circleWidth: circle.getBoundingClientRect().width,
          circleColor: getComputedStyle(circle).backgroundColor,
          arrowColor: getComputedStyle(arrow).backgroundColor,
          arrowTransform: getComputedStyle(arrow).transform,
          textColor: getComputedStyle(button.querySelector('.button-text')).color };
      })()`);
      assert.ok(Math.abs(hovered.circleWidth - initial.buttonWidth) < 3, `${selector} circle did not expand across button`);
      assert.notEqual(hovered.circleColor, initial.circleColor, `${selector} circle color did not change`);
      assert.notEqual(hovered.arrowColor, initial.arrowColor, `${selector} chevron did not become an arrow`);
      assert.ok(hovered.arrowTransform.includes('16'), `${selector} arrow did not translate`);
      assert.notEqual(hovered.textColor, initial.textColor, `${selector} text color did not change`);
      if (selector === '.hero-cta-primary') await capture('home-390-hover.png');
      await send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: [] });
      await send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: ['focus-visible'] });
      await pause(550);
      assert.ok(Math.abs(parseFloat(await evaluate(`getComputedStyle(document.querySelector('${selector} .circle')).width`)) - initial.buttonWidth) < 3, `${selector} keyboard focus did not expand the circle`);
      await send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: [] });
    }
    await send('Emulation.setDeviceMetricsOverride', { width: 320, height: 844, deviceScaleFactor: 1, mobile: true });
    await pause(150);
    await checkCtas(320);
    await checkBrandMargins(320);
    await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
    await pause(150);
    await checkCtas(1440);
    await checkBrandMargins(1440);
    await capture('home-1440.png');
    await send('Emulation.setDeviceMetricsOverride', { width: 400, height: 844, deviceScaleFactor: 1, mobile: true });
    await pause(350);
    const afterResize = await evaluate('window.__particleFrames');
    assert.ok(afterResize > settled, 'resize did not redraw the brand');

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
    assert.ok(parseFloat(await evaluate("getComputedStyle(document.querySelector('.hero-cta .circle')).transitionDuration")) < .001, 'reduced motion kept the CTA transition');
    const reducedBrand = await evaluate("document.querySelector('.particle-text').toDataURL()");
    await evaluate(`(() => {
      const canvas = document.querySelector('.particle-text');
      const rect = canvas.getBoundingClientRect();
      canvas.dispatchEvent(new PointerEvent('pointermove', {
        pointerType: 'mouse', clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2,
      }));
    })()`);
    await pause(150);
    assert.equal(await evaluate("document.querySelector('.particle-text').toDataURL()"), reducedBrand, 'reduced motion still animates the brand');
    socket.close();
    process.stdout.write('hero motion smoke passed\n');
  } finally { chrome.kill(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
