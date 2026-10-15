# Implementation Plan: Story Engine Baseline Remediation

**Branch**: `001-story-engine-baseline` | **Date**: 2026-10-15 | **Spec**: [spec.md](./spec.md)
**Input**: baseline spec plus the issue list in vault note `Projects/Story-Engine/Decisions-vs-Code.md`.

## Summary

The baseline is built and passing (38 Playwright tests, CI green on mocked LLM). This plan
closes the `[GAP]` requirements (NFR-001..007, SC-004) and the audit defects that violate the
constitution. No new product features; roadmap features get their own specs later.

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5 (React 18 + Vite)
**Primary Dependencies**: FastAPI, LangGraph 1.x, langchain-anthropic, langchain-openai, SQLAlchemy async, Alembic, Langfuse v3
**Storage**: PostgreSQL + pgvector, Redis (checkpointer)
**Testing**: pytest (mocked LLM) in CI; Playwright e2e locally
**Target Platform**: Docker Compose behind Cloudflare Tunnel (ZimaOS); dev on WSL
**Constraints**: cost <= $0.19/story (target $0.08); every LLM call has a `MAX_TOKENS_*` cap; no provider SDK in nodes
**Scale/Scope**: single-tenant dev now; per-user quotas needed before public sign-up

## Constitution Check

| Principle | Status | Remediation phase |
|---|---|---|
| I Token cost | VIOLATED: discarded supervisor call, literal `max_tokens=50`, no caching, supervisor cost uncounted | Phase 2 |
| II Model tiering | OK | - |
| III Provider-agnostic | OK | - |
| IV Observable | PARTIAL: trace id and user id wrong | Phase 3 |
| V Streaming contract | OK | - |
| VI Secure by default | VIOLATED: ownership, payment, fail-closed secret | Phase 1 |
| VII Test discipline | PARTIAL: no auth or ownership tests, weak API smoke tests | Phase 1, 4 |
| VIII Licensing | UNCHECKED: no dependency licence audit | Phase 4 |

## Project Structure

```text
specs/001-story-engine-baseline/   spec.md, plan.md, tasks.md, analysis.md
backend/app/api/v1/                stories.py, personalities.py (ownership)
backend/app/payment/sslcommerz.py  payment hardening
backend/app/agents/                nodes.py, graph.py (supervisor, caps)
backend/app/core/                  config.py (startup guard), auth.py
frontend/src/                      auth header + login
backend/tests/                     ownership, payment, cost, truncation tests
```

## Phases

1. **Security (blocking public use)**: ownership checks, payment hardening, fail-closed secret, frontend token header.
2. **Cost and correctness**: remove or use supervisor route, centralise caps, fix synthesizer truncation, correct cost accounting, add prompt caching.
3. **Observability and data**: Langfuse ids, persist research, quotas and rate limits.
4. **Hygiene**: tests, licence audit, doc drift in the vault, Makefile ports, prod compose secrets.

## Complexity Tracking

None: all work removes drift or adds checks inside existing modules.
