# Tasks: Run Story Engine on AWS (Option S Serverless)

> **Go-live deferred, not scheduled (human, 2026-10-16).** Current mode: local deployment (docker
> compose). Production LLM = Amazon Bedrock. PRs #12, #14, #15, #17 are drafts and wait.

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md)
**Prerequisites**: D1-D9 answered (T001, 2026-10-16). D1 = Option S.
**Format**: `[status] [ID] [P?] Description (files) -> evidence | OWNER`. `[P]` = parallelisable.
**Status** (as of 2026-10-16): `[x]` done in draft (PR # and commit), `[~]` partial (what is
missing follows), `[ ]` open. Nothing is merged to `master` and nothing has run on AWS yet:
"done in draft" means code written and verified by cfn-lint, `sam validate`, stubbed tests and
local amd64 builds.
**Owner** of every open or partial task: **AGENT** (code we can do now), **HUMAN** (account, MFA,
bootstrap deploy, GitHub environment/variables, SSM values, Cloudflare NS, approvals, merges) or
**FIRST-DEPLOY** (only verifiable on real AWS; the human runs it, an agent assists and fixes).
**Commits**: #12 `prod-config-safety` d6dd06d5; #16 `jwt-login` 2cb78928; #13 `editor-haiku`
5840d6e3; #17 `aws-app` bd66b3a, afc2db3, 37aa2d65, f3ac2182; #15 `aws-infra` 20ac535, af194bb,
f63f6a24, c2e48a82; #14 `aws-deployment-plan` (this spec).
Tasks of the rejected alternatives (T024-T026, T032, T034, T037) were removed in v3 (research.md R1).

## Phase 1: Setup - decisions and prod readiness (P0)

- [x] T001 Record answers to D1-D9 in research.md R5 and the vault note -> #14 b1e84d9
- [~] T002 Merge HAG-17 `prod-config-safety` (`prod_guard`, `${VAR:?}` secrets) (`backend/app/core/prod_guard.py`) -> code #12 d6dd06d5; missing: review + merge | HUMAN
- [~] T003 [P] SPA login, bearer token on every fetch incl. the SSE stream, no dev-user fallback in production (`frontend/src/lib/auth.ts`, `LoginPage.tsx`, `backend/app/core/auth.py`) -> code #16 2cb78928; missing: rebase after #17, review + merge | HUMAN
- [ ] T004 [P] Bedrock model access in the AWS console (us-east-1): request access to the Claude models used (Haiku 5.5; Sonnet 5.5 if the editor stays on it), fill the Anthropic use-case form (Doctor-Assist bug 6), note the inference-profile IDs for the `Model*` stack parameters. The Anthropic API key is for local dev only; SSM `graph/ANTHROPIC_API_KEY` is optional and unused in prod | HUMAN
- [ ] T005 [P] Constitution amendment PR (`.specify/memory/constitution.md`): principle IV allows production with tracing off (D5, FR-010); Workflow: CD = manual GitHub Actions deploy job instead of `make deploy`. Blocks cutover (T041) | AGENT drafts 0.25 d, HUMAN approves
- [ ] T006 [P] Measure story duration on the prod models (p50/p95, longest silent gap between events) to confirm the 600 s deadline and 15 s ping. Needs paid tokens: run only on the human's go (locally on the Anthropic API, or on Bedrock after T004 + T044) | AGENT 0.25 d (blocked by the human's go)

## Phase 2: Foundational - AWS account baseline

- [ ] T007 AWS account hygiene: dedicated account, root MFA and no root keys, IAM Identity Center admin with MFA, us-east-1 (runbook section 1) | HUMAN
- [~] T008 GitHub OIDC provider + deploy role bound to environment `production`, CloudFormation execution role (`infra/bootstrap.yaml`) -> #15 20ac535; missing: deploy the bootstrap stack (runbook section 2) | HUMAN
- [~] T009 [P] ECR repository, scan on push, keep last 10; SAM artifact bucket; Route 53 zone; $25 budget (`infra/bootstrap.yaml`) -> #15 20ac535; missing: same bootstrap deploy as T008 | HUMAN

## Phase 3: User Story 1 - Readers use Story Engine from AWS (P1) MVP

