# Tasks: Story Engine Baseline Remediation

**Input**: [spec.md](./spec.md), [plan.md](./plan.md)
**Format**: `[ID] [P?] [Req] Description (file)`; `[P]` = parallelisable.

## Phase 1: Security

- [ ] T001 [NFR-003] Require `get_current_user` and owner filter on story get/export/delete (`backend/app/api/v1/stories.py`)
- [ ] T002 [P] [NFR-003] Same for personality get/update/delete (`backend/app/api/v1/personalities.py`)
- [ ] T003 [NFR-003] Pytest: user B gets 404 on user A's story and personality (`backend/tests/test_ownership.py`)
- [ ] T004 [NFR-004] Authenticate `/payment/initiate`, use `user.id`, add `BACKEND_PUBLIC_URL` setting (`backend/app/payment/sslcommerz.py`, `core/config.py`)
- [ ] T005 [NFR-004] IPN: require signature, call SSLCommerz validation API with `val_id`, make `confirmed` terminal (`backend/app/payment/sslcommerz.py`)
- [ ] T006 [NFR-004] Pytest with mocked gateway: forged IPN rejected, replay idempotent (`backend/tests/test_payment.py`)
- [ ] T007 [NFR-005] Startup error when `DEBUG` false and `JWT_SECRET_KEY` is the default (`backend/app/core/config.py`, `main.py`)
- [ ] T008 [FR-011] Frontend login page and bearer header on all fetches (`frontend/src/`)

## Phase 2: Cost and correctness

- [ ] T009 [NFR-006] Remove supervisor node or make `route` skip sections (`backend/app/agents/nodes.py`, `graph.py`)
- [ ] T010 [FR-004] Move literal `max_tokens` (supervisor 50, ping 20) into `Settings.MAX_TOKENS_*` (`nodes.py`, `api/v1/llm.py`, `config.py`)
- [ ] T011 [FR-004] Set `MAX_TOKENS_SYNTHESIZER >= MAX_TOKENS_WRITER`; test final length is not shorter than draft by cap (`config.py`, `tests/test_agents.py`)
- [ ] T012 [FR-005] Compute story tokens and cost from final `token_usage`, include every node (`backend/app/api/v1/stories.py`)
- [ ] T013 [NFR-001] Add Anthropic `cache_control` to personality/system prompts (`backend/app/llm/adapter.py`, `nodes.py`)
- [ ] T014 [SC-004] Mock-LLM cost test that fails above $0.19 per story (`backend/tests/test_cost.py`)
- [ ] T015 [NFR-002] Spec the semantic cache (own spec, with cost estimate) before building

## Phase 3: Observability and data

- [ ] T016 [FR-014] Pass `user.id` to Langfuse callback; link the real trace id (`backend/app/api/v1/stories.py`)
- [ ] T017 [FR-010] Persist `research_bullets` to `stories.research`; include in export (`stories.py`)
- [ ] T018 [NFR-007] Increment `stories_this_month` / `total_tokens_used`; enforce free-plan limit; add rate limit (`stories.py`, `core/`)

## Phase 4: Hygiene

- [ ] T019 [P] [SC-002] Make `make deploy` smoke test fail on `degraded` (`Makefile:82`)
- [ ] T020 [P] Move Langfuse keys and DB password in prod compose to env (`docker-compose.prod.yml`)
- [ ] T021 [P] Align ports (8080) in Makefile and `main.py` docstring
- [ ] T022 [P] Dependency licence audit for GPL-3.0 compatibility (constitution VIII)
- [ ] T023 [P] Update vault Hub, Testing, Architecture to match `Decisions-vs-Code.md`
