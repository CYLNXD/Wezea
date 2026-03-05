import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      // Proxy l'API FastAPI en dev pour éviter les problèmes CORS
      '/scan':           { target: 'http://localhost:8000', changeOrigin: true },
      '/report':         { target: 'http://localhost:8000', changeOrigin: true },
      '/health':         { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir:     'dist',
    sourcemap:  true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react':  ['react', 'react-dom'],
          'vendor-motion': ['framer-motion'],
          'vendor-ui':     ['lucide-react'],
        },
      },
    },
  },
});
