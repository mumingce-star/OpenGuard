import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
const proxy = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } };
export default defineConfig({ plugins: [tailwindcss()], server: { proxy }, preview: { proxy } });
