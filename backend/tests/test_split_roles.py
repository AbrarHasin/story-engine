"""ADR split-api-graph: story-api never loads the generation stack; story-graph serves only it.

Imports run in a fresh interpreter so modules already loaded by other tests cannot hide
an accidental import.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

HEAVY = ("langgraph", "langchain", "langchain_core", "langchain_anthropic", "langchain_openai",
         "anthropic", "openai", "fastembed", "onnxruntime", "sentence_transformers", "torch",
         "app.agents.graph", "app.agents.nodes", "app.cache.semantic",
         "app.api.v1.generate")

PROBE = """
import json, sys
import {module} as m
heavy = {heavy!r}
loaded = sorted(n for n in sys.modules if any(n == h or n.startswith(h + ".") for h in heavy))
routes = sorted({{(r.path, ",".join(sorted(getattr(r, "methods", None) or []))) for r in m.app.routes}})
print(json.dumps({{"loaded": loaded, "routes": routes}}))
"""


def _probe(module: str, role: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("RUN_ROLE", "SSM_PARAMETER_PATH")}
    if role:
        env["RUN_ROLE"] = role
    out = subprocess.run(
        [sys.executable, "-c", PROBE.format(module=module, heavy=HEAVY)],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _paths(result: dict) -> set[tuple[str, str]]:
    return {tuple(r) for r in result["routes"]}


def test_api_role_imports_no_langgraph_llm_sdk_or_onnx():
    r = _probe("app.main", "api")
    assert r["loaded"] == [], f"story-api imported the generation stack: {r['loaded']}"
    paths = _paths(r)
    assert ("/api/v1/stories/generate", "POST") not in paths
    assert ("/api/v1/llm/ping", "POST") not in paths
    # everything else story-api owns is still there
    for path, method in [("/api/v1/auth/login", "POST"), ("/api/v1/stories/", "GET"),
                         ("/api/v1/stories/{story_id}/export", "GET"),
                         ("/api/v1/personalities/", "GET"), ("/api/v1/llm/config", "GET"),
                         ("/health", "GET")]:
        assert (path, method) in paths, (path, method)
    assert any(p.startswith("/api/v1/payment") for p, _ in paths)


def test_all_role_is_one_process_with_everything():
    r = _probe("app.main", None)  # default RUN_ROLE=all (local dev, docker compose)
    paths = _paths(r)
    assert ("/api/v1/stories/generate", "POST") in paths
    assert ("/api/v1/llm/ping", "POST") in paths
    assert ("/api/v1/stories/", "GET") in paths
    assert "langgraph" in {n.split(".")[0] for n in r["loaded"]}


def test_graph_entry_point_serves_only_generation():
    r = _probe("app.graph_main", "graph")
    paths = {p for p, _ in _paths(r)}
    assert paths == {"/api/v1/stories/generate", "/health"}


def test_llm_config_works_without_langchain(monkeypatch):
    # /llm/config is on story-api, whose image has no langchain: it must not need it
    probe = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name.split('.')[0] in ('langchain_core', 'langchain', 'langgraph'):\n"
        "        raise ImportError('blocked: ' + name)\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        "import asyncio\n"
        "from app.api.v1.llm import llm_config\n"
        "info = asyncio.run(llm_config())\n"
        "import json; print(json.dumps(info))\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("RUN_ROLE", "SSM_PARAMETER_PATH")}
    out = subprocess.run([sys.executable, "-c", probe], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    info = json.loads(out.stdout.strip().splitlines()[-1])
    assert set(info["models"]) == {"router", "writer", "synthesizer", "premium"}
