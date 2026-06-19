# Vendored: Open-Generative-AI (content-creation base)

Source: https://github.com/F-game25/Open-Generative-AI (fork of Anil-matcha/Open-Generative-AI)
Upstream commit: 1f198c582f2377453049ab417e261941cc81d4e7
License: MIT (see LICENSE)
Vendored: 2026-06-17

We integrate the **content-creation engine** (the MuAPI model catalog + generation
convention), not the Next.js/Electron UI app or its nested submodules. The
AI-EMPLOYEE content factory consumes this via:
- runtime/content/media_models.py  — loads this catalog (models_dump.json + models.js)
- runtime/content/muapi_client.py   — MuAPI submit→poll client (x-api-key)

To refresh: re-copy models_dump.json + packages/studio/src/models.js from upstream.
