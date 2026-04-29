/* global process */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import glsl from 'vite-plugin-glsl'

const BACKEND_PORT = process.env.BACKEND_PORT || 8787

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    glsl(),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.js'],
    css: false,
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // HMR must advertise the correct host when accessed from a different
    // machine (WSL host, Docker host, LAN). Without this, Vite sends the
    // internal container/WSL IP and the browser can't reach it.
    hmr: {
      host: process.env.HMR_HOST || 'localhost',
      port: 5173,
      protocol: 'ws',
    },
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
