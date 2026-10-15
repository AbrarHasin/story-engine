# Implementation Plan: Run Story Engine on AWS

**Branch**: `aws-deployment-plan` | **Date**: 2026-10-16 (v2.2, ADR split-api-graph) | **Spec**: [spec.md](./spec.md)
**Input**: spec.md, [research.md](./research.md), vault notes `Projects/Story-Engine/AWS-Deployment-Architecture.md`
and `Projects/Doctor-Assistant/Cloud-Architecture.md` (Doctor-Assist spec 008, the design this follows).

## Summary

**Recommended: Option S Serverless**, modelled on Doctor-Assist: the existing FastAPI app runs as two
Lambda functions behind the Lambda Web Adapter, split by route at an API Gateway REST API on
`api.storyteller.techvigilant.com` (replaces nginx; ADR `split-api-graph`, research.md R7):
`story-api` (every route except generation, buffered) and `story-graph` (`POST /api/v1/stories/generate`
only, response streaming, LangGraph + semantic cache), plus the `migrate` function; CloudFront serves only the
SPA from S3 on `storyteller.techvigilant.com`; both names sit in a Route 53 hosted zone NS-delegated
from Cloudflare (decided 2026-10-16, as Doctor-Assist); Aurora Serverless v2 PostgreSQL + pgvector
(minimum 0 ACU, auto-pause) is reached through the RDS Data API, so the Lambda needs no VPC and no NAT;
Redis is removed. About **$12.60/month** at 1,000 stories, **~$2 idle**, **11.5 person-days** (~14 with
contingency).

**Baseline: Option 1 Lean** (one Lightsail host, same compose, Cloudflare Tunnel): ~$50/month flat,
6 person-days. Choose it if go-live speed matters more than ~$38/month. Option 2 Managed (Fargate,
~$104-162/month, 13 person-days) is not pursued. No build work starts until D1-D9 are answered.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5 / React 18 / Vite (frontend)
**Primary Dependencies**: FastAPI, LangGraph 1.x, SQLAlchemy async, Alembic, Langfuse, embeddings
([OPT-S] ONNX MiniLM instead of torch); [OPT-S] AWS Lambda Web Adapter, boto3 `rds-data`
**Storage**: [OPT-S] Aurora Serverless v2 PostgreSQL 16 + pgvector via Data API; S3 for the SPA.
[OPT-1] Postgres + Redis containers; S3 for backups
**Testing**: pytest with mocked LLM in CI; [OPT-S] shim tests against a real Aurora; Playwright e2e on the deployed URL
**Target Platform**: AWS, one region (D2). [OPT-S] three Lambda arm64 container images from one Dockerfile (targets `api`, `graph`, `migrate`); [OPT-1] Lightsail Linux host
**Project Type**: web service + SPA (existing)
**Performance Goals**: SSE streams up to 600 s; first event p95 <= 5 s warm DB; deploy <= 15 min; rollback <= 10 min
**Constraints**: [OPT-S] <= $20/month at low traffic, <= $5 idle; no NAT gateway, no ALB, no always-on compute; no secrets in git or images
**Scale/Scope**: under 1,000 stories/month, a few concurrent streams

### [OPT-S] Functions (ADR `split-api-graph`, 2026-10-16)

| Function | Routes (API Gateway REST) | Integration | Memory | Timeout | Concurrency | Image target | Holds |
|---|---|---|---|---|---|---|---|
| `story-api` | `ANY /{proxy+}`: auth, stories CRUD/list/export, personalities, payments + SSLCommerz IPN, LLM config, `/health` | BUFFERED | 512 MB | 30 s | account pool | `api` | FastAPI only; no LangGraph, LLM SDKs or ONNX model (absent or lazy imports): fast cold start |
| `story-graph` | `POST /api/v1/stories/generate` (SSE) | STREAM | 2048 MB | 900 s (app deadline 600 s) | reserved, e.g. 20 (caps LLM spend and Aurora load) | `graph` | minimal FastAPI app mounting only the generate route; LangGraph + semantic cache (ONNX MiniLM); JWT check, ownership and quota from the shared code package |
| `migrate` | none (CodeDeploy PreTraffic hook / manual invoke) | - | as today | as today | 1 | `migrate` | Alembic |

No Lambda calls another Lambda: API Gateway picks the function by route. Each side gets its own
memory, timeout, concurrency cap and image; CRUD cold starts no longer load LangGraph or ONNX; a
burst of generations cannot starve login or CRUD; a failure in one function does not take down the other.

## Constitution Check

| Principle | Status | Note |
|---|---|---|
| I Token cost | PASS | Hosting only; per-story LLM cost unchanged (~$0.0073). |
| II Model tiering | PASS | No model change. |
| III Provider-agnostic | PASS | Bedrock (D4) would be a new adapter, not node edits. |
| IV Observable | PASS / DECIDE | Langfuse on the home server via Tunnel complies; Langfuse Cloud (D5) needs an amendment. Self-host on AWS breaks the cost case. |
| V Streaming contract | PASS with work | Same events; [OPT-S] adds `: ping` comments (ignored by SSE clients) and a 600 s run deadline. |
| VI Secure by default | DEPENDS ON P0 | Plus API Gateway as the only way in (throttling, no function URL), IAM-only DB access, Parameter Store, OIDC. |
| VII Test discipline | PASS with work | CI stays mocked; Data API shim needs an integration suite against Aurora (not in CI by default). |
| VIII Licensing | PASS | Lambda Web Adapter Apache-2.0, fastembed Apache-2.0, AWS SAM CLI Apache-2.0 (tooling). |
| Workflow: CD = `make deploy` + `/health` smoke | AMEND | CD moves to a GitHub Actions deploy job. |

