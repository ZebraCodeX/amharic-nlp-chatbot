import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The build lands inside the Django project so one container can serve both.
export default defineConfig({
  plugins: [react()],
  base: '/static/spa/',
  build: {
    outDir: '../backend/static/spa',
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
