import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const require = createRequire(import.meta.url);
const proxy = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } };
// Preserve complete licenses from the installed, locked browser dependencies.
function browserLicenses() {
  const reactDomRequire = createRequire(require.resolve('react-dom/package.json'));
  return ['react', 'react-dom', 'scheduler', 'tailwindcss'].map((name) => {
    const resolver = name === 'scheduler' ? reactDomRequire : require;
    const manifest = resolver.resolve(`${name}/package.json`);
    const { version } = JSON.parse(readFileSync(manifest, 'utf8'));
    const license = readFileSync(join(dirname(manifest), 'LICENSE'), 'utf8');
    return `${name}@${version}\nhttps://www.npmjs.com/package/${name}/v/${version}\n\n${license}`;
  }).join('\n\n---\n\n');
}
export default defineConfig({
  plugins: [tailwindcss(), {
    name: 'openguard-browser-licenses',
    apply: 'build',
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'third-party-licenses.txt', source: browserLicenses() });
    },
    transformIndexHtml() {
      return [{ tag: 'link', attrs: { rel: 'license', href: './third-party-licenses.txt' }, injectTo: 'head' }];
    },
  }],
  server: { proxy },
  preview: { proxy },
});
