import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Two builds from one config:
 *  - web   (default): base `/static/spa/`, output `../backend/static/spa`
 *    → served by Django / the Fly container.
 *  - app   (`npm run build:app`): base `./`, output `dist`
 *    → bundled into the Capacitor (Android/iOS) and Electron (desktop) shells.
 */
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || '/static/spa/',
  build: {
    outDir: process.env.VITE_OUTDIR || '../backend/static/spa',
    emptyOutDir: true,
    assetsDir: 'assets',
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
