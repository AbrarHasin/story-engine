#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="/home/abrar/code/story-engine/frontend"
LOG_FILE="/tmp/frontend.log"

echo "[deploy] Stopping existing frontend..."
pkill -f "vite" 2>/dev/null && sleep 1 || true

echo "[deploy] Starting frontend..."
cd "$FRONTEND_DIR"
setsid npm run dev -- --host \
  >> "$LOG_FILE" 2>&1 &

echo "[deploy] Frontend started (PID $!). Log: $LOG_FILE"
