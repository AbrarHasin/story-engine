# Research: Run Story Engine on AWS

**Spec**: [spec.md](./spec.md) | **Date**: 2026-10-16 (v2, serverless first)
**Method**: v1 read `docker-compose*.yml`, `nginx/prod.conf`, Dockerfiles, `config.py`, `requirements.txt`,
CI, Makefile. v2 also read `core/limits.py`, `core/database.py`, `api/v1/stories.py`, `payment/sslcommerz.py`,
`agents/graph.py`, `cache/semantic.py`, and the Doctor-Assist cloud note (spec 008, live since 2026-07-29).
Prices by web search on 2026-10-16. No AWS account, CLI or API key was used.

## R1. Options considered

| Option | Shape | Verdict |
|---|---|---|
| S Serverless | Lambda (container, Web Adapter, streaming function URL) + CloudFront/S3 + Aurora Serverless v2 via Data API + SSM + ECR, GitHub OIDC, SAM | **Recommended** |
| 1 Lean | One Lightsail 8 GB host, existing compose stack, Cloudflare Tunnel | Baseline: fastest go-live |
| 2 Managed | ECS Fargate + RDS + ElastiCache + ALB + S3/CloudFront + Secrets Manager | Not pursued: dearest and slowest at this traffic |
| API Gateway HTTP API + Mangum (Doctor-Assist's API edge) | Buffered, 30 s integration limit | Rejected for Story Engine: no SSE |
| API Gateway REST API with response streaming | Up to 15 min, Nov 2025 | Alternative edge if usage plans / WAF on the API are wanted |
| App Runner, EKS | - | Rejected (v1) |

**Decision**: recommend Option S. **Rationale**: ~$12/month at 1,000 stories and ~$1.50 idle vs $50
flat (Lean) and ~$104 (Managed); no host to patch; reuses a design already debugged live in
Doctor-Assist. **Cost of it**: ~5.5 person-days more than Lean, most of it in the Data API adapter.

## R2. Monthly cost (us-east-1, on-demand, 1,000 stories/month)

### Option S Serverless: ~$12 low traffic, ~$1.50 idle

| Item | Rate | $/month | Source |
|---|---|---|---|
| Lambda arm64, ~252k GB-s (1,000 x 120 s x 2 GB + 20k x 0.3 s x 2 GB) | $0.0000133334/GB-s; 400k GB-s + 1M req free monthly | 0 (3.36 w/o free tier) | [cloudburn](https://cloudburn.io/blog/aws-lambda-pricing), [wiz](https://www.wiz.io/academy/cloud-cost/aws-lambda-cost-breakdown) |
| Aurora Serverless v2 compute, ~90 ACU-h awake (assumption) | $0.12/ACU-h | 10.80 | [AWS Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/) |
| Aurora storage 2 GB + ~1M I/O | $0.10/GB-month, $0.20/M I/O | 0.40 | same |
| Data API ~60k requests | $0.35 per million (<= 32 KB) | 0.02 | same |
| CloudFront + S3 SPA | free tier | ~0.10 | unverified |
| ECR ~1 GB, CloudWatch logs + 4 alarms | - | ~1.00 | unverified |
| SSM Parameter Store standard, ACM, Cloudflare DNS | free | 0 | - |
| Langfuse (Cloud Hobby or home self-host) | free | 0 | v1 |
| **Idle floor** (paused DB, no traffic) | | **~1.50** | |
| **If minimum 0.5 ACU** (never pauses) | 0.5 x 730 h x $0.12 = $43.80 | **~45** | |

Scale to 0 ACU: Aurora PostgreSQL 13.15+, 14.12+, 15.7+, 16.3+
([AWS, Nov 2024](https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-aurora-serverless-v2-scaling-zero-capacity)).
Auto-pause after 300 s to 86,400 s idle; the Data API resumes a paused writer and returns
`DatabaseResumingException` meanwhile ([AWS docs](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html),
[botocore](https://docs.aws.amazon.com/botocore/latest/reference/services/rds-data/client/exceptions/DatabaseResumingException.html)).
Resume ~15 s, longer after 24 h idle (third-party). RDS Proxy keeps the cluster from pausing.

Per-story compute beyond the free tier: 2 GB x 120 s x $0.0000133334 = ~$0.0032 (vs ~$0.0073 LLM).

### Option 1 Lean: ~$50 (idle the same)

Lightsail 8 GB $44 ([AWS](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.md)),
snapshots ~$4, S3 + ECR ~$1, CloudWatch ~$1 (unverified). Self-hosted Langfuse needs a 16 GB host (+~$40).

### Option 2 Managed: ~$104 minimal, ~$162 with HA (idle the same)

Fargate 1 vCPU/2 GB ARM $28.84, RDS `db.t4g.small` + 20 GB $25.66, ALB $22.27, ElastiCache
`t4g.micro` $9.34, public IPv4 x3 $10.95, Secrets Manager x8 $3.20, other ~$3.50. Sources as in v1:
[Vantage](https://www.vantage.sh/blog/fargate-pricing), [Bytebase](https://www.bytebase.com/dbcost/rds/instance/db.t4g.small/),
[cloudburn ALB](https://cloudburn.io/blog/aws-elastic-load-balancing-pricing),
[Upstash](https://upstash.com/blog/aws-elasticache-pricing-explained-2026-full-cost-breakdown),
[cloudburn VPC](https://cloudburn.io/blog/amazon-vpc-pricing).

### LLM tokens (all options)

~$0.0073/story, ~$7.27 per 1,000 stories (Haiku 5.5 router + writer, Sonnet 5.5 editor), vault
`Model-Cost-Analysis.md`. Unchanged by the hosting move.

## R3. Where Story Engine differs from Doctor-Assist (Option S design answers)

Doctor-Assist is event-driven batch (S3 -> EventBridge -> Transcribe -> Lambda) and the client polls
through API Gateway HTTP API + Mangum. Story Engine streams one long request per story.

| # | Topic | Finding | Plan |
|---|---|---|---|
| 1 | Long LangGraph runs vs 15-min Lambda limit | Story ~1-2 min (unmeasured). Worst case 3 sequential stages x 60 s `LLM_TIMEOUT_SECONDS` x 3 attempts = 540 s < 900 s. A Lambda timeout skips `finally`; a `running` row then counts as in-flight in `enforce_quota`. | Lambda timeout 900 s; app deadline 600 s marks the story failed; quota ignores `running` rows older than 15 min. No Step Functions. |
| 2 | SSE streaming | HTTP API buffers, 30 s cap. Python has no native Lambda streaming; Lambda Web Adapter + function URL `RESPONSE_STREAM` streams FastAPI ([example](https://github.com/awslabs/aws-lambda-web-adapter/blob/main/examples/fastapi-response-streaming-zip)). CloudFront origin response timeout default 30 s applies to each packet ([re:Post](https://www.repost.aws/knowledge-center/cloudfront-custom-origin-response)). `stories.py` sends no heartbeat today. | CloudFront `/api/*` -> function URL; `: ping` every 15 s. Alternative: REST API streaming ([Nov 2025](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis)). |
| 3 | SSLCommerz IPN | OAC on a function URL requires `x-amz-content-sha256` on POST/PUT ([AWS](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-lambda.html)); SSLCommerz and the browser `POST /generate` do not send it. IPN already checks the MD5 signature and calls the validation API (`sslcommerz.py:153`). | Function URL auth NONE + secret `X-Origin-Verify` header added by CloudFront, checked by middleware. Outbound validation call works (no VPC). |
| 4 | Langfuse hosting | Self-host needs ClickHouse 8 GiB always on (+~$105 EC2). Lambda freezes after the response, so batched traces are lost unless flushed. | D5: Cloud Hobby (amend IV) or home self-host via Tunnel. `flush()` in the stream's `finally`. |
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

| Phase | Option S | Option 1 |
|---|---|---|
| P0 Prod readiness (shared) | 1.5 | 1.5 |
| IaC / host base | 1.0 | 0.5 |
| Data services + data move | 1.0 | 1.0 (compose) + 1.0 (data, backups) |
| Data access adapter | 3.0 | - |
| Compute packaging | 1.5 | - |
| Edge / frontend | 1.0 | - |
| CI/CD | 1.0 | 1.0 |
| Monitoring, tests, cutover, runbook | 1.5 | 1.0 |
| **Total** | **11.5 (~14 with 20%)** | **6 (~7)** |

Option 2 Managed: 13 (~16). Option S with D7 = VPC + NAT instance: ~9.5 (~11.5).

## R5. Open decisions for the human

| Id | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Option | S / Lean / Managed | S; Lean if go-live speed beats ~$38/month |
| D2 | Region | us-east-1 / ap-south-1 | us-east-1 (Doctor-Assist verified); ap-south-1 only after checking Data API + 0 ACU there |
| D3 | DNS | Cloudflare CNAME / Route 53 sub-zone | Cloudflare CNAME ($0) |
| D4 | LLM provider | Anthropic API / Bedrock | Anthropic API now |
| D5 | Langfuse | Cloud Hobby / home self-host via Tunnel / AWS self-host | Home self-host via Tunnel (complies with IV, $0) or Cloud Hobby with amendment |
| D6 | IaC | SAM / CDK / Terraform | SAM (Doctor-Assist precedent) |
| D7 | DB path | Data API adapter / Lambda in VPC + NAT instance | Data API adapter |
| D8 | Aurora minimum | 0 ACU / 0.5 ACU | 0 ACU (accept ~15 s first request after idle) |
| D9 | Embeddings | ONNX in image / torch / cache off | ONNX in image |

## R6. Verification status

Verified this session (AWS pages or AWS docs): Aurora serverless ACU-hour, storage, I/O and Data API
prices (us-east-1); 0 ACU support and versions; auto-pause range and Data API resume behaviour;
API Gateway REST streaming (Nov 2025); CloudFront OAC POST requirement; Lambda Web Adapter streaming
example. Third-party only: Lambda arm64 rate and free tier, CloudFront per-packet timeout wording,
resume time ~15 s. **Unverified**: CloudFront/S3 free tier, ECR and CloudWatch rates, NAT instance
cost, function URL streaming size/bandwidth limits, SnapStart for container images, Data API and
0 ACU in ap-south-1, Bedrock prices per region, real story duration on prod models.
