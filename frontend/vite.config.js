import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    // Single-port runtime contract: frontend and backend share 127.0.0.1:8787.
    port: 8787,
    strictPort: true,
  },
})
