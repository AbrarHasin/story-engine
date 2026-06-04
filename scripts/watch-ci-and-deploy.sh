#!/usr/bin/env bash
# watch-ci-and-deploy.sh <SHA>
#
# Background daemon: polls GitHub Actions until the "CI" workflow for <SHA>
# completes, then runs `make deploy` from PROJECT_ROOT.
#
# Launched by .claude/hooks/post_push_deploy.py via setsid after a git push.
# All output is redirected to /tmp/ci-watch.log by the caller.

set -euo pipefail

SHA="${1:?Usage: watch-ci-and-deploy.sh <full-sha>}"
PROJECT_ROOT="/home/abrar/code/story-engine"
REPO="AbrarHasin/story-engine"
CI_WORKFLOW_NAME="CI"
GH="/home/abrar/.local/bin/gh"

POLL_INTERVAL=30     # seconds between polls
MAX_APPEAR=120       # max seconds to wait for the run to appear
MAX_TOTAL=1200       # max seconds to wait for completion (20 min)

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [ci-watch] $*"; }
die() { log "FATAL: $*"; exit 1; }

[ -x "$GH" ] || die "gh CLI not found at $GH"
cd "$PROJECT_ROOT" || die "Cannot cd to $PROJECT_ROOT"

log "=== Watcher started — SHA ${SHA:0:12} ==="
log "Polling every ${POLL_INTERVAL}s · appear timeout ${MAX_APPEAR}s · total timeout ${MAX_TOTAL}s"

# ── Phase 1: Wait for CI run to appear ────────────────────────────────────────

log "Waiting for CI workflow run to appear..."
RUN_ID=""
t0=$(date +%s)

while true; do
    elapsed=$(( $(date +%s) - t0 ))
    [ "$elapsed" -ge "$MAX_APPEAR" ] && die "Run for ${SHA:0:12} not found after ${MAX_APPEAR}s"

    runs_json=$("$GH" api \
        "repos/${REPO}/actions/runs?head_sha=${SHA}&event=push" \
        2>/dev/null) || { log "API error, retrying..."; sleep "$POLL_INTERVAL"; continue; }

    RUN_ID=$(echo "$runs_json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
runs = [r for r in d.get('workflow_runs', []) if r.get('name') == '${CI_WORKFLOW_NAME}']
print(runs[0]['id'] if runs else '')
" 2>/dev/null) || RUN_ID=""

    if [ -n "$RUN_ID" ]; then
        log "Found run ID: $RUN_ID"
        break
    fi

    log "Run not visible yet — waiting ${POLL_INTERVAL}s..."
    sleep "$POLL_INTERVAL"
done

# ── Phase 2: Poll until run completes ─────────────────────────────────────────

log "Polling run $RUN_ID..."
t1=$(date +%s)
status=""
conclusion=""

while true; do
    elapsed=$(( $(date +%s) - t1 ))
    [ "$elapsed" -ge "$MAX_TOTAL" ] && die "Run $RUN_ID did not complete within ${MAX_TOTAL}s"

    run_json=$("$GH" api "repos/${REPO}/actions/runs/${RUN_ID}" 2>/dev/null) || {
        log "API error, retrying..."
        sleep "$POLL_INTERVAL"
        continue
    }

    status=$(echo "$run_json" | python3 -c "
import sys, json; d = json.load(sys.stdin); print(d.get('status', 'unknown'))
" 2>/dev/null) || status="unknown"

    conclusion=$(echo "$run_json" | python3 -c "
import sys, json; d = json.load(sys.stdin); print(d.get('conclusion') or '')
" 2>/dev/null) || conclusion=""

    log "Status: $status | Conclusion: $conclusion"
    [ "$status" = "completed" ] && break

    sleep "$POLL_INTERVAL"
done

# ── Phase 3: Deploy or report failure ─────────────────────────────────────────

if [ "$conclusion" != "success" ]; then
    log "CI FAILED (conclusion: $conclusion) — deploy skipped"
    log "Details: https://github.com/${REPO}/actions/runs/${RUN_ID}"
    exit 1
fi

log "CI PASSED — running make deploy"
log "========================================"
make deploy 2>&1
RESULT=$?
log "========================================"

if [ "$RESULT" -eq 0 ]; then
    log "=== Deploy SUCCEEDED ==="
else
    log "=== Deploy FAILED (exit $RESULT) ==="
    exit "$RESULT"
fi
