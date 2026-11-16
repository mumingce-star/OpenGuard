/** NOT_RUN. Future explicitly authorized isolated copy only. Never import the product Vite config. */
import { defineConfig } from 'vite';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
// Approved layout: TASK/runtime/frontend/tests/readonly-async/. TASK/candidate/after is a delta, not a runnable copy.
const taskRoot = resolve(frontendRoot, '../..');
if (frontendRoot !== resolve(taskRoot, 'runtime/frontend') || !existsSync(resolve(taskRoot, 'input/00_START_HERE.md'))) {
  throw new Error('Only the separately authorized complete TASK/runtime/frontend copy may use this test config');
}
export default defineConfig({
  root: frontendRoot,
  envDir: false,
  cacheDir: resolve(taskRoot, 'runtime-test-cache'),
  // No product plugins, proxy, .env loading or network API fallback. Existing Vite/React only.
  esbuild: { jsx: 'automatic', jsxImportSource: 'react' },
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api/v1'),
    'import.meta.env.VITE_P2_WORKBENCH': JSON.stringify('1'),
  },
  server: { host: '127.0.0.1', port: 19873, strictPort: true, hmr: false, cors: false, proxy: {}, fs: { strict: true, allow: [frontendRoot] } },
  preview: { host: '127.0.0.1', port: 19874, strictPort: true },
  build: { outDir: resolve(taskRoot, 'runtime-test-dist'), emptyOutDir: false, rollupOptions: { input: resolve(frontendRoot, 'tests/readonly-async/index.html') } },
});