- [~] T010 SAM template base: IAM roles, SSM read per function (`shared/` for story-api, `shared/` + `graph/` for story-graph, none for migrate) (`infra/template.yaml`) -> #15 20ac535, f63f6a24, c2e48a82; missing: SecureString values put by hand (runbook section 3; CloudFormation cannot create SecureStrings); `graph/ANTHROPIC_API_KEY` is optional with Bedrock | HUMAN
- [~] T011 Aurora Serverless v2 PG 16.11, min 0 ACU, auto-pause 300 s, Data API on, 7-day backups, deletion protection, final snapshot; `CREATE EXTENSION vector` runs in migrations 0001/0003 (`infra/template.yaml`) -> #15 20ac535; missing: first deploy creates it, migrate run proves pgvector on Aurora | FIRST-DEPLOY
- [~] T012 Move data: CSV export at home, `infra/scripts/dataapi_restore.py` loads it over the Data API with per-table row-count check (runbook section 6) -> #15 20ac535 (script + Stubber tests); missing: rehearsal on a copy, then the real move in a maintenance window right before T041 | HUMAN (FIRST-DEPLOY for the rehearsal)
- [x] T013 Async Data API dialect `postgresql+dataapi` under SQLAlchemy: bind casts (`::uuid`, enum, `::vector(384)`, timestamps, JSON), lazy transactions (FOR UPDATE in `enforce_quota`), `DatabaseResumingException` retry <= 45 s, `DB_BACKEND` switch (`backend/app/core/dataapi.py`, `database.py`) -> #17 bd66b3a (stubbed Data API + botocore Stubber tests)
- [ ] T014a Integration suite: every query path through the dialect (stories, auth, payments, quotas, rate limit, semantic cache) against a real Aurora, skipped unless `DATAAPI_RESOURCE_ARN` is set; not in CI (`backend/tests/integration/`) | AGENT 0.5 d
- [ ] T014b Run T014a against the staging Aurora; fix casts it finds (Doctor-Assist bug 2: UUID hints) | FIRST-DEPLOY
- [x] T015 Alembic over either backend (`build_engine`) + `migrate` Lambda handler reporting CodeDeploy hook status (`backend/alembic/env.py`, `app/migrate.py`) -> #17 bd66b3a, 37aa2d65; template #15 20ac535
- [x] T016 Remove Redis: `rate_limit_window` table + migration 0005, upsert; `CHECKPOINTER=none` default (`core/limits.py`, `agents/graph.py`, `alembic/versions/0005_rate_limit_window.py`) -> #17 bd66b3a
- [x] T017 Run deadline 600 s marks the story failed (`deadline`); quota ignores `running` rows older than 15 min (`api/v1/generate.py`, `core/limits.py`) -> #17 bd66b3a
- [x] T018 SSE `: ping` every 15 s while a node runs; Langfuse optional, lazy, `flush()` in the stream's `finally` (`api/v1/generate.py`, `core/observability.py`) -> #17 bd66b3a
- [~] T019a `api` image target: Lambda Web Adapter buffered, uvicorn single worker, `RUN_ROLE=api`, no LangGraph, LLM SDKs or ONNX model; build fails if `app.main` imports them; fresh-interpreter import test (`backend/Dockerfile.lambda`, `requirements-lambda-api.txt`, `app/main.py`, `tests/test_split_roles.py`) -> #17 afc2db3, f3ac2182 (amd64 build 461 MB, import 1.8 s); missing: arm64 build, which first runs in `deploy.yml` | FIRST-DEPLOY
- [~] T019b `graph` image target: `AWS_LWA_INVOKE_MODE=response_stream`, `RUN_ROLE=graph`, `app/graph_main.py` mounts only `POST /api/v1/stories/generate` + `/health` with the shared JWT, ownership and quota code; LangGraph + ONNX MiniLM baked in, lazy load (`backend/Dockerfile.lambda`, `app/graph_main.py`, `app/api/v1/generate.py`, `cache/semantic.py`) -> #17 afc2db3, f3ac2182 (amd64 build 924 MB, import 3.2 s, read-only FS ok); missing: arm64 build | FIRST-DEPLOY
- [~] T020a `story-api` 512 MB, 30 s, no function URL; API Gateway REST (Regional), `/`, `/api`, `/api/v1`, `/api/v1/stories` and `/{proxy+}` BUFFERED, stage throttling, `execute-api` endpoint disabled (`infra/template.yaml`) -> #15 c2e48a82; missing: confirm on real API Gateway that list/get under `/api/v1/stories` reach story-api next to the generate resource | FIRST-DEPLOY
- [~] T020b `story-graph` 2048 MB, 900 s, reserved concurrency 20, no function URL; `POST` + `OPTIONS /api/v1/stories/generate` STREAM (2021-11-15 streaming URI) (`infra/template.yaml`) -> #15 c2e48a82; missing: SPIKE: LWA `response_stream` output accepted by REST STREAM, events arrive one by one (runbook 5.6); fallback = function URL behind CloudFront (research.md R1) | FIRST-DEPLOY
- [x] T021 Real client IP from the API Gateway request context / last `X-Forwarded-For` hop; CORS `https://storyteller.techvigilant.com` set by the stack; SPA built with `VITE_API_BASE_URL=https://api.storyteller.techvigilant.com` (`core/client_ip.py`, `infra/template.yaml`, `deploy.yml`, `frontend/.env.production.example`) -> #17 bd66b3a, afc2db3; #15 af194bb, c2e48a82
- [~] T022 Route 53 zone (bootstrap); ACM cert for `storyteller` + `api.storyteller`; S3 + CloudFront (OAC, SPA fallback); API Gateway custom domain; alias records (`infra/template.yaml`, `infra/bootstrap.yaml`) -> #15 20ac535; missing: two ACM validation CNAMEs in Cloudflare (grey cloud) during the first deploy (runbook 5.2) | HUMAN
- [ ] T023 Rehearse NS delegation on a staging sub-zone (e.g. `staging-storyteller`); at cutover replace the `storyteller` Tunnel record with 4 NS records (runbook section 7) | HUMAN
- [x] T027 `BACKEND_PUBLIC_URL`, `FRONTEND_URL`, `BACKEND_CORS_ORIGINS` from the stack parameters, `VITE_API_BASE_URL` in the deploy; SSLCommerz IPN URL documented (runbook 7.5) -> #15 20ac535, c2e48a82; the live IPN check is T039
- [ ] T028 [P] E2E long-stream test: a stream >= 150 s with a >= 60 s silent node survives (FR-002); mocked slow LLM, runnable against staging (`e2e/api.spec.ts`) | AGENT 0.5 d
- [ ] T029 Run the SC-001 Playwright suites against the pinned staging names (runbook 5.5) | FIRST-DEPLOY

