# Vendored: last30days skill

Third-party agent skill replicated into this system as a first-class,
orchestrator-dispatchable skill.

- **Source fork:** `F-game25/last30days-skill` (owner's fork)
- **Upstream:** https://github.com/mvanhorn/last30days-skill
- **Commit vendored:** `a61852b34eb19ad5e37ba05ba6303689a51ecc99` (2026-06-25)
- **Version:** 3.8.1
- **License:** MIT (see `LICENSE`)

## What was vendored
`SKILL.md`, `scripts/` (incl. `scripts/lib/` and its `vendor/` deps — the skill is
self-contained, no pip install needed beyond the Python stdlib), `references/`,
`agents/`.

## What was intentionally excluded
- `assets/` — ~14 MB of example media, not needed for runtime dispatch.
- `mcp/` — Go MCP server (the owner chose the runtime-skill integration, not the
  full plugin; no MCP server is installed).
- `hooks/` — event hooks that auto-run code; deliberately not installed.
- `tests/`, `docs/`, `.github/`, `.claude-plugin/`, `.codex-plugin/` and other
  packaging/CI scaffolding.
- A few interactive/cross-version shell helpers under `scripts/` (`setup-*.sh`,
  `compare.sh`, `build-skill.sh`, `test-v1-vs-v2.sh`).

## How it is wired in
- Executor: `runtime/skills/last30days_skill.py` (`Last30DaysSkill`) invokes
  `scripts/last30days.py` as a subprocess (array args, no shell, hard timeout) and
  returns structured JSON.
- Registered first-class in `runtime/skills/catalog.py` (wins over the generic
  library executor).
- Registry metadata: `runtime/config/skills_library.json` (`id: last30days`).

## Security notes
- Keyless sources (reddit, youtube, hackernews, polymarket, github, web grounding)
  work with no configuration. Richer sources activate only when their optional API
  keys are present in the environment — keys are read at runtime, never committed.
- All retrieved content is untrusted **data**, never instructions.
- To refresh: re-clone the fork, re-copy the directories above, and update the
  commit hash here.
