# Playwright Browser Bundle

Enterprise/offline builds populate this directory with browser binaries using:

```bash
npm run build:browser-core
```

Runtime sets `PLAYWRIGHT_BROWSERS_PATH` to this directory so RPA/browser actions do not download browsers on first use.
