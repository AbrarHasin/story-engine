# Feature Specification: Story Engine Baseline (as built)

**Feature Branch**: `001-story-engine-baseline`
**Created**: 2026-10-15
**Status**: Baseline - describes what is BUILT at commit `c2db465` (branch `llm-adapter`), not what is planned.
**Input**: Reconcile vault notes (`Projects/Story-Engine/`) with the code and put the project under Spec Kit.

> Convention: requirements marked **[GAP]** are documented intent that the code does not meet.
> They are listed so `/speckit-analyze` can see them; they are not part of the built baseline.
> The reconciliation table lives in the vault note `Decisions-vs-Code.md`.

## User Scenarios & Testing

### User Story 1 - Generate a structured story from a topic (Priority: P1)

A user submits topic, tonality, audience, length, locale and optional include flags
(light side, dark side, facts) and watches the story assemble live.

**Why this priority**: it is the product.

**Independent Test**: `POST /api/v1/stories/generate` with a topic; assert event order
`start`, one or more `node_complete`, `done`; assert a `stories` row reaches `completed`.
Covered by `e2e/api.spec.ts`, `e2e/story-config.spec.ts`.

**Acceptance Scenarios**:

1. **Given** a valid request, **When** generation runs, **Then** the client receives `start`,
   then `node_complete` for research, light_side, dark_side, facts, writer, synthesizer, then `done`.
2. **Given** `include_dark=false`, **When** generation runs, **Then** the dark_side node emits
   no bullets, the writer prompt omits the Dark Side section, and no dark-side tokens are spent.
3. **Given** the LLM raises, **When** the graph fails, **Then** an `error` event is sent and the
   story status becomes `failed`.

### User Story 2 - Reuse a writing personality (Priority: P2)

A user saves named presets (voice, tone, reading level, banned words, locale) and applies
one to a generation.

**Independent Test**: create via `POST /api/v1/personalities/`, pass `personality_id` to generate.

**Acceptance Scenarios**:

1. **Given** a saved personality, **When** it is passed to generate, **Then** its fields are
   compiled into a prompt fragment and injected into the writer system prompt.

### User Story 3 - Browse, export and delete past stories (Priority: P2)

**Independent Test**: list, get, export (`.md` download) and delete a story.

**Acceptance Scenarios**:

1. **Given** completed stories, **When** the library is opened, **Then** stories are listed newest first with cost and tokens.
2. **Given** a story, **When** export is requested, **Then** a Markdown file with the sections is returned.

### User Story 4 - Choose where inference runs (Priority: P2)

An operator switches the whole pipeline between Claude API and a local Docker Model
Runner model with `LLM_PROVIDER`.

**Independent Test**: `GET /api/v1/llm/config`; `POST /api/v1/llm/ping`; `e2e/llm-adapter.spec.ts`.

**Acceptance Scenarios**:

1. **Given** `LLM_PROVIDER=local`, **When** a story is generated, **Then** reported cost is 0.
2. **Given** `LLM_PROVIDER=anthropic`, **When** a story is generated, **Then** roles map to Haiku (router) and Sonnet (writer, synthesizer) and cost is computed from token usage.

### User Story 5 - Account, plan and payment (Priority: P3)

Users register and log in with email and password (JWT) and can start an SSLCommerz
payment to upgrade to Pro or Enterprise.

**Acceptance Scenarios**:

1. **Given** valid credentials, **When** login is called, **Then** access and refresh tokens are returned.
2. **Given** a valid gateway IPN, **When** received, **Then** the payment is confirmed and the user plan upgraded.

### User Story 6 - Inspect traces and health (Priority: P3)

Operators open per-story Langfuse traces and check dependency health.

**Acceptance Scenarios**:

1. **Given** Langfuse keys, **When** a story completes, **Then** the `done` event carries a trace link.
2. **Given** a dependency is down, **When** `/health` is called, **Then** status is `degraded` (HTTP 207).

### Edge Cases

- Local models wrap JSON in prose or code fences: `_json_loads` tolerates fences and embedded arrays; on failure the raw text becomes one bullet.
- Redis checkpointer unavailable: graph runs stateless (warning logged).
- Unknown `LLM_PROVIDER`: falls back to anthropic with a warning.
- No JWT and default secret: request is served as the seeded dev user.

