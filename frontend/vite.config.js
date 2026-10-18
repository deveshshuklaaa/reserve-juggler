import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    host: true
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['./tests/setup.js'], restoreMocks: true, testTimeout: 15000, maxWorkers: 2 },
  build: { rollupOptions: { output: { manualChunks: { charts: ['recharts'], icons: ['lucide-react'] } } } }
});
