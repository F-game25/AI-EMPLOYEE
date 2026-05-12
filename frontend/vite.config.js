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
  build: {
    // Phase 3.3: Performance optimization
    minify: 'terser',
    sourcemap: false,
    reportCompressedSize: true,
    chunkSizeWarningLimit: 600,
    terserOptions: {
      compress: {
        drop_console: true,
        passes: 2,
        pure_funcs: ['console.log', 'console.debug'],
      },
      format: {
        comments: false,
      },
    },
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          // Vendor chunks
          if (id.includes('node_modules/react') && !id.includes('react-three') && !id.includes('react-force')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/three') || id.includes('@react-three')) {
            return 'vendor-three';
          }
          if (id.includes('node_modules/framer-motion') || id.includes('node_modules/gsap')) {
            return 'vendor-motion';
          }
          if (id.includes('node_modules/zustand') || id.includes('node_modules/leva') || id.includes('node_modules/howler')) {
            return 'vendor-utils';
          }

          // Route-based splits
          if (id.includes('NexusOSDashboard')) {
            return 'page-dashboard';
          }
          if (id.includes('OperationsPage')) {
            return 'page-operations';
          }
          if (id.includes('NeuralNetworkPage')) {
            return 'page-neural';
          }
          if (id.includes('SettingsPage')) {
            return 'page-settings';
          }
          if (id.includes('IntelligencePage')) {
            return 'page-intelligence';
          }
          if (id.includes('IntegrationsPage')) {
            return 'page-integrations';
          }
          if (id.includes('AscendForgePage') || id.includes('WorkspacePage') ||
              id.includes('VoicePage') || id.includes('BlacklightPage') ||
              id.includes('OutputPage') || id.includes('DevPanel') ||
              id.includes('SystemHealthPage')) {
            return 'page-others';
          }

          // Core UI (immediate load)
          if (id.includes('Sidebar.jsx') || id.includes('TopBar.jsx') ||
              id.includes('SystemBar.jsx') || id.includes('CommandDock.jsx')) {
            return 'core-ui';
          }
        },
      },
    },
  },
  define: {
    // Optimize build flags
    __VITE_PROD__: JSON.stringify(process.env.NODE_ENV === 'production'),
  },
})
