# Implementation Plan: Run Story Engine on AWS

**Branch**: `aws-deployment-plan` | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)
**Input**: spec.md, [research.md](./research.md), vault note `Projects/Story-Engine/AWS-Deployment-Architecture.md`.

## Summary

Move the running compose stack from the home server to AWS. Two options are planned so the human
can choose (D1): **Option 1 Lean** (one Lightsail host, same compose, Cloudflare Tunnel; ~$50/month,
6 person-days) and **Option 2 Managed** (ECS Fargate, RDS + pgvector, ElastiCache, ALB,
S3/CloudFront, Secrets Manager, ECR, CloudWatch, GitHub OIDC; ~$104-162/month, 13 person-days).
**Recommended: Option 1**, because it is about half the cost and effort at low traffic and its images
move to Option 2 unchanged. No build work starts until the human answers D1-D7 (research.md R5).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5 / React 18 / Vite (frontend)
**Primary Dependencies**: FastAPI, LangGraph 1.x, SQLAlchemy async, Alembic, Langfuse v3, sentence-transformers
**Storage**: PostgreSQL 16 + pgvector; Redis 7 / Valkey; S3 for backups (and SPA in Option 2)
**Testing**: pytest with mocked LLM in CI; Playwright e2e against the deployed URL; restore drill
**Target Platform**: AWS, one region (D2). Option 1 Lightsail Linux host; Option 2 ECS Fargate ARM64
**Project Type**: web service + SPA (existing)
**Performance Goals**: SSE streams up to 300 s without cut; deploy <= 15 min; rollback <= 10 min
**Constraints**: hosting <= $60/month (Opt 1) or <= $120 / $180 (Opt 2); no NAT gateway; no secrets in git or images
**Scale/Scope**: under 1,000 stories/month, a few concurrent streams

## Constitution Check

| Principle | Status | Note |
|---|---|---|
| I Token cost | PASS | Hosting only; per-story LLM cost unchanged (~$0.0073). Bedrock (D4) would need its own cost delta. |
| II Model tiering | PASS | No model change. |
| III Provider-agnostic | PASS | Bedrock, if chosen, is a new adapter, not node edits. |
| IV Observable | PASS / DECIDE | Self-hosted Langfuse complies. Langfuse Cloud (D5) requires a constitution amendment PR first. |
| V Streaming contract | PASS with work | FR-002 sets 300 s on every hop; covered by an e2e long-stream test. |
| VI Secure by default | DEPENDS ON P0 | Needs HAG-17 `prod_guard`, real secrets, frontend token; FR-004/005/012 add secrets store, OIDC, no open ports. |
| VII Test discipline | PASS | CI stays mocked; deploy job adds `/health` smoke and post-deploy e2e. |
| VIII Licensing | PASS | No new runtime dependency in Option 1; Option 2 IaC tool (D6) is not shipped in the app. Terraform is BUSL-1.1 (tooling only, unverified impact); OpenTofu (MPL-2.0) is the GPL-friendly fallback. |
| Workflow: CD = `make deploy` + `/health` smoke | AMEND | CD moves to a GitHub Actions deploy job; the constitution's Development Workflow line needs an amendment when this is built. |

## Project Structure

### Documentation (this feature)

```text
specs/002-aws-deployment/
├── spec.md       # what and why, two options
├── plan.md       # this file
├── research.md   # prices with sources, findings, open decisions D1-D7
└── tasks.md      # phased tasks for both options
```

### Source Code (repository root) - files the build would touch (none touched by this plan)

```text
docker-compose.prod.yml      # Opt 1: env secrets, cloudflared service, no dev ports
nginx/prod.conf              # keep 300 s, no buffering
backend/Dockerfile           # multi-stage, non-root, bake MiniLM model, proxy headers
backend/app/core/config.py   # DB/Redis TLS settings (Opt 2), public URLs
frontend/Dockerfile          # build arg VITE_API_BASE_URL
.github/workflows/deploy.yml # new: OIDC deploy job (both options)
infra/                       # new: Opt 1 small Terraform/CDK or scripts; Opt 2 full IaC (D6)
docs/runbook-aws.md          # new: deploy, rollback, restore
```

**Structure Decision**: infrastructure code lives under a new top-level `infra/` so app code stays
unchanged in shape; nothing is created by this planning branch.

## Phases

| Phase | Option 1 Lean | Days | Option 2 Managed | Days |
|---|---|---|---|---|
| P0 | Prod readiness (shared) | 1.5 | Prod readiness (shared) | 1.5 |
| P1 | Lightsail host, Docker, firewall | 0.5 | IaC base: VPC, SGs, IAM, OIDC, ECR | 2.0 |
| P2 | Prod compose, cloudflared, env secrets | 1.0 | RDS + pgvector, ElastiCache, Secrets Manager, data move | 1.5 |
| P3 | Data move, pg_dump to S3, restore drill | 1.0 | Slim image, ECS service, ALB 300 s, migrate task | 2.5 |
| P4 | CI/CD to ECR + SSM deploy | 1.0 | S3 + CloudFront SPA, api host | 1.0 |
| P5 | Monitoring, runbook | 0.5 | OIDC deploy workflow, rollback | 1.5 |
| P6 | Cutover | 0.5 | Code + config: TLS, proxy headers, URLs | 1.0 |
| P7 | - | - | Monitoring, cutover, SSE load test, runbook | 2.0 |
| **Total** | | **6** | | **13** |

Add 20% contingency: Option 1 ~7, Option 2 ~16 person-days.

## Complexity Tracking

| Violation / addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| Option 2 adds IaC, VPC, five managed services | Managed backups, HA, scaling | Option 1 is the simpler alternative and is the recommendation |
| CD moves from `make deploy` to a deploy job | No shell on the home server any more | SSH-from-laptop deploys break FR-005 (OIDC, no stored keys) |
