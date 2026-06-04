#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="/home/abrar/code/story-engine/backend"
LOG_FILE="/tmp/backend.log"

echo "[deploy] Stopping existing backend..."
pkill -f "uvicorn app.main:app" 2>/dev/null && sleep 2 || true

echo "[deploy] Starting backend..."
cd "$BACKEND_DIR"
setsid .venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8080 --reload \
  >> "$LOG_FILE" 2>&1 &

echo "[deploy] Backend started (PID $!). Log: $LOG_FILE"