## Project Structure

### Documentation (this feature)

```text
specs/002-aws-deployment/
  spec.md       # what and why; Option S recommended, Option 1 baseline
  plan.md       # this file
  research.md   # prices with sources, Doctor-Assist comparison, decisions D1-D9
  tasks.md      # phased tasks for Option S and Option 1
```

### Source Code - files the build would touch (none touched by this plan)

```text
backend/Dockerfile.lambda        # [OPT-S] arm64, Lambda Web Adapter; targets api (slim), graph (LangGraph + ONNX baked in), migrate
backend/app/main_graph.py        # [OPT-S] new: minimal FastAPI app, generate route only (story-graph)
backend/app/core/database.py     # [OPT-S] engine over the Data API shim (or NullPool asyncpg if D7 = VPC)
backend/app/core/dataapi.py      # [OPT-S] new: async Data API adapter, casts, resume retry
backend/app/core/limits.py       # [OPT-S] Postgres rate-limit window; ignore stale running rows
backend/app/api/v1/stories.py    # [OPT-S] SSE ping every 15 s, 600 s deadline, Langfuse flush
backend/app/agents/graph.py      # [OPT-S] checkpointer off by setting
backend/app/cache/semantic.py    # [OPT-S] ONNX embedder, lazy load
backend/alembic/versions/0005_*  # [OPT-S] rate_limit_window table
frontend (build config)          # [OPT-S] VITE_API_BASE_URL = https://api.storyteller.techvigilant.com
backend/app/core/config.py       # [OPT-S] BACKEND_CORS_ORIGINS += https://storyteller.techvigilant.com
.github/workflows/deploy.yml     # new: OIDC deploy job (both options)
infra/template.yaml              # [OPT-S] AWS SAM: story-api + story-graph + migrate Lambdas, API Gateway REST (generate -> STREAM, proxy -> BUFFERED), Route 53 zone, ACM, Aurora, CloudFront, S3, alarms (D6)
docs/runbook-aws.md              # new: deploy, rollback, restore, resume behaviour
```

**Structure Decision**: infrastructure lives under a new top-level `infra/`, as in Doctor-Assist;
the app keeps its shape; Option S adds a small database adapter (no origin guard: API Gateway is
the only way in).

## Phases

| Phase | Option S Serverless | Days | Option 1 Lean | Days |
|---|---|---|---|---|
| P0 | Prod readiness (shared) | 1.5 | Prod readiness (shared) | 1.5 |
| P1 | SAM base: ECR, OIDC role, SSM parameters, budget | 1.0 | Lightsail host, Docker, firewall | 0.5 |
| P2 | Aurora SV2 + pgvector + Data API, data move | 1.0 | Prod compose, cloudflared, env secrets | 1.0 |
| P3 | Data access over Data API (shim, txns, casts, retry, tests) | 3.0 | Data move, pg_dump to S3, restore drill | 1.0 |
| P4 | Lambda images: Web Adapter (stream spike behind REST API first), api/graph split (slim api target, graph entry app), ping, deadline, flush, no Redis, ONNX | 2.0 | CI/CD to ECR + SSM deploy | 1.0 |
| P5 | Edge: Route 53 zone + NS delegation, ACM, API Gateway REST (STREAM, custom domain, throttling), S3 + CloudFront SPA, CORS | 1.0 | Monitoring, runbook | 0.5 |
| P6 | CI/CD: OIDC, migrate Lambda, alias deploy + rollback | 1.0 | Cutover | 0.5 |
| P7 | Alarms, IPN + long-stream + cold-start tests, runbook, cutover | 1.5 | - | - |
| **Total** | | **12** | | **6** |

Add 20% contingency: Option S ~14.5, Option 1 ~7. If D7 = Lambda in VPC with asyncpg + NAT instance,
Option S P3 drops to ~1.0 day (total ~10) for ~$7/month more. The api/graph split (ADR
`split-api-graph`) adds 0.5 day (P4 1.5 -> 2.0; edge routes and the second function in P5 fit the
existing day). Cost is about neutral to slightly lower: CRUD runs at 512 MB instead of 2048 MB
(~243k GB-s instead of ~252k, still inside the free tier), one more function, still ~$0 idle compute.

## Complexity Tracking

| Violation / addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| Data API adapter under SQLAlchemy async | Keeps Lambda out of the VPC: no NAT ($33/month), no open DB port; Doctor-Assist pattern | Lambda in VPC + NAT instance is D7's alternative; it is cheaper in effort, dearer per month and adds a host to patch |
| SSE heartbeat + run deadline | Keeps any proxy between browser and API Gateway from dropping an idle stream (API Gateway idle limit 5 min); Lambda timeout skips `finally` | None: without them streams drop and stories stick in `running` |
| Redis removed | No always-on cache in a serverless stack | ElastiCache Serverless or a node costs more than the whole Option S bill |
| Two app functions (`story-api`, `story-graph`) instead of one | Separate memory, timeout, concurrency cap and image; CRUD cold starts skip LangGraph/ONNX; generation bursts cannot starve login/CRUD (ADR `split-api-graph`) | One function: 2048 MB/900 s for every CRUD call and shared concurrency. Lambda->Lambda invoke: both run the whole story (double compute). SQS/Step Functions: breaks token streaming |
| CD moves from `make deploy` to a deploy job | No home server shell any more | SSH-from-laptop deploys break FR-005 |
