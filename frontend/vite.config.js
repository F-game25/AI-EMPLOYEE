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
    // oxc minifier (rolldown-native). terser caused syntax errors on modern
    // operators (??, ?.) in the working tree; oxc handles them cleanly.
    minify: 'oxc',
    sourcemap: false,
    reportCompressedSize: true,
    // Three.js core is intentionally isolated as a vendor chunk. Keep the
    // warning budget above that known dependency size so builds only warn on
    // unexpected growth.
    chunkSizeWarningLimit: 800,
    rolldownOptions: {
      output: {
        // Native Rolldown codeSplitting API — splits Three.js vendor out of each
        // neural page chunk so they share a single ~1MB vendor-three bundle.
        // First-match wins; ordering matters.
        codeSplitting: {
          includeDependenciesRecursively: false,
          groups: [
            // Three.js ecosystem split into sub-chunks so no single bundle exceeds ~300KB.
            // First-match wins; order is load-time importance + size.
            { name: 'vendor-three-forcegraph', test: /node_modules\/(three-forcegraph|three-render-objects|d3-force-3d|ngraph[^/]*|accessor-fn|kapsule|float-rgba)(\/|$)/ },
            { name: 'vendor-three-text',      test: /node_modules\/(troika[^/]*|bidi-js|webgl-sdf-generator)(\/|$)/ },
            { name: 'vendor-three-mesh',      test: /node_modules\/(three-mesh-bvh|meshline)(\/|$)/ },
            { name: 'vendor-zustand',          test: /node_modules\/zustand(\/|$)/ },
            { name: 'vendor-three-extras',    test: /node_modules\/(@react-three|three-stdlib|stats-gl|stats\.js|maath|suspend-react|its-fine)(\/|$)/ },
            { name: 'vendor-three-core',      test: /node_modules\/three(\/|$)/ },
            { name: 'vendor-react',           test: /node_modules\/(react|react-dom|scheduler|use-sync-external-store)(\/|$)/ },
            { name: 'vendor-motion',          test: /node_modules\/(framer-motion|gsap|motion|@motionone|@emotion\/is-prop-valid|@emotion\/memoize)(\/|$)/ },
            { name: 'vendor-utils',           test: /node_modules\/(leva|howler|tunnel-rat)(\/|$)/ },
            { name: 'page-dashboard',   test: /NexusOSDashboard/ },
            { name: 'page-operations',  test: /OperationsPage/ },
            // NeuralNetworkPage owns the entire src/components/three/ subtree (UnifiedBrain etc.)
            { name: 'page-neural-graph',test: /(NeuralNetworkPage|components\/three\/(UnifiedBrain|NeuralCore|DataStreamHighway|OrbitalSubsystem))/ },
            { name: 'page-neural-brain',test: /NeuralBrainPage/ },
            { name: 'page-knowledge',   test: /KnowledgePage/ },
            { name: 'page-intelligence',test: /IntelligencePage/ },
            { name: 'page-settings',    test: /SettingsPage/ },
            { name: 'page-integrations',test: /IntegrationsPage/ },
            { name: 'page-others',      test: /(AscendForgePage|WorkspacePage|VoicePage|BlacklightPage|OutputPage|DevPanel|SystemHealthPage)/ },
            { name: 'core-ui',          test: /(Sidebar|TopBar|SystemBar|CommandDock)\.jsx/ },
          ],
        },
      },
    },
  },
  define: {
    // Optimize build flags
    __VITE_PROD__: JSON.stringify(process.env.NODE_ENV === 'production'),
  },
})