## Phase 4: User Story 2 - Deploy and roll back (P1)

- [~] T030 Deploy workflow: `workflow_dispatch` only (deploy / rollback), OIDC, CI-green check, build three arm64 targets, push, `sam deploy`, SPA sync + invalidation, `/health` smoke (`.github/workflows/deploy.yml`) -> #15 20ac535, c2e48a82; missing: GitHub environment `production` with required reviewers and the 5 repo variables from the bootstrap outputs (runbook section 4). Automatic deploy on green `master` stays off until the human approves | HUMAN
- [~] T031 `sam deploy`: CodeDeploy publishes versions, runs `migrate` as PreTraffic hook of both functions (migrate reserved concurrency 1), shifts each `live` alias; rollback by alias per function (`infra/template.yaml`, `deploy.yml`) -> #15 20ac535, c2e48a82; #17 37aa2d65; missing: verify on the first deploy that the second hook waits and succeeds (relies on async hook invokes being retried); first create needs one manual migrate invoke (runbook 5.4) | FIRST-DEPLOY
- [ ] T033 Rehearse a rollback of each function once and time it (SC-004); note ECR keeps 10 images and a deploy pushes 3, so about the last 3 deploys are reachable | FIRST-DEPLOY

## Phase 5: User Story 3 - Backups and restore (P2)

- [ ] T035 Restore drill: Aurora point-in-time restore to a scratch cluster, count `stories`, record time (SC-005), delete the scratch cluster (runbook section 8) | HUMAN

## Phase 6: User Story 4 - Monitoring (P3)

