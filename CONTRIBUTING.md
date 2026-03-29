# Contributing to AI Employee

Thank you for your interest in contributing! This document explains how to work with the codebase and submit improvements.

## Table of Contents

- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Adding a New Bot](#adding-a-new-bot)
- [Code Style](#code-style)
- [Running Tests](#running-tests)
- [Submitting a Pull Request](#submitting-a-pull-request)

---

## Project Structure

```
runtime/
  bin/ai-employee        # CLI entry point
  bots/                  # All bot modules
    <bot-name>/
      <bot_name>.py      # Bot logic
      run.sh             # Start script (must be chmod +x)
      requirements.txt   # Python dependencies
  config/                # Per-bot .env config files
  start.sh               # Start all bots
  stop.sh                # Stop all bots
.env.example             # Template for environment variables
install.sh               # Full installer (Linux/macOS)
```

---

## Getting Started

1. **Clone** and install dependencies:

   ```bash
   git clone https://github.com/F-game25/AI-EMPLOYEE.git
   cd AI-EMPLOYEE
   cp .env.example .env
   # Edit .env with your API keys
   bash install.sh
   ```

2. **Run the self-test** to verify everything is wired up:

   ```bash
   npm test
   # or directly:
   python3 runtime/bots/bot_selftest.py
   ```

3. **Start the system:**

   ```bash
   npm start
   # or directly:
   cd ~/.ai-employee && ./start.sh
   ```

---

## Adding a New Bot

Follow these steps exactly so the bot integrates cleanly with the rest of the system:

1. **Create the bot directory:**

   ```
   runtime/bots/<bot-name>/
     <bot_name>.py        # Main bot module
     run.sh               # Runner script
     requirements.txt     # Python deps (at minimum: requests>=2.31.0)
   ```

2. **Write `run.sh`** using the standard template:

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail
   AI_HOME="${AI_HOME:-$HOME/.ai-employee}"
   BOT_HOME="$AI_HOME/bots/<bot-name>"
   if [[ -f "$AI_HOME/.env" ]]; then set -a; source "$AI_HOME/.env"; set +a; fi
   if [[ -f "$AI_HOME/config/<bot-name>.env" ]]; then set -a; source "$AI_HOME/config/<bot-name>.env"; set +a; fi
   python3 "$BOT_HOME/<bot_name>.py"
   ```

3. **Make `run.sh` executable** — this is required:

   ```bash
   chmod +x runtime/bots/<bot-name>/run.sh
   ```

4. **Add a config template** at `runtime/config/<bot-name>.env` (even if empty).

5. **Add a selftest check** in `runtime/bots/bot_selftest.py` following the pattern of `check_engineering_assistant()`.

6. **Test your bot:**

   ```bash
   npm run lint       # syntax check all Python files
   npm test           # run the full selftest suite
   ```

---

## Code Style

- **Python:** stdlib-first; third-party imports are lazy/optional where possible. Follow the patterns already in the codebase (logging, pathlib, type hints with `from __future__ import annotations`).
- **Shell:** `set -euo pipefail` on every script; always guard `source` calls with `[[ -f ... ]]`.
- **No hardcoded secrets** — all credentials go through `.env` / environment variables.
- **Graceful fallbacks** — if an optional dependency (e.g. `requests`) is missing, catch `ImportError` and degrade gracefully.

---

## Running Tests

```bash
# Syntax-check all Python files
npm run lint

# Full health selftest (dry-run, no live API calls)
npm test

# Full selftest including a live Discord message
python3 runtime/bots/bot_selftest.py --live
```

The selftest exits with code `0` when all **required** checks pass and `1` when any required check fails — suitable for CI/CD pipelines.

---

## Submitting a Pull Request

1. Fork the repository and create a feature branch:

   ```bash
   git checkout -b feature/my-new-bot
   ```

2. Make your changes following the guidelines above.

3. Ensure tests pass:

   ```bash
   npm run lint && npm test
   ```

4. Open a pull request against `main` with a clear description of what you changed and why.

5. A maintainer will review and merge once the checks pass.

---

## Security

Please do **not** commit API keys, passwords, or other secrets. See [SECURITY.md](SECURITY.md) for the full security policy and responsible disclosure process.
