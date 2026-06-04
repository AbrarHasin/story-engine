#!/usr/bin/env python3
"""
Pre-tool hook: checks if backend/frontend are alive before Bash commands
that touch the API, and warns if they are down.
Writes to stderr so it shows as a warning, not a blocker.
"""
import sys, json, subprocess, os

# Only run for Bash tool calls that touch the project
try:
    input_data = json.load(sys.stdin)
    command = input_data.get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

# Skip for non-project commands
if not any(kw in command for kw in ["localhost:8080", "localhost:5173", "/api/", "test_generate", "playwright"]):
    sys.exit(0)

# Quick health check
try:
    result = subprocess.run(
        ["curl", "-sf", "--max-time", "2", "http://localhost:8080/health"],
        capture_output=True, text=True, timeout=3
    )
    if result.returncode != 0:
        print("⚠️  Backend (port 8080) is DOWN — start it first:", file=sys.stderr)
        print("   cd /home/abrar/code/story-engine/backend", file=sys.stderr)
        print("   setsid .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload > /tmp/backend.log 2>&1 &", file=sys.stderr)
except Exception:
    pass

sys.exit(0)