- [~] T036 [P] Alarms per function (Errors, Throttles, Duration p95), API Gateway 5xx, Aurora not pausing (`ServerlessDatabaseCapacity`), SNS email, log retention 14 days, $25 budget (`infra/template.yaml`, `infra/bootstrap.yaml`) -> #15 20ac535, c2e48a82; missing: an alarm on `/health` failure (FR-009): Route 53 health check on `api.storyteller/health` + alarm, or record that Api5xx covers it | AGENT 0.25 d
- [~] T038 Tracing per D5: `TRACING_ENABLED=false` in the stack, no `LANGFUSE_*` in SSM, flush in `finally` for local runs -> #17 bd66b3a; #15 af194bb; missing: constitution IV amendment (T005) | HUMAN (approval)
- [ ] T039 On staging: cold start and first event after a DB pause (SC-007); status code when `story-graph` is throttled; IPN end-to-end with the SSLCommerz sandbox | FIRST-DEPLOY

## Phase 7: Polish and cutover

- [ ] T040 Secret scan of the repo and the three images (AGENT now), then of the first deploy's CI logs (SC-006) | AGENT 0.25 d
- [ ] T041 Cutover: final data move (T012), NS-delegate `storyteller` to Route 53 (T023), smoke test; keep the home server read-only 7 days as fallback (runbook section 7) | HUMAN
- [ ] T042 Update vault notes (Hub, Architecture, AWS-Deployment-Architecture status) and diagrams after cutover | AGENT 0.25 d
- [ ] T043 Check the first monthly bill against SC-002; record real ACU-hours | HUMAN

## Phase 8: Follow-ups and integration

- [ ] T044 **Required** Bedrock adapter for production (D4 revised): new `bedrock` provider in `backend/app/llm/adapter.py` (langchain-aws `ChatBedrockConverse`), role -> inference-profile ID mapping, cost table, prompt-caching check, tests with a mocked client; `langchain-aws` in the `graph` image only; `prod_guard` accepts `bedrock` without `ANTHROPIC_API_KEY`; prod stack values `LlmProvider=bedrock`, `UseBedrock=true` and Bedrock `Model*` IDs (`infra/samconfig.toml`; the template parameters, Rule and IAM grant on story-graph already exist, #15 af194bb, c2e48a82). Local dev keeps `anthropic`. Not started | AGENT 1.5-2 d
- [ ] T045 Integrate the PRs in the order of plan.md "Implementation sequence": AGENT rebases #17 onto `master` after #12, rebases #16 after #17 (shared `config.py`, `SettingsPage.tsx`), resolves `MODEL_SYNTHESIZER` with #13; HUMAN reviews and merges | AGENT 0.5 d, HUMAN

## Status counts (2026-10-16)

| Status | Count | Tasks |
|---|---|---|
| Done in draft `[x]` | 8 | T001, T013, T015, T016, T017, T018, T021, T027 (none merged yet) |
| Partial `[~]` | 16 | T002, T003, T008-T012, T019a, T019b, T020a, T020b, T022, T030, T031, T036, T038 |
| Open `[ ]` | 18 | T004-T007, T014a, T014b, T023, T028, T029, T033, T035, T039-T045 |

## Dependencies & Execution Order

- T045 merge order (#12 -> #17 -> #15 -> #13 -> #14 -> #16) blocks any deploy: the template
  builds `backend/Dockerfile.lambda` from `master`.
- T007 -> T008/T009 (bootstrap) -> T010 (SSM values) + T030 (GitHub env) -> first deploy
  (T011, T022 CNAMEs, T031 manual migrate) -> spike T020b + T020a + T019a/b arm64 -> T014b, T029,
  T039 -> T033, T035 -> T012 rehearsal -> T005 merged -> T012 final move + T041 cutover.
- T044 + T004 block real generation on AWS (T029 with a real LLM, T039 first event).
- If the T020b spike fails: switch the generate route to a function URL behind CloudFront
  (research.md R1 fallback, ~1 d AGENT), then repeat the spike.

## Implementation Strategy

Build is mostly done in draft. Remaining work: merge (T045), stand up the account and bootstrap
(HUMAN), one staging deploy that answers the FIRST-DEPLOY questions, small AGENT tasks
(T014a, T028, T036, T040), rehearsals (T033, T035, T012, T023), then cutover. Critical path,
effort and risks: plan.md "Implementation sequence".
