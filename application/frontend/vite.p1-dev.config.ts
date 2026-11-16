/** Opt-in synthetic P1 integration proxy. The ordinary Vite config is unchanged. */
import { defineConfig, mergeConfig } from 'vite';
import baseConfig from './vite.config.ts';

function devPort(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined) return fallback;
  if (!/^[0-9]+$/.test(raw)) throw new Error(`${name} must be a numeric loopback dev port`);
  const port = Number(raw);
  if (!Number.isSafeInteger(port) || port < 1024 || port > 65535
      || [5174, 8000, 8011, 8080].includes(port)) {
    throw new Error(`${name} must be a separate port between 1024 and 65535`);
  }
  return port;
}

export default defineConfig(() => {
  const apiPort = devPort('OPENGUARD_P1_API_PORT', 18011);
  const webPort = devPort('OPENGUARD_P1_WEB_PORT', 15174);
  if (apiPort === webPort) throw new Error('P1 API and web ports must differ');
  // Accept ports, never an arbitrary proxy URL. Keep real Origin headers intact.
  const proxy = { '/api': { target: `http://127.0.0.1:${apiPort}`, changeOrigin: false } };
  const local = {
    host: '127.0.0.1', port: webPort, strictPort: true,
    allowedHosts: ['127.0.0.1', 'localhost'], cors: false, proxy,
  };
  return mergeConfig(baseConfig, {
    define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api/v1') },
    server: local,
    preview: local,
  });
});
