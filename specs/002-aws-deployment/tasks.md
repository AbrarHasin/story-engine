# Tasks: Run Story Engine on AWS

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md)
**Prerequisites**: the human has answered D1-D9 (research.md R5). Do not start before D1 is decided.
**Format**: `[ID] [P?] [Story] Description (file)`; `[P]` = parallelisable. `[OS]` / `[O1]` = option only.
**Estimates**: person-days per phase; totals Option S = 12 (11.5 + 0.5 for ADR `split-api-graph`), Option 1 = 6 (before 20% contingency).

## Phase 1: Setup - decisions and prod readiness (P0, both) [1.5 d]

- [x] T001 Record answers to D1-D9 in research.md R5 and the vault note (2026-10-16: S, us-east-1, Route 53, Anthropic, Langfuse local only; D6-D9 defaults)
- [ ] T002 Merge HAG-17 `prod-config-safety` (`prod_guard`, `${VAR:?}` secrets) (`backend/app/core/prod_guard.py`)
- [ ] T003 [P] Frontend sends the bearer token on every fetch; login works in a prod build (`frontend/src/`)
- [ ] T004 [P] Funded Anthropic key (or Bedrock access if D4), not in git
- [ ] T005 [P] Constitution amendment PRs: CD via GitHub Actions; principle IV if D5 = Langfuse Cloud (`.specify/memory/constitution.md`)
- [ ] T006 [P] Measure story duration on the prod models (p50/p95, longest silent gap between events) to confirm the 600 s deadline and 15 s ping

## Phase 2: Foundational - AWS account baseline (both)

- [ ] T007 AWS account hygiene: no root keys, MFA, budget alarm at the option's estimate, region D2
- [ ] T008 GitHub OIDC provider + least-privilege deploy role (`infra/`)
- [ ] T009 [P] ECR repository, scan on push, keep last 10 (`infra/`)

## Phase 3: User Story 1 - Readers use Story Engine from AWS (P1) MVP

### Option S Serverless [OS] [P1-P5: 8.0 d]

- [ ] T010 [OS] SAM template base: SSM SecureString parameters, IAM roles (`infra/template.yaml`) [1.0 d with T008-T009]
- [ ] T011 [OS] Aurora Serverless v2 PG 16 (>= 16.3), min 0 ACU, auto-pause 300 s, Data API on, 7-day backups; `CREATE EXTENSION vector` (`infra/`)
- [ ] T012 [OS] Move data: `pg_dump` from the home server, restore into Aurora, row-count check (`docs/runbook-aws.md`)
- [ ] T013 [OS] Async Data API adapter under SQLAlchemy: params, transactions (FOR UPDATE in `enforce_quota`), `::uuid` / `::vector` casts, timestamps, `DatabaseResumingException` retry up to 45 s (`backend/app/core/dataapi.py`, `database.py`) [3.0 d with T014-T015]
- [ ] T014 [OS] Integration tests: every query path through the adapter against a real Aurora (stories, auth, payments, quotas, semantic cache) (`backend/tests/integration/`)
- [ ] T015 [OS] Alembic over the Data API (sync dialect or the adapter) + `migrate` Lambda (`backend/alembic/env.py`, `infra/`)
- [ ] T016 [OS] Remove Redis: `rate_limit_window` table + migration 0005, upsert in the quota transaction; `CHECKPOINTER=none` (`core/limits.py`, `agents/graph.py`, `alembic/versions/`)
- [ ] T017 [OS] Run deadline 600 s marks the story failed; quota ignores `running` rows older than 15 min (`api/v1/stories.py`, `core/limits.py`)
- [ ] T018 [OS] SSE `: ping` comment every 15 s while a node runs; Langfuse `flush()` in the stream's `finally` (`api/v1/stories.py`, `core/observability.py`)
ADR `split-api-graph` (research.md R7): T019 and T020 are split into `api` and `graph` tasks (+0.5 d).

- [ ] T019a [OS] `api` image target: arm64, Lambda Web Adapter (buffered), uvicorn single worker, no LangGraph, LLM SDKs or ONNX model in the image; imports of them absent or lazy so CRUD cold starts stay fast; import-guard test (`backend/Dockerfile.lambda` target `api`, `main.py`)
- [ ] T019b [OS] `graph` image target: arm64, Lambda Web Adapter, `AWS_LWA_INVOKE_MODE=response_stream`, minimal FastAPI app mounting only `POST /api/v1/stories/generate` with the shared JWT, ownership and quota code; LangGraph + ONNX MiniLM baked in, lazy load (`backend/Dockerfile.lambda` target `graph`, `app/main_graph.py`, `cache/semantic.py`)
- [ ] T020a [OS] `story-api` function 512 MB, timeout 30 s, no function URL; API Gateway REST API (Regional), `ANY /{proxy+}` Lambda proxy BUFFERED, stage throttling, default `execute-api` endpoint disabled (`infra/`)
- [ ] T020b [OS] `story-graph` function 2048 MB, timeout 900 s, reserved concurrency (e.g. 20), no function URL; resource `/api/v1/stories/generate` `POST` Lambda proxy with response transfer mode `STREAM`, integration timeout 900 s; spike first: LWA `response_stream` output accepted by API Gateway (`infra/`)
- [ ] T021 [OS] Real client IP from the API Gateway request context / `X-Forwarded-For`; CORS allows `https://storyteller.techvigilant.com`; SPA built with `VITE_API_BASE_URL=https://api.storyteller.techvigilant.com` (`main.py`, `core/config.py`, frontend build)
- [ ] T022 [OS] Route 53 public hosted zone `storyteller.techvigilant.com` ($0.50/month); ACM cert in us-east-1 for `storyteller` + `api.storyteller`, DNS-validated in the zone; S3 bucket + CloudFront (OAC, SPA fallback, SPA only); API Gateway custom domain `api.storyteller` (Regional); alias records apex -> CloudFront, `api` -> API Gateway (`infra/`)
- [ ] T023 [OS] Cloudflare: at cutover replace the `storyteller` Tunnel record with 4 NS records pointing at the Route 53 zone (as `doc.techvigilant.com`); no Cloudflare proxy or Tunnel left on the path (rehearse on a staging sub-zone first)

