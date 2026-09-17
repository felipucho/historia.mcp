import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 127.0.0.1 y no "localhost": Node 17+ puede resolver localhost a ::1 y uvicorn escucha solo IPv4.
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Si Vite saltara a 5174, ese origen no está en CORS_ORIGINS y el WebSocket cerraría con 1008.
    strictPort: true,
    // Proxy: el navegador habla solo con :5173 (mismo origen). El header Origin llega intacto al backend.
    proxy: {
      '/api': BACKEND_URL,
      '/ws': { target: BACKEND_URL, ws: true },
    },
  },
})
