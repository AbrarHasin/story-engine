# Research: Run Story Engine on AWS

**Spec**: [spec.md](./spec.md) | **Date**: 2026-10-16 (v2, serverless first; v2.2 adds R7 ADR split-api-graph; v3 Option S chosen, R8 analysis; v3.1 Bedrock for prod, go-live deferred)
**Method**: v1 read `docker-compose*.yml`, `nginx/prod.conf`, Dockerfiles, `config.py`, `requirements.txt`,
CI, Makefile. v2 also read `core/limits.py`, `core/database.py`, `api/v1/stories.py`, `payment/sslcommerz.py`,
`agents/graph.py`, `cache/semantic.py`, and the Doctor-Assist cloud note (spec 008, live since 2026-07-29).
Prices by web search on 2026-10-16. No AWS account, CLI or API key was used.

## R1. Options considered

| Option | Shape | Verdict |
|---|---|---|
| S Serverless | Two Lambdas split by route (`story-api` buffered, `story-graph` streaming; R7) + `migrate` (containers, Web Adapter) behind API Gateway REST response streaming + Route 53 sub-zone + CloudFront/S3 (SPA) + Aurora Serverless v2 via Data API + SSM + ECR, GitHub OIDC, SAM | **Chosen (D1, human, 2026-10-16)** |
| 1 Lean (Lightsail + compose) / 2 Managed (Fargate + RDS + ALB) | - | **Rejected 2026-10-16 (human): removed from planning; ~$50 and ~$104/month flat, a host or more to run** |
| API Gateway HTTP API + Mangum (Doctor-Assist's API edge) | Buffered, 30 s integration limit | Rejected for Story Engine: no SSE |
| API Gateway REST API with response streaming | Up to 15 min, 5 min idle (Regional), Nov 2025 | **Chosen edge (2026-10-16)**: the only AWS edge that streams a Lambda response; replaces nginx |
| ALB -> Lambda target | Reply is one JSON, max 1 MB, Content-Length computed first ([AWS](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/lambda-functions.html)); ~$16/month floor | Rejected: no streaming |
| CloudFront -> Lambda function URL (v2 plan) | Streams; needs `X-Origin-Verify` guard because OAC breaks POST | Superseded by API Gateway REST; kept as fallback if the LWA-behind-REST spike fails |
| App Runner, EKS | - | Rejected (v1) |

**Decision**: Option S (D1, human, 2026-10-16). **Rationale**: ~$12.60/month at 1,000 stories and ~$2 idle and ~$2.40 idle;
no host to patch; reuses a design already debugged live in
Doctor-Assist. Most of the effort is the Data API adapter.

## R2. Monthly cost (us-east-1, on-demand, 1,000 stories/month)

### Option S Serverless: ~$12.60 low traffic, ~$2 idle

| Item | Rate | $/month | Source |
|---|---|---|---|
| Lambda arm64, ~243k GB-s (`story-graph` 1,000 x 120 s x 2 GB + `story-api` 20k x 0.3 s x 0.5 GB; R7) | $0.0000133334/GB-s; 400k GB-s + 1M req free monthly | 0 (3.24 w/o free tier; was 3.36 as one 2 GB function) | [cloudburn](https://cloudburn.io/blog/aws-lambda-pricing), [wiz](https://www.wiz.io/academy/cloud-cost/aws-lambda-cost-breakdown) |
| Aurora Serverless v2 compute, ~90 ACU-h awake (assumption) | $0.12/ACU-h | 10.80 | [AWS Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/) |
| Aurora storage 2 GB + ~1M I/O | $0.10/GB-month, $0.20/M I/O | 0.40 | same |
| Data API ~60k requests | $0.35 per million (<= 32 KB) | 0.02 | same |
| CloudFront + S3 SPA | free tier | ~0.10 | unverified |
| API Gateway REST, ~20k requests (a stream is billed per 10 MB, so 1 story = 1 request) | $3.50 per million | 0.07 | [AWS](https://aws.amazon.com/api-gateway/pricing/) |
| Route 53 public hosted zone (alias queries free) | $0.50/zone-month | 0.50 | [AWS](https://aws.amazon.com/route53/pricing/) |
| ECR ~1 GB, CloudWatch logs + 4 alarms | - | ~1.00 | unverified |
| SSM Parameter Store standard, ACM, Cloudflare NS records | free | 0 | - |
| Secrets Manager: the RDS-managed master secret the Data API needs (found while building #15) | $0.40/secret-month | 0.40 | [AWS](https://aws.amazon.com/secrets-manager/pricing/) |
| Langfuse | not in AWS (D5: local only, tracing off in prod) | 0 | 2026-10-16 decision |
| **Idle floor** (paused DB, no traffic) | | **~2.40** (was ~2.00 before the secret line) | |
| **If minimum 0.5 ACU** (never pauses) | 0.5 x 730 h x $0.12 = $43.80 | **~45** | |

Scale to 0 ACU: Aurora PostgreSQL 13.15+, 14.12+, 15.7+, 16.3+
([AWS, Nov 2024](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-aurora-serverless-v2-scaling-zero-capacity)).
Auto-pause after 300 s to 86,400 s idle; the Data API resumes a paused writer and returns
`DatabaseResumingException` meanwhile ([AWS docs](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html),
[botocore](https://docs.aws.amazon.com/botocore/latest/reference/services/rds-data/client/exceptions/DatabaseResumingException.html)).
Resume ~15 s, longer after 24 h idle (third-party). RDS Proxy keeps the cluster from pausing.

Per-story compute beyond the free tier: 2 GB x 120 s x $0.0000133334 = ~$0.0032 (vs ~$0.0073 LLM).

The ~$12.60 low-traffic total predates the secret line; with it the total is ~$13, still under SC-002's $20.

### LLM tokens

~$0.0073/story, ~$7.27 per 1,000 stories at Anthropic list prices (Haiku 5.5 router + writer, Sonnet 5.5
editor; lower with the Haiku editor, #13), vault `Model-Cost-Analysis.md`. Production uses Amazon Bedrock
(D4 revised); Bedrock on-demand prices for these models are assumed equal to Anthropic list prices
(unverified, check before go-live), so SC-003 holds if that is true.

## R3. Where Story Engine differs from Doctor-Assist (Option S design answers)

Doctor-Assist is event-driven batch (S3 -> EventBridge -> Transcribe -> Lambda) and the client polls
through API Gateway HTTP API + Mangum. Story Engine streams one long request per story.

| # | Topic | Finding | Plan |
|---|---|---|---|
| 1 | Long LangGraph runs vs 15-min Lambda limit | Story ~1-2 min (unmeasured). Worst case 3 sequential stages x 60 s `LLM_TIMEOUT_SECONDS` x 3 attempts = 540 s < 900 s. A Lambda timeout skips `finally`; a `running` row then counts as in-flight in `enforce_quota`. | Lambda timeout 900 s; app deadline 600 s marks the story failed; quota ignores `running` rows older than 15 min. No Step Functions. |
| 2 | SSE streaming | HTTP API buffers, 30 s cap. Python has no native Lambda streaming; Lambda Web Adapter + function URL `RESPONSE_STREAM` streams FastAPI ([example](https://github.com/awslabs/aws-lambda-web-adapter/blob/main/examples/fastapi-response-streaming-zip)). CloudFront origin response timeout default 30 s applies to each packet ([re:Post](https://www.repost.aws/knowledge-center/cloudfront-custom-origin-response)). `stories.py` sends no heartbeat today. | **Decided 2026-10-16:** API Gateway REST API, response transfer mode `STREAM` ([Nov 2025](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis), [docs](https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode.html)); `: ping` every 15 s. (v2 had CloudFront `/api/*` -> function URL.) |
| 3 | SSLCommerz IPN | OAC on a function URL requires `x-amz-content-sha256` on POST/PUT ([AWS](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-lambda.html)); SSLCommerz and the browser `POST /generate` do not send it. IPN already checks the MD5 signature and calls the validation API (`sslcommerz.py:153`). | Solved by the 2026-10-16 edge: the IPN posts to the API Gateway custom domain, no OAC and no `X-Origin-Verify` header needed. Outbound validation call works (no VPC). |
| 4 | Langfuse hosting | Self-host needs ClickHouse 8 GiB always on (+~$105 EC2). Lambda freezes after the response, so batched traces are lost unless flushed. | **D5 decided 2026-10-16:** Langfuse runs only locally for debugging; production on AWS runs with tracing off (no `LANGFUSE_*` keys in SSM). The `flush()` in the stream's `finally` stays harmless for local runs. |
| 5 | Semantic cache + pgvector | Aurora PG supports pgvector. Data API has no vector/UUID types; `semantic.py:71` uses `cosine_distance`. | Keep `vector(384)` / migration 0003; shim casts `::vector`, `::uuid`; `CREATE EXTENSION vector` first. |
| 6 | Rate limit + quota without Redis | Quota is already Postgres (`limits.py` `SELECT ... FOR UPDATE`). Redis holds only the 60 s window (fails open) and the optional checkpointer (`graph.py:85` falls back to stateless). | `rate_limit_window` table, upsert in the quota transaction; `CHECKPOINTER=none`; reserved concurrency; WAF rate rule optional (~$6+). |
| 7 | Cold starts with MiniLM | torch => ~2 GB image, slow import. Doctor-Assist: HF download crashed on read-only FS; 1024 MB starved first inference (moved to 2048 MB). | ONNX MiniLM (fastembed) baked in, lazy-loaded only when `SEMANTIC_CACHE_ENABLED`; 2048 MB; measure p95. SnapStart for container images reported Sept 2026 ([InfoQ](https://www.infoq.com/news/2026/09/lambda-snapstart-container-image/)), unverified. |
| 8 | DB access path | SQLAlchemy async + asyncpg, ~47 query sites; no async Data API dialect is known to be maintained (unverified). | D7: async Data API adapter (3 pd) or Lambda in VPC + asyncpg `NullPool` + NAT instance (~1 pd, ~$7/month). |

### Doctor-Assist live bugs reused as checklist items

1. IAM needs `rds-data:BeginTransaction/CommitTransaction/RollbackTransaction`, not only `ExecuteStatement`.
2. Data API typing: UUID hints needed; an over-eager hint broke `hashtext(uuid)`. Test against real Aurora.
3. Read-only file system: bake models into the image.
4. 1024 MB too small for first CPU inference; use 2048 MB.
5. In-process state does not cross Lambda instances (ADR-023).
6. Bedrock: Anthropic models needed a use-case form (ADR-024); inference-profile ARNs need the account id.
7. Log caught LLM errors with detail (T060).

## R4. Effort (person-days)

| Phase | Option S |
|---|---|
| P0 Prod readiness | 1.5 |
| IaC base | 1.0 |
| Data services + data move | 1.0 |
| Data access adapter | 3.0 |
| Compute packaging (incl. api/graph split, R7) | 2.0 |
| Edge / frontend | 1.0 |
| CI/CD | 1.0 |
| Monitoring, tests, cutover, runbook | 1.5 |
| **Total planned** | **12 (~14.5 with 20%)** |
| Bedrock adapter (T044, added with D4 revised) | 1.5-2 |

Option S with D7 = VPC + NAT instance: ~10 (~12). Remaining effort after the draft PRs: plan.md
"Implementation sequence".

## R5. Decisions (answered 2026-10-16, T001)

All nine are answered. The human picked D1, D2, D4 and D5 explicitly and D3 earlier; D6-D9 take the
recommended default below.

| Id | Answer | Source |
|---|---|---|
| D1 | **Option S Serverless** | human, 2026-10-16 |
| D2 | **us-east-1** | human, 2026-10-16 |
| D3 | **Route 53 sub-zone** `storyteller.techvigilant.com` NS-delegated from Cloudflare; edge = API Gateway REST streaming, no nginx | human, 2026-10-16 |
| D4 | **Amazon Bedrock in production**; Anthropic API for local dev (revised 2026-10-16; first answer was Anthropic API) | human, 2026-10-16 |
| D5 | **Langfuse local only**, for debugging; production runs with tracing off; no Langfuse in AWS | human, 2026-10-16 |
| D6 | SAM | recommended default |
| D7 | Data API adapter (no VPC Lambda, no NAT) | recommended default |
| D8 | Aurora minimum 0 ACU, auto-pause 300 s | recommended default |
| D9 | ONNX MiniLM baked into the image | recommended default |

Infrastructure for these answers: branch `aws-infra` (`infra/template.yaml`, `.github/workflows/deploy.yml`,
`docs/runbook-aws.md`).

### Options as presented (kept for the record)

| Id | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Option | S / two alternatives (R1, rejected) | S |
| D2 | Region | us-east-1 / ap-south-1 | us-east-1 (Doctor-Assist verified); ap-south-1 only after checking Data API + 0 ACU there |
| D3 | DNS | Cloudflare CNAME / Route 53 sub-zone | **Resolved 2026-10-16 (human): Route 53 sub-zone NS-delegated from Cloudflare, as Doctor-Assist; no Tunnel or Cloudflare proxy; +$0.50/month.** Edge: API Gateway REST streaming, no nginx (+~$0.07/month) |
| D4 | LLM provider | Anthropic API / Bedrock | Anthropic API first; revised to Bedrock for production |
| D5 | Langfuse | Cloud Hobby / home self-host via Tunnel / AWS self-host | Home self-host via Tunnel (complies with IV, $0) or Cloud Hobby with amendment |
| D6 | IaC | SAM / CDK / Terraform | SAM (Doctor-Assist precedent) |
| D7 | DB path | Data API adapter / Lambda in VPC + NAT instance | Data API adapter |
| D8 | Aurora minimum | 0 ACU / 0.5 ACU | 0 ACU (accept ~15 s first request after idle) |
| D9 | Embeddings | ONNX in image / torch / cache off | ONNX in image |

## R6. Verification status

Verified this session (AWS pages or AWS docs): Aurora serverless ACU-hour, storage, I/O and Data API
prices (us-east-1); 0 ACU support and versions; auto-pause range and Data API resume behaviour;
API Gateway REST streaming (Nov 2025) and its limits (15 min, 5 min idle Regional, Lambda proxy only)
and pricing (per 10 MB); HTTP API 30 s integration timeout; ALB Lambda 1 MB response; Route 53 zone
and alias-query pricing; CloudFront OAC POST requirement; Lambda Web Adapter streaming example.
**Unverified, spike in P4**: Lambda Web Adapter `response_stream` output behind an API Gateway REST
integration (no source shows the combination). Third-party only: Lambda arm64 rate and free tier, CloudFront per-packet timeout wording,
resume time ~15 s. **Unverified**: CloudFront/S3 free tier, ECR and CloudWatch rates, NAT instance
cost, function URL streaming size/bandwidth limits, SnapStart for container images, Data API and
0 ACU in ap-south-1, Bedrock prices per region, real story duration on prod models.

## R7. ADR split-api-graph: two Lambdas split by route (decided 2026-10-16)

**Status**: accepted (human request, accepted by god 2026-10-16). Applies to Option S only.

**Context**: v2 ran the whole FastAPI app as one 2048 MB / 900 s Lambda. Every login or list call
then paid the LangGraph + ONNX cold start and the 2 GB price, and a burst of generations shared one
concurrency pool with login and CRUD.

**Decision**: two functions, chosen by route at API Gateway; no Lambda calls another.

| Function | Routes | API Gateway integration | Memory / timeout | Concurrency | Image target |
|---|---|---|---|---|---|
| `story-api` | `ANY /{proxy+}`: auth, stories CRUD/list/export, personalities, payments + SSLCommerz IPN, LLM config, `/health` | BUFFERED | 512 MB / 30 s | account pool | `api`: no LangGraph, LLM SDKs or ONNX model (absent or lazy imports) |
| `story-graph` | `POST /api/v1/stories/generate` (SSE) | STREAM | 2048 MB / 900 s, app deadline 600 s | reserved, e.g. 20 | `graph`: minimal FastAPI app with only the generate route; LangGraph + semantic cache (ONNX MiniLM) |
| `migrate` | none (deploy hook) | - | unchanged | 1 | `migrate` |

API Gateway REST: resource `/api/v1/stories/generate` `POST` -> `story-graph` (STREAM, more
specific path wins); `ANY /{proxy+}` -> `story-api` (BUFFERED). JWT check, story ownership and
quota run inside `story-graph` too, from the shared code package, so the generate route is not
less protected than the rest.

**Why**: each side gets its own memory, timeout, concurrency cap and image; CRUD cold starts no
longer load LangGraph/ONNX; a burst of generations cannot starve login/CRUD (reserved concurrency
also caps LLM spend and Aurora load); failures are isolated.

**Alternatives rejected**:

| Alternative | Why rejected |
|---|---|
| (a) `story-api` invokes `story-graph` (`InvokeWithResponseStream`) | Both Lambdas run for the whole story: double compute bill, extra hop and extra failure point |
| (b) Async jobs via SQS or Step Functions | Breaks token streaming (the client would poll); more moving parts. Revisit only if background generation that survives a closed browser is wanted |
| (c) Keep one function | Simplest, but 2048 MB / 900 s for every CRUD call, slow CRUD cold starts, shared concurrency |

**Cost**: about neutral to slightly lower (CRUD at 512 MB instead of 2048 MB: ~243k instead of
~252k GB-s/month, inside the free tier either way); one more function, still $0 idle compute.
**Effort**: +0.5 person-day (P4 Compute packaging 1.5 -> 2.0; T019/T020 split into T019a/b, T020a/b).

## R8. Analysis pass (`/speckit-analyze`, 2026-10-16, v3)

Cross-check of spec.md, plan.md, tasks.md and the constitution against the code in #15 and #17.
All findings below were fixed in v3 of the three files.

| ID | Category | Severity | Finding | Fix |
|---|---|---|---|---|
| C1 | Constitution | CRITICAL | IV "every generation MUST produce a Langfuse trace" conflicts with D5 (production tracing off); FR-010, US4 and T038 still required a trace in production | FR-010 follows D5; T005 now drafts the IV amendment and gates cutover (plan Gate C); Constitution Check marks IV AMEND |
| C2 | Constitution | HIGH | Workflow "CD = `make deploy`" vs the GitHub Actions deploy job | Kept in T005; plan marks AMEND |
| I1 | Inconsistency | HIGH | US2 said "deploy on green `master`"; `deploy.yml` is `workflow_dispatch` only, automatic deploys off until the human approves | US2 rewritten; T030 states it |
| I2 | Inconsistency | HIGH | SC-001 required every local Playwright test to pass on AWS; `langfuse.spec.ts` (D5) and the `/llm/ping` tests cannot (route not served on AWS) | SC-001 lists the expected suites and the exclusions |
| I3 | Inconsistency | MEDIUM | FR-003 allowed `bedrock`; no Bedrock adapter exists and the stack Rule rejects it without `UseBedrock` | FR-003: provider switchable, `bedrock` rejected until T044 |
| I4 | Inconsistency | MEDIUM | Plan summary said 11.5 pd, phase table 12 | Plan uses 12 planned, ~7.5 remaining |
| I5 | Terminology | MEDIUM | `app/main_graph.py` (plan, tasks) vs `app/graph_main.py` (built); `stories.py` vs `generate.py` for the SSE code | Names follow the code |
| I6 | Inconsistency | MEDIUM | Idle cost ~$2 omitted the $0.40 RDS master secret (runbook says ~$2.40) | R2 row added; SC-002 ~$2.40 |
| I7 | Inconsistency | LOW | FR-017 / T020a said `ANY /{proxy+}` only; built template maps `/`, `/api`, `/api/v1`, `/api/v1/stories` explicitly (parents of the generate resource) | Plan functions table and T020a list them |
| I8 | Inconsistency | LOW | Spec status "planning only", assumption "the human picks one option" | Status and assumptions updated |
| G1 | Coverage | HIGH | FR-009 `/health` failure alarm: template has Errors, Throttles, Duration, 5xx, Aurora alarms but no `/health` check | T036 partial, open part AGENT |
| G2 | Coverage | MEDIUM | T014 real-Aurora suite: only stubbed tests exist | Split T014a (AGENT, write) / T014b (FIRST-DEPLOY, run) |
| G3 | Coverage | MEDIUM | Edge case "concurrency cap -> clear 429/503" untested; status code from a throttled STREAM integration unknown | Edge case reworded; check in T039 |
| G4 | Coverage | MEDIUM | FR-006 migrations vs alias rollback: schema is not rolled back | FR-006 requires backward-compatible (expand/contract) migrations |
| G5 | Coverage | MEDIUM | No task for a Bedrock adapter although production has no funded key | T044 (AGENT, 1.5-2 d, not started) |
| G6 | Coverage | LOW | No task for PR integration order | T045 + plan "Implementation sequence" |
| U1 | Underspecified | LOW | FR-002 "at least 300 s" vs the 600 s deadline | FR-002 says 600 s on the generate path |

Metrics after the fixes: 17 FR + 7 SC; every FR and buildable SC maps to at least one task; 42 tasks
(8 done in draft, 16 partial, 18 open); 0 CRITICAL left open in the documents (C1 remains a gate
until T005 merges).
