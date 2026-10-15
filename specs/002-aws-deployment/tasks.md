# Tasks: Run Story Engine on AWS

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md)
**Prerequisites**: the human has answered D1-D7 (research.md R5). Do not start before D1 is decided.
**Format**: `[ID] [P?] [Story] Description (file)`; `[P]` = parallelisable. `[O1]` / `[O2]` = option only.
**Estimates**: person-days in brackets per phase; totals Option 1 = 6, Option 2 = 13 (before 20% contingency).

## Phase 1: Setup - decisions and prod readiness (P0, both options) [1.5 d]

- [ ] T001 Record answers to D1-D7 in research.md R5 and the vault note
- [ ] T002 Merge HAG-17 `prod-config-safety` (`prod_guard`, `${VAR:?}` secrets) into master (`backend/app/core/prod_guard.py`, `docker-compose.prod.yml`)
- [ ] T003 [P] Frontend sends the bearer token on every fetch; login works in prod build (`frontend/src/`)
- [ ] T004 [P] Funded Anthropic key (or Bedrock access if D4) available to the operator, not in git
- [ ] T005 [P] If D5 = Langfuse Cloud: constitution amendment PR for principle IV (`.specify/memory/constitution.md`)
- [ ] T006 Constitution amendment: CD via GitHub Actions deploy job instead of `make deploy` (`.specify/memory/constitution.md`)

**Checkpoint**: prod config fails closed on defaults; decisions recorded.

## Phase 2: Foundational - AWS account baseline (both options)

- [ ] T007 AWS account hygiene: MFA on root, budget alarm at the option's monthly estimate, chosen region (D2)
- [ ] T008 GitHub OIDC provider + least-privilege deploy role (`infra/`)
- [ ] T009 [P] ECR repository with scan on push and keep-last-10 lifecycle (`infra/`)
- [ ] T010 [P] Backend image: multi-stage, non-root, MiniLM model baked in, `--proxy-headers` (`backend/Dockerfile`)
- [ ] T011 [P] Frontend image / build takes `VITE_API_BASE_URL` as a build arg (`frontend/Dockerfile`)

**Checkpoint**: images build in CI and push to ECR through OIDC.

## Phase 3: User Story 1 - Readers use Story Engine from AWS (P1) MVP

### Option 1 Lean [O1] [P1-P2: 1.5 d]

- [ ] T012 [O1] Lightsail 8 GB (16 GB if self-hosted Langfuse) in region D2, static IP, firewall: no inbound ports (`infra/` or runbook)
- [ ] T013 [O1] Install Docker + compose plugin, SSM agent, instance role for ECR pull and S3 backups
- [ ] T014 [O1] Prod compose: `cloudflared` service with tunnel token, no published dev ports, env secrets from root-only file (`docker-compose.prod.yml`)
- [ ] T015 [O1] Point the Cloudflare Tunnel ingress for `storyteller.techvigilant.com` at the AWS host (staging hostname first)

### Option 2 Managed [O2] [P1-P4, P6: 8 d]

- [ ] T016 [O2] VPC, 2 AZs, public + private subnets, no NAT, security groups (ALB -> task -> DB/cache) (`infra/`)
- [ ] T017 [O2] RDS PostgreSQL 16 `db.t4g.small`, `CREATE EXTENSION vector`, 7-day backups (`infra/`)
- [ ] T018 [P] [O2] ElastiCache Valkey `cache.t4g.micro` with in-transit TLS (`infra/`)
- [ ] T019 [P] [O2] Secrets Manager entries and task execution role access (`infra/`)
- [ ] T020 [O2] ECS cluster, task definition 1 vCPU / 2 GB ARM64, service behind ALB, idle timeout 300 s, health `/health` (`infra/`)
- [ ] T021 [O2] One-off migrate task running `alembic upgrade head` (`infra/`)
- [ ] T022 [P] [O2] S3 + CloudFront for the SPA with origin access control and SPA fallback; API host direct to ALB (`infra/`)
- [ ] T023 [O2] Config for TLS: `DATABASE_URL` SSL and `REDIS_URL=rediss://` (`backend/app/core/config.py`, `backend/app/core/database.py`)
- [ ] T024 [O2] ACM certificate and DNS records (Cloudflare or Route 53 per D3)

### Both

- [ ] T025 Set `BACKEND_PUBLIC_URL`, `FRONTEND_URL`, `BACKEND_CORS_ORIGINS` to the public hosts; check SSLCommerz callback URLs
- [ ] T026 E2E long-stream test: a story stream of >= 150 s survives every hop (FR-002) (`e2e/api.spec.ts`)
- [ ] T027 Run the 38 Playwright tests against the staging URL (SC-001)

**Checkpoint**: staging URL serves the full app from AWS.

## Phase 4: User Story 2 - Deploy and roll back (P1) [O1 1.0 d / O2 1.5 d]

- [ ] T028 Deploy workflow on green `master`: OIDC, build, push, migrate, deploy, `/health` smoke (`.github/workflows/deploy.yml`)
- [ ] T029 [O1] Deploy step via SSM Run Command: `docker compose pull && up -d`, then migrate
- [ ] T030 [O2] Deploy step: run migrate task, update ECS service, wait for stable
- [ ] T031 Rollback by previous image tag, rehearsed once (SC-004) (`docs/runbook-aws.md`)

## Phase 5: User Story 3 - Backups and restore (P2) [O1 1.0 d / O2 in T017]

- [ ] T032 [O1] Nightly `pg_dump` to versioned S3 bucket, 30-day lifecycle; Lightsail auto snapshots on
- [ ] T033 Restore drill into a scratch database; record time (SC-005) (`docs/runbook-aws.md`)
- [ ] T034 Move data from the home server: dump, restore, row-count check, then cutover

## Phase 6: User Story 4 - Monitoring (P3) [O1 0.5 d / O2 part of 2.0 d]

- [ ] T035 [P] CloudWatch alarm on `/health` (uptime check) and disk / DB storage > 80% (FR-009)
- [ ] T036 [P] [O2] Log groups with 14-day retention; alarms on ALB 5xx and task CPU
- [ ] T037 Langfuse reachable from the backend per D5; a trace appears for a test story (FR-010)

## Phase 7: Polish and cutover [O1 0.5 d / O2 rest of 2.0 d]

- [ ] T038 Secret scan of repo, images and CI logs (SC-006)
- [ ] T039 Cutover: switch DNS / tunnel to AWS, keep the home server read-only for 7 days as fallback
- [ ] T040 Update vault notes (Hub, Architecture, AWS-Deployment-Architecture status) and the architecture diagram
- [ ] T041 Check the first monthly bill against SC-002

## Dependencies & Execution Order

- Phase 1 (P0) blocks everything. D1 decides which of the [O1] / [O2] tasks run.
- Phase 2 blocks Phase 3. Phase 3 blocks Phases 4-7.
- T034 data move and T039 cutover run last, after T031 rollback and T033 restore are rehearsed.
- `[P]` tasks touch different files and can run in parallel.

## Implementation Strategy

MVP = Phase 1-3 on a staging hostname, then Phase 4-5, then cutover. If Option 1 is chosen and
traffic later grows, re-run Phase 3 [O2] tasks with the same images; nothing in the app changes shape.
