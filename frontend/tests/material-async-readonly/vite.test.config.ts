import { defineConfig } from 'vite';
import { realpathSync } from 'node:fs';
import { isAbsolute, join, relative } from 'node:path';

// Future authorized runner only. These path checks are not OS enforcement or
// permission evidence. This file was not imported or executed in preparation.
const declared = process.env.OPENGUARD_VALIDATION_TASK;
if (!declared || !isAbsolute(declared)) throw Error('Explicit isolated TASK required');
const task = realpathSync(declared), root = realpathSync(join(task, 'runtime', 'frontend'));
const within = relative(task, root);
if (within.startsWith('..') || isAbsolute(within)) throw Error('Frontend escaped TASK');
export default defineConfig({
  root, mode: 'development', envDir: false, cacheDir: join(task, 'runtime', 'material-async-vite-cache'),
  esbuild: { jsx: 'automatic' },
  define: { 'process.env.NODE_ENV': JSON.stringify('development'),
    'import.meta.env.VITE_DATA_MODE': JSON.stringify('api'),
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api/v1'),
    'import.meta.env.VITE_P2_WORKBENCH': JSON.stringify('1') },
  server: { host: '127.0.0.1', strictPort: true, hmr: false, open: false, fs: { strict: true, allow: [task] } },
  build: { outDir: join(task, 'artifacts', 'material-async-readonly'), emptyOutDir: false,
    rollupOptions: { input: join(root, 'tests', 'material-async-readonly', 'index.html') } },
});
