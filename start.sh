#!/usr/bin/env bash
# Doberman — one-command startup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Kill any stale processes on our ports ────────────────────────────────────
kill_port() { lsof -ti:"$1" 2>/dev/null | xargs kill -9 2>/dev/null || true; }
kill_port 5001
kill_port 5002
kill_port 5173

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🐕  Doberman — Scoped Access Broker"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Backend ──────────────────────────────────────────────────────────────────
python3 main.py > /tmp/gr-backend.log 2>&1 &
BACKEND_PID=$!
printf "  [1/2] Backend starting…"

for i in $(seq 1 30); do
  if curl -sf http://localhost:5001/api/status > /dev/null 2>&1; then
    echo " ready ✓  (PID $BACKEND_PID)"
    break
  fi
  printf "."
  sleep 0.4
done
echo ""

# ── Frontend ─────────────────────────────────────────────────────────────────
npm --prefix ui run dev > /tmp/gr-ui.log 2>&1 &
UI_PID=$!
printf "  [2/2] Frontend starting…"

for i in $(seq 1 30); do
  if curl -sf http://localhost:5173 > /dev/null 2>&1; then
    echo " ready ✓  (PID $UI_PID)"
    break
  fi
  printf "."
  sleep 0.4
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Dashboard → http://localhost:5173"
echo "  API       → http://localhost:5001/api/status"
echo "  Ctrl+C    → stop everything"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Open browser (macOS)
open "http://localhost:5173" 2>/dev/null || true

# ── Cleanup on exit ───────────────────────────────────────────────────────────
cleanup() {
  echo ""
  echo "  Stopping Doberman…"
  kill "$BACKEND_PID" "$UI_PID" 2>/dev/null || true
  wait "$BACKEND_PID" "$UI_PID" 2>/dev/null || true
  echo "  Done."
}
trap cleanup INT TERM

wait
