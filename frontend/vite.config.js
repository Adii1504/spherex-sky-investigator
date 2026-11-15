import { defineConfig } from 'vite';
// Keep hashed assets available to browser tabs opened before an incremental build.
export default defineConfig({server:{proxy:{'/api':'http://127.0.0.1:8000','/processing':'http://127.0.0.1:8000'}}, build:{outDir:'dist',emptyOutDir:false}});
