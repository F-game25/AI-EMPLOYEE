import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const BACKEND_PORT = process.env.BACKEND_PORT || 8787

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    // Dev server uses port 5173 (Vite default) so it does not conflict with
    // the Node backend that owns port 8787. Binding to 0.0.0.0 makes the dev
    // server reachable from the host machine when running inside WSL or Docker.
    // The proxy below forwards all backend paths (API, WebSocket, and static
    // assets served by Express) to the backend so relative-URL fetch calls
    // work transparently in dev mode.
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': `http://127.0.0.1:${BACKEND_PORT}`,
      '/agents': `http://127.0.0.1:${BACKEND_PORT}`,
      '/health': `http://127.0.0.1:${BACKEND_PORT}`,
      '/version': `http://127.0.0.1:${BACKEND_PORT}`,
      '/gateway': `http://127.0.0.1:${BACKEND_PORT}`,
      '/orchestrator': `http://127.0.0.1:${BACKEND_PORT}`,
      '/ws': {
        target: `ws://127.0.0.1:${BACKEND_PORT}`,
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
