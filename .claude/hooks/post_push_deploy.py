#!/usr/bin/env python3
"""
PostToolUse hook: detect git push to master, launch CI watcher daemon.

Receives JSON via stdin:
  tool_name  : "Bash"
  tool_input : {"command": "...", "description": "..."}
  tool_result: {"exit_code": N, "output": "..."}

Launches scripts/watch-ci-and-deploy.sh via setsid (non-blocking).
All watcher output → /tmp/ci-watch.log
"""
import sys
import json
import subprocess
import os
import re

PROJECT_ROOT = "/home/abrar/code/story-engine"
WATCHER_SCRIPT = f"{PROJECT_ROOT}/scripts/watch-ci-and-deploy.sh"
LOG_FILE = "/tmp/ci-watch.log"
BRANCH = "master"


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")

    if "git" not in command or "push" not in command:
        sys.exit(0)

    # Reject pushes to an explicitly named non-master ref
    # Allows: git push, git push origin, git push origin master, git push -u origin master
    # Rejects: git push origin feature-branch, git push origin HEAD:some-branch
    match = re.search(r'git\s+push\b[^|&;]*\borigin\s+(\S+)', command)
    if match:
        ref = match.group(1)
        if ":" in ref:
            ref = ref.split(":")[-1]
        if not ref.startswith("-") and ref != BRANCH:
            sys.exit(0)

    # Don't deploy if the push itself failed
    tool_result = data.get("tool_result", {})
    if isinstance(tool_result, dict) and tool_result.get("exit_code", 0) != 0:
        sys.exit(0)

    # Get HEAD SHA
    try:
        r = subprocess.run(
            ["git", "-C", PROJECT_ROOT, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            sys.exit(0)
        sha = r.stdout.strip()
    except Exception:
        sys.exit(0)

    if len(sha) < 40:
        sys.exit(0)

    # Ensure gh CLI is on PATH for the watcher subprocess
    env = os.environ.copy()
    local_bin = "/home/abrar/.local/bin"
    if local_bin not in env.get("PATH", ""):
        env["PATH"] = local_bin + ":" + env.get("PATH", "")

    try:
        with open(LOG_FILE, "a") as log:
            subprocess.Popen(
                ["/usr/bin/setsid", "/usr/bin/bash", WATCHER_SCRIPT, sha],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                close_fds=True,
                start_new_session=True,
                env=env,
            )
    except Exception as e:
        print(f"[post_push_deploy] Failed to launch watcher: {e}", file=sys.stderr)
        sys.exit(0)

    print(
        f"[post_push_deploy] CI watcher started for {sha[:12]}. "
        f"Watch: tail -f {LOG_FILE}"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