### Option 1 Lean [O1] [P1-P3: 2.5 d]

- [ ] T024 [O1] Lightsail 8 GB (16 GB if self-hosted Langfuse), static IP, no inbound ports; Docker, SSM agent, instance role
- [ ] T025 [O1] Prod compose: `cloudflared` service, no dev ports, env secrets (`docker-compose.prod.yml`)
- [ ] T026 [O1] Tunnel ingress for `storyteller.techvigilant.com` -> AWS host (staging host first)

### Both

- [ ] T027 `BACKEND_PUBLIC_URL`, `FRONTEND_URL`, `BACKEND_CORS_ORIGINS`, `VITE_API_BASE_URL` for the public host; check SSLCommerz URLs
- [ ] T028 E2E long-stream test: a stream >= 150 s with a >= 60 s silent node survives (FR-002) (`e2e/api.spec.ts`)
- [ ] T029 Run the Playwright suite against the staging URL (SC-001)

## Phase 4: User Story 2 - Deploy and roll back (P1) [OS 1.0 d / O1 1.0 d]

- [ ] T030 Deploy workflow on green `master`: OIDC, build, push, migrate, deploy, `/health` smoke (`.github/workflows/deploy.yml`)
- [ ] T031 [OS] `sam deploy`: build and push the `api`, `graph` and `migrate` image targets, publish versions, invoke `migrate`, shift the `live` alias of `story-api` and `story-graph`, roll back by alias
- [ ] T032 [O1] SSM Run Command: `docker compose pull && up -d`, then migrate
- [ ] T033 Rollback rehearsed once (SC-004) (`docs/runbook-aws.md`)

## Phase 5: User Story 3 - Backups and restore (P2) [OS in T011 / O1 1.0 d]

- [ ] T034 [O1] Nightly `pg_dump` to versioned S3, 30-day lifecycle; Lightsail snapshots
- [ ] T035 Restore drill ([OS] point-in-time restore to a scratch cluster), record time (SC-005)

## Phase 6: User Story 4 - Monitoring (P3) [OS part of 1.5 d / O1 0.5 d]

- [ ] T036 [P] [OS] Alarms per function (`story-api`, `story-graph`): Lambda Errors, Throttles, Duration p95, `ServerlessDatabaseCapacity`; log retention 14 days; budget alarm $25
- [ ] T037 [P] [O1] Alarm on `/health` and disk > 80%
- [ ] T038 Langfuse reachable per D5; a trace appears for a test story, also after a cold start (FR-010)
- [ ] T039 [OS] Measure cold start and first event after a DB pause (SC-007); IPN end-to-end with SSLCommerz sandbox

## Phase 7: Polish and cutover [OS rest of 1.5 d / O1 0.5 d]

- [ ] T040 Secret scan of repo, images and CI logs (SC-006)
- [ ] T041 Cutover: [OPT-S] NS-delegate `storyteller` to Route 53 (T023), [OPT-1] switch the Tunnel; keep the home server read-only for 7 days as fallback
- [ ] T042 Update vault notes (Hub, Architecture, AWS-Deployment-Architecture status) and diagrams
- [ ] T043 Check the first monthly bill against SC-002; record real ACU-hours

## Dependencies & Execution Order

- Phase 1 blocks everything; D1 picks [OS] or [O1] tasks; D7 = VPC replaces T013-T015 with
  "Lambda in VPC, asyncpg `NullPool`, NAT instance" (~1 day).
- [OS] T011 blocks T012-T016; T013 blocks T014-T016; T019a blocks T020a, T019b blocks T020b; T019a-T021 block T022; T022 blocks T023.
- T012 final data move and T041 cutover run last, after T033 rollback and T035 restore are rehearsed.

## Implementation Strategy

MVP = Phases 1-3 on a staging hostname, then 4-6, then cutover. If Option 1 ships first for speed,
Option S can follow later: only T010-T023 and T031 are added; the app changes in T013-T021 also run
unchanged on Lean (Postgres-backed rate limit, ping, deadline, flush).
