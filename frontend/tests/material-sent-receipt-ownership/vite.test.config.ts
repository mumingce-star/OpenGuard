import { defineConfig } from 'vite';
import { existsSync, realpathSync } from 'node:fs';
import { dirname, isAbsolute, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

/** FUTURE APPROVED RUNNER ONLY. Prepared as text, not imported/executed here.
 * File checks and closed fetch do not provide native network/write isolation. */
const here = dirname(fileURLToPath(import.meta.url));
const declared = process.env.OPENGUARD_SENT_RECEIPT_TASK;
if (!declared || !isAbsolute(declared)) throw Error('Explicit approved TASK required');
const task = realpathSync(declared);
if (realpathSync(join(here, '../..')) !== task) throw Error('Configuration not inside the declared TASK');
const source = realpathSync(join(task, '../p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend'));
// The established snapshot remains the only product/24-test source. Never use
// the Owner root or create another 178-file tree. Recheck frozen hashes first.
if (!source.endsWith('/p2-receiver-snapshot-20261020T140609Z/receiver/source/frontend')) throw Error('Unexpected frozen source root');
const depsDeclared = process.env.OPENGUARD_APPROVED_FRONTEND_DEPENDENCIES;
if (!depsDeclared || !isAbsolute(depsDeclared)) throw Error('Existing compatible dependency identity/approval required; do not install');
const deps = realpathSync(depsDeclared), insideTask = relative(task, deps);
if (insideTask.startsWith('..') || isAbsolute(insideTask)) throw Error('Dependency staging must be in this approved TASK');
for (const p of ['react/package.json', 'react-dom/package.json']) if (!existsSync(join(deps, p))) throw Error('Approved existing React dependency is missing');
export default defineConfig({
  root: task, envDir: false, mode: 'development', cacheDir: join(task, 'future-runtime', 'sent-receipt-vite-cache'),
  esbuild: { jsx: 'automatic' },
  resolve: { alias: [{ find: /^react-dom(\/.*)?$/, replacement: join(deps, 'react-dom') + '$1' }, { find: /^react(\/.*)?$/, replacement: join(deps, 'react') + '$1' }] },
  define: { 'process.env.NODE_ENV': JSON.stringify('development'), 'import.meta.env.VITE_DATA_MODE': JSON.stringify('api'), 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api/v1'), 'import.meta.env.VITE_P2_WORKBENCH': JSON.stringify('1') },
  server: { host: '127.0.0.1', strictPort: true, open: false, hmr: false, fs: { strict: true, allow: [task, source] } },
  build: { outDir: join(task, 'future-runtime', 'artifacts', 'material-sent-receipt-ownership'), emptyOutDir: false, rollupOptions: { input: join(here, 'index.html') } },
});
