import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Where the dev server proxies /api and /health. In docker compose this is the
// backend container (API_PROXY_TARGET); on the host it is localhost:8080.
const apiTarget =
  process.env.API_PROXY_TARGET || process.env.VITE_API_BASE_URL || 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
    },
    hmr: {
      host: 'localhost',
      port: 5173,
    },
  },
})
