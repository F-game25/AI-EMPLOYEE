import '@testing-library/jest-dom'

// Silence framer-motion warnings in test environment
vi.mock('framer-motion', () => ({
  motion: new Proxy({}, {
    get: (_, tag) => {
      const { forwardRef, createElement } = require('react')
      return forwardRef((props, ref) => createElement(tag, { ...props, ref }))
    },
  }),
  AnimatePresence: ({ children }) => children,
  useMotionValue: () => ({ set: vi.fn(), get: () => 0 }),
  useTransform: () => ({ set: vi.fn(), get: () => 0 }),
}))

// Silence react-force-graph-3d (WebGL not available in jsdom)
vi.mock('react-force-graph-3d', () => ({ default: () => null }))

// Stub WebSocket
global.WebSocket = class {
  constructor() {}
  send() {}
  close() {}
  addEventListener() {}
  removeEventListener() {}
}

// Stub sessionStorage / localStorage (jsdom provides these but make explicit)
Object.defineProperty(window, 'sessionStorage', { value: global.sessionStorage })
