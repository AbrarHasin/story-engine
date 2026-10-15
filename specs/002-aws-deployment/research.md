# Research: Run Story Engine on AWS

**Spec**: [spec.md](./spec.md) | **Date**: 2026-10-16
**Method**: read `docker-compose*.yml`, `nginx/prod.conf`, `backend/Dockerfile`, `frontend/Dockerfile`,
`backend/app/core/config.py`, `backend/requirements.txt`, `.github/workflows/ci.yml`, `Makefile`,
specs/001, and vault notes `Decisions-vs-Code.md` and `Model-Cost-Analysis.md`. Prices by web search
on 2026-10-16. No AWS account, CLI or API key was used.

## R1. Options considered

| Option | Shape | Verdict |
|---|---|---|
| 1 Lean | One Lightsail 8 GB host, existing compose stack, Cloudflare Tunnel | **Recommended** for low traffic |
| 2 Managed | ECS Fargate + RDS + ElastiCache + ALB + S3/CloudFront + Secrets Manager + ECR + CloudWatch, GitHub OIDC | Move here when traffic or uptime needs grow |
| EKS | Kubernetes | Rejected: control plane cost and effort far above need |
| App Runner | Managed containers | Rejected: no long-lived SSE guarantee checked, less control of timeouts; not evaluated further |

**Decision**: recommend Option 1. **Rationale**: about half the monthly cost (~$50 vs ~$104-162) and
half the effort (6 vs 13 person-days), and it reuses the compose stack that already runs.
**Alternative kept open**: Option 2 reuses the same images, so the move is a re-platform, not a rewrite.

## R2. Monthly cost (us-east-1, on-demand, low traffic)

### Option 1 Lean: ~$50