## Requirements

### Functional Requirements (built)

- **FR-001**: `POST /api/v1/stories/generate` MUST stream SSE events `start`, `node_complete`, `done`, `error`.
- **FR-002**: The graph MUST run supervisor, then research/light/dark/facts in parallel, then writer, then synthesizer.
- **FR-003**: Light, dark and facts nodes MUST be skipped when their include flag is false; the writer MUST omit their sections.
- **FR-004**: Each node MUST cap output with `MAX_TOKENS_*` settings (research 300, light 250, dark 250, facts 200, writer 1500, synthesizer 500).
- **FR-005**: Per-call token usage and USD cost MUST be accumulated and returned in `node_complete` and `done`, and stored on the story.
- **FR-006**: Nodes MUST obtain models only through `get_adapter().chat(role, ...)`.
- **FR-007**: `LLM_PROVIDER` MUST select `anthropic` or `local`; `GET /api/v1/llm/config` MUST expose provider and role-to-model map without secrets.
- **FR-008**: `POST /api/v1/llm/ping` MUST run one real inference and require auth.
- **FR-009**: Personalities MUST support create, list, get, update, delete; banned words, voice, tone, reading level MUST reach the writer prompt.
- **FR-010**: Stories MUST support list (paginated), get, export Markdown, delete.
- **FR-011**: Auth MUST support register, login, refresh, me with bcrypt hashes and HS256 JWTs (access 60 min, refresh 30 days).
- **FR-012**: With no token and `JWT_SECRET_KEY == "changeme-in-production"`, the API MUST authenticate as the seeded dev user.
- **FR-013**: `POST /api/v1/payment/initiate` MUST create a gateway session and a `payments` row; `POST /api/v1/payment/ipn` MUST confirm and upgrade the plan.
- **FR-014**: Langfuse callback MUST be attached to each run when keys are configured; absence MUST be non-fatal.
- **FR-015**: Graph state MUST be checkpointed to Redis keyed by `thread_id = story_id`, falling back to stateless.
- **FR-016**: `/health` MUST report db, redis, langfuse and return 207 when degraded.
- **FR-017**: Frontend MUST provide Generate, Library, Story detail, Personalities and Settings pages, consuming SSE via fetch.
- **FR-018**: Schema changes MUST ship as Alembic migrations (`0001_initial`, `0002_add_password_hash`).

### Non-Functional Requirements (constitution-derived)

- **NFR-001 [GAP]**: Prompt caching MUST be applied to repeated system/personality prompts (Principle I). Not implemented.
- **NFR-002 [GAP]**: Semantic cache MUST short-circuit repeat topics (Principle I). Not implemented.
- **NFR-003 [GAP]**: Every user-data endpoint MUST authenticate and check ownership (Principle VI). Partially implemented.
- **NFR-004 [GAP]**: Payment confirmation MUST be verified with the gateway (Principle VI). Not implemented.
- **NFR-005 [GAP]**: Production MUST fail closed on the default JWT secret (Principle VI). Not implemented.
- **NFR-006 [GAP]**: Discarded LLM calls MUST NOT ship (Principle I). The supervisor route is discarded.
- **NFR-007 [GAP]**: Per-user quotas and rate limits MUST bound spend on the free plan.

### Key Entities

- **User**: id, email, password_hash, plan (free/pro/enterprise), stories_this_month, total_tokens_used.
- **Personality**: user, name, voice, tone, reading_level, banned_words, locale, is_default.
- **Story**: user, personality, inputs, section texts, status, tokens, cost, langgraph_run_id, embedding (unused).
- **Payment**: user, tran_id, val_id, amount, plan, status, ipn_payload.
- **StoryState**: LangGraph TypedDict (inputs, bullets lists with `operator.add`, draft, final, route, errors, token_usage, run_id).

## Success Criteria

- **SC-001**: Full E2E suite (Playwright, 38 tests in `e2e/`) passes against the running stack.
- **SC-002**: CI (lint, agent tests with mocked LLM, API tests) passes on every push.
- **SC-003**: Local story generation completes in under 60 s on the reference machine (documented 40-46 s).
- **SC-004 [GAP]**: Anthropic-provider cost per story at or below $0.19, target $0.08 (not measured in CI).
