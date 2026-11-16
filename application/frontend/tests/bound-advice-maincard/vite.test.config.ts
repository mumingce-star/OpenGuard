import { defineConfig } from 'vite';
import { realpathSync } from 'node:fs';
import { isAbsolute, join, relative } from 'node:path';

// Future authorized runner only. The full frontend copy and pre-existing
// compatible third-party dependencies must be provided under this TASK first.
// This config is not evidence of OS network or filesystem enforcement.
const declared=process.env.OPENGUARD_VALIDATION_TASK;
if(!declared||!isAbsolute(declared))throw Error('An explicit absolute isolated TASK is required');
const task=realpathSync(declared);
const root=realpathSync(join(task,'runtime','frontend'));
if(relative(task,root).startsWith('..')||isAbsolute(relative(task,root)))throw Error('Frontend root escaped TASK');
export default defineConfig({root,mode:'development',envDir:false,cacheDir:join(task,'runtime','vite-cache'),define:{'process.env.NODE_ENV':JSON.stringify('development'),'import.meta.env.VITE_DATA_MODE':JSON.stringify('api'),'import.meta.env.VITE_API_BASE_URL':JSON.stringify('/api/v1'),'import.meta.env.VITE_P2_WORKBENCH':JSON.stringify('1')},server:{host:'127.0.0.1',strictPort:true,hmr:false,open:false,fs:{strict:true,allow:[task]}},build:{outDir:join(task,'artifacts','bound-advice-component-test'),emptyOutDir:false,rollupOptions:{input:join(root,'tests','bound-advice-maincard','index.html')}}});
