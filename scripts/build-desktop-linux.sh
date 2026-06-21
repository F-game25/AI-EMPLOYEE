#!/usr/bin/env bash
# M5 — build the Nexus OS Linux desktop bundle (AppImage + .deb).
#
# Stages a self-contained repo payload (frontend/dist + backend + runtime + offline
# Python core wheelhouse), rebuilds native modules for the bundled-Node ABI, then runs
# `cargo tauri build`. The Tauri bundle config (`bundle.resources`) ships the staged
# `.build/desktop-linux/repo` dir; the Rust shell's resolve_repo_dir() finds it at runtime.
#
# NOTE (honest scope):
#   - Clean-VM verification is a MANUAL step — run the produced AppImage on a pristine
#     Linux box (only WebKitGTK from deb deps preinstalled) and confirm splash → dashboard.
#   - A bundled Python backend needs first-run venv creation from the wheelhouse (desktop
#     milestone M3). Until M3 lands, the bundle runs Node + the dashboard; the Python AI
#     backend starts only where a compatible Python is resolvable.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
STAGE="$REPO_ROOT/.build/desktop-linux/repo"

echo "[1/5] Build frontend → frontend/dist"
npm run build:frontend

echo "[2/5] Build offline Python core (wheelhouse + manifest)"
npm run build:python-core

echo "[3/5] Rebuild native modules (better-sqlite3) for the runtime Node ABI"
( npm --prefix backend rebuild better-sqlite3 ) 2>/dev/null \
  || npm rebuild better-sqlite3 2>/dev/null \
  || echo "  [warn] better-sqlite3 rebuild skipped (not installed here) — run on the build host"

echo "[4/5] Stage self-contained repo payload → $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"
for d in backend runtime frontend/dist; do
  mkdir -p "$STAGE/$(dirname "$d")"
  cp -a "$REPO_ROOT/$d" "$STAGE/$d"
done
for f in start.sh stop.sh; do
  [ -f "$REPO_ROOT/$f" ] && cp -a "$REPO_ROOT/$f" "$STAGE/$f" || true
done
echo "  staged $(du -sh "$STAGE" 2>/dev/null | cut -f1) payload"

# The bundle.resources override lives in a build-time-only config so the static
# tauri.conf.json stays buildable/checkable without the staged dir present.
echo "[5/5] cargo tauri build (AppImage + .deb) with bundled repo payload"
PKG_CONFIG_PATH="${PKG_CONFIG_PATH:-/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig}" \
  "${HOME}/.cargo/bin/cargo" tauri build \
    --target x86_64-unknown-linux-gnu \
    --manifest-path src-tauri/Cargo.toml \
    --config src-tauri/bundle.linux.conf.json

echo
echo "Done. Artifacts under src-tauri/target/**/bundle/{appimage,deb}/."
echo "Next (manual): copy the AppImage to a clean Linux VM and verify splash → dashboard."
