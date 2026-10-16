import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend runs on 8000 (see the project root's start.sh). Proxying it here
// keeps the browser on a single origin, so there is no CORS round-trip and no
// hard-coded backend URL in the app code.
const BACKEND = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // 5173/5174 are taken by another local Vite project on this machine, so
    // this app uses 5180. Override with `npm run dev -- --port <n>`.
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
      '/docs': { target: BACKEND, changeOrigin: true },
      '/openapi.json': { target: BACKEND, changeOrigin: true },
    },
  },
  preview: {
    port: 4174,
    strictPort: true,
  },
})
