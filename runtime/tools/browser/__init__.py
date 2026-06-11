"""Browser Execution Service (Module 1, Reference-Capability Layers).

Headless-chromium execution as a set of atomic tools:
- browser_service        — session lifecycle, URL policy, single worker thread
- accessibility_snapshot — stable-ref page snapshots (@eN refs survive mutation)
- action_executor        — click/fill/type/press/scroll/select on refs/selectors
- extract                — text/html/value/title/url/attr extraction (bounded)
- capture                — screenshots/PDFs to ~/.ai-employee/state/browser_captures
- tool_contracts         — op descriptors mirroring the capability registry seeds

All Playwright calls run on ONE dedicated worker thread (sync Playwright is
greenlet-bound and refuses to run on asyncio-loop threads), which makes the
service safely callable from FastAPI handlers or anywhere else.
"""