| Item | $/month | Source |
|---|---|---|
| Lightsail 8 GB, 2 vCPU, 160 GB, 5 TB transfer, IPv4 included | 44.00 | [AWS Lightsail bundles](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.md) |
| Snapshots ~80 GB | ~4 | unverified |
| S3 backups + ECR | ~1 | unverified |
| CloudWatch alarm + logs | ~1 | unverified |
| Cloudflare DNS + Tunnel | 0 | free plan |
| Langfuse Cloud Hobby | 0 | [50k units/month](https://www.zenml.io/blog/langfuse-pricing) |

Self-hosted Langfuse needs a 16 GB host (+~$40, Lightsail 16 GB price unverified):
[ClickHouse wants 8 GiB](https://langfuse.com/self-hosting/scaling).
EC2 alternative `t4g.large`: $0.0672/h us-east-1, $0.0448/h ap-south-1 ([source](https://aws-pricing.com/t4g.large.html)).

### Option 2 Managed: ~$104 minimal, ~$162 with HA

| Item | Rate | $/month | Source |
|---|---|---|---|
| Fargate 1 vCPU / 2 GB ARM, 730 h | $0.03238 vCPU-h, $0.00356 GB-h | 28.84 | [Vantage](https://www.vantage.sh/blog/fargate-pricing) |
| RDS `db.t4g.small` single-AZ + 20 GB gp3 | $0.032/h; gp3 ~$0.115/GB (unverified) | 25.66 | [Bytebase](https://www.bytebase.com/dbcost/rds/instance/db.t4g.small/) |
| ALB + ~1 LCU | $0.0225/h + $0.008/LCU-h | 22.27 | [cloudburn](https://cloudburn.io/blog/aws-elastic-load-balancing-pricing) |
| ElastiCache Valkey `cache.t4g.micro` | $0.0128/h | 9.34 | [Upstash](https://upstash.com/blog/aws-elasticache-pricing-explained-2026-full-cost-breakdown) |
| Public IPv4 x3 | $0.005/h | 10.95 | [cloudburn VPC](https://cloudburn.io/blog/amazon-vpc-pricing) |
| Secrets Manager x8 | $0.40 | 3.20 | [AWS](https://aws.amazon.com/secrets-manager/pricing/) |
| S3 + CloudFront, ECR, CloudWatch | - | ~3.50 | unverified |
| HA add-on: second task + Multi-AZ RDS | - | +58 | derived |

Not included: NAT gateway (avoided; ~$33/month + $0.045/GB,
[source](https://cloudburn.io/blog/aws-nat-gateway-pricing)), WAF (~$6+, unverified), self-hosted
Langfuse (+~$105 on one EC2 `t4g.xlarge`, +~$200 on Fargate).

### LLM tokens (both options)

~$0.0073/story, ~$7.27 per 1,000 stories (Haiku 5.5 router + writer, Sonnet 5.5 editor), from vault
`Model-Cost-Analysis.md`. Unchanged by the hosting move (constitution I: no token impact).

## R3. Technical findings that shape the plan

- **SSE timeouts**: nginx already sets 300 s and no buffering. ALB idle timeout must be raised from
  its 60 s default (from AWS docs, not re-verified). CloudFront origin read timeout is 1-120 s,
  default 30 s ([AWS SDK ref](https://docs.aws.amazon.com/sdk-for-kotlin/api/latest/cloudfront/aws.sdk.kotlin.services.cloudfront.model/-custom-origin-config/origin-read-timeout.html)),
  so in Option 2 the API host goes straight to the ALB, not through CloudFront. Cloudflare's proxy
  read timeout (100 s on the free plan, not re-verified) is satisfied because events flow every node.
- **Image size**: `sentence-transformers` pulls torch; the backend image is ~2 GB and wants ~1 GB RAM.
  Bake the MiniLM model into the image; size Fargate at 1 vCPU / 2 GB.
- **Redis**: `langgraph-checkpoint-redis` needs Redis modules (JSON, search) and already falls back
  to stateless on plain `redis:7-alpine` (`graph.py:85`). Rate limits (`core/limits.py`) need plain
  Redis only and fail open. ElastiCache Valkey is enough; no change in behaviour.
- **pgvector on RDS**: supported extension; run `CREATE EXTENSION vector` before migration 0003.
- **Local LLM**: Docker Model Runner (`models:` block) does not apply on AWS without a GPU; prod uses
  `LLM_PROVIDER=anthropic`.
- **Secrets drift**: base and prod compose still carry dev Langfuse keys and default passwords;
  HAG-17 (`prod-config-safety`) moves them to `${VAR:?}` and adds `prod_guard`. P0 depends on it.
- **Langfuse**: constitution IV requires self-hosted v3. Langfuse Cloud Hobby would need an amendment.

## R4. Effort (person-days)

| Phase | Option 1 | Option 2 |
|---|---|---|
| P0 Prod readiness (shared) | 1.5 | 1.5 |
| Host / IaC base | 0.5 | 2.0 |
| Compose or data services | 1.0 | 1.5 |
| Data move + backups | 1.0 | (in data services) |
| Compute (ECS, ALB, migrate task) | - | 2.5 |
| Frontend (S3 + CloudFront) | - | 1.0 |
| CI/CD | 1.0 | 1.5 |
| Code + config changes | (in compose) | 1.0 |
| Monitoring, cutover, runbook | 1.0 | 2.0 |
| **Total** | **6 (7 with 20%)** | **13 (~16 with 20%)** |

## R5. Open decisions for the human

| Id | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Option | Lean / Managed | Lean |
| D2 | Region | ap-south-1 Mumbai / us-east-1 | Mumbai if users are in Bangladesh; confirm Bedrock models there if D4 = Bedrock |
| D3 | DNS | Cloudflare / Route 53 | Keep Cloudflare (free, Tunnel already set up) |
| D4 | LLM provider | Anthropic API / Amazon Bedrock | Anthropic API now; Bedrock needs a `BedrockAdapter` (~1 day) and unverified prices |
| D5 | Langfuse | self-host / Cloud Hobby | Self-host per constitution IV, unless the human amends it |
| D6 | IaC | Terraform / AWS CDK | Terraform (Option 1 needs little IaC either way) |
| D7 | HA on day one | yes / later | Later |

## R6. Verification status

Verified by source this session: Lightsail 4/8 GB bundle prices, Fargate ARM rates, RDS t4g
micro/small rates, ElastiCache Valkey t4g.micro, ALB hourly and LCU, public IPv4, NAT gateway,
Secrets Manager, EC2 t4g.large (us-east-1, ap-south-1), Langfuse self-host sizing and Hobby plan,
CloudFront origin read timeout. Most are third-party trackers quoting the AWS price list.
**Unverified**: gp3 storage rate, Lightsail 16 GB and snapshot rates, S3/ECR/CloudWatch rates,
ALB idle-timeout default/maximum, Cloudflare free-plan timeout, Route 53 zone price, WAF price,
Bedrock prices and per-region model availability.
