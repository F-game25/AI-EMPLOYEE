#!/usr/bin/env bash
# restart.sh — stop, rebuild frontend, start alles opnieuw.
# Gebruik dit na ELKE codewijziging zodat de wijziging ook echt draait.

set -e
cd "$(dirname "$0")"

echo "⟳  Stoppen..."
bash stop.sh

echo ""
echo "⟳  Frontend bouwen (dit duurt ~15 seconden)..."
(cd frontend && npm run build)

echo ""
echo "⟳  Starten..."
bash start.sh

echo ""
echo "✅ Klaar! Doe nu in je browser: Ctrl+Shift+R (harde herlaad)."
echo "   Dan staat de nieuwe code in je browser."
