# Story Engine Constitution

Source: vault notes `Projects/Story-Engine/` (00-Project-Hub "Token Optimisation (Primary Design Constraint)",
Architecture, Local-LLM-Adapter, LangGraph-Feature-Roadmap) and `CLAUDE.md` "Model Tiers" / "Dev Constraints".
Each principle is normative: spec, plan and tasks MUST comply (see `/speckit-analyze`).

## Core Principles

### I. Token Cost Is the Primary Design Constraint (NON-NEGOTIABLE)
Every feature MUST state its token and USD impact before it is built. Target cost is
about $0.19 per story today and about $0.08 with caching. A change that raises
per-story cost MUST be justified in its spec and measured against that budget.
- Levers in priority order: model tiering, prompt caching, hard output caps, structured
  short outputs from sub-agents, semantic cache, Batch API for non-interactive work.
- Every LLM call MUST set a hard `max_tokens` cap sourced from `Settings.MAX_TOKENS_*`.
- Sub-agents MUST return structured output (JSON array of 3-5 short bullets), never prose.
- Token and cost accounting MUST be reported per node and per story (`TokenUsage`,
  `done` SSE event, `stories.tokens_*`, `stories.cost_usd`).
- Calls whose result is discarded are waste and MUST NOT ship.

### II. Model Tiering
Cheap models route and research; premium models only write.
- Router/sub-agent role (supervisor, research, light, dark, facts): Haiku tier (`MODEL_ROUTER`).
- Writer and synthesizer roles: Sonnet tier (`MODEL_WRITER`, `MODEL_SYNTHESIZER`).
- Opus tier (`MODEL_PREMIUM`) only for a paid premium plan, and only behind an explicit role.
- Moving a node to a higher tier requires a documented quality justification and a cost delta.

### III. Provider-Agnostic Nodes (Adapter Pattern)
Graph nodes MUST NOT import a provider SDK. They request a model by role through
`get_adapter().chat(role, max_tokens, temperature)`. `LLM_PROVIDER=anthropic|local`
switches the whole pipeline. Local inference is accounted at $0. Adding a provider
means adding an adapter, not editing nodes.

### IV. Observable by Default
Every generation MUST produce a Langfuse trace (self-hosted v3, no SaaS tracing),
with per-node spans, token usage and cost. Traces MUST be linkable from the `done`
event and from the stored story (`langgraph_run_id`). Observability failures MUST
degrade to no-op, never fail a generation.

### V. Streaming Contract
Generation is delivered over SSE (`start`, `node_complete`, `done`, `error`). The
client uses fetch-based streaming (POST body), not `EventSource`. Any new event or
payload field MUST be added to the contract in the spec and covered by an e2e test.

### VI. Secure by Default, Dev Convenience Isolated
- Secrets (`backend/.env`, API keys) MUST never be committed or added to CI as
  secrets unless a job needs a live LLM.
- The tokenless dev-user fallback MUST be reachable only when `JWT_SECRET_KEY` is the
  default dev value. Production configuration MUST fail closed (startup error) when the
  secret is the default.
- Every endpoint that reads or mutates user data MUST authenticate the caller and
  check ownership.
- Payment confirmation MUST be verified server-side with the gateway; unsigned or
  unverifiable notifications MUST be rejected.

### VII. Test Discipline
- CI MUST run with a mocked LLM and no paid API calls (`tests/test_agents.py`,
  `tests/test_llm_adapter.py`) plus API smoke tests against Postgres and Redis.
- E2E (Playwright) covers the API, the browser UI, Langfuse traces and the adapter.
- A bug fix lands with a regression test.

### VIII. Open Source and Licensing
The project is GPL-3.0. New dependencies MUST be GPL-3.0 compatible. Observability,
caching and local-model choices favour free, self-hostable OSS.

## Additional Constraints

- Stack: Python 3.12 + FastAPI (async) + LangGraph 1.x; React + Vite + TypeScript +
  Tailwind; PostgreSQL + pgvector; Redis; Langfuse v3; SSLCommerz for payments.
- Backend dev port 8080, container port 8000; frontend 5173; Langfuse 3000.
- State schema uses `Annotated[list, operator.add]` for parallel-safe writes; each node
  returns only the keys it writes.
- Schema changes go through Alembic migrations.
- The vault (`Projects/Story-Engine/`) is the narrative record; `specs/` is the
  normative record. They MUST NOT disagree: drift is a defect (see `Decisions-vs-Code.md`).

## Development Workflow

- Work on feature branches; merge to `master` via PR after CI passes.
- CD is a local `make deploy` triggered after CI success; it MUST smoke-test `/health`.
- Roadmap features (streaming tokens, critique loop, HITL outline, dynamic sections)
  are specified under `specs/` before implementation, each with a cost estimate.

## Governance

This constitution supersedes ad-hoc practice. Amendments require a PR that updates
this file, states the reason, and lists affected specs. `/speckit-analyze` treats any
violation of a MUST as CRITICAL.

**Version**: 1.0.0 | **Ratified**: 2026-10-15 | **Last Amended**: 2026-10-15
