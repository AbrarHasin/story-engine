# Feature Specification: Run Story Engine on AWS (Option S Serverless)

**Feature Branch**: `aws-deployment-plan` (spec id `002-aws-deployment`)
**Created**: 2026-10-16 | **Revised**: 2026-10-16 (v2 serverless first; v2.1 DNS + edge; v2.2 ADR split-api-graph; v3 Option S only, implementation plan)
**Status**: Approved design (D1 = Option S, human, 2026-10-16). **AWS go-live deferred, not scheduled; current mode = local deployment (docker compose).** Code in draft PRs #17 (`aws-app`) and #15 (`aws-infra`); see tasks.md for status
**Input**: "Produce a deployment architecture and a Spec Kit plan for running Story Engine on AWS, so the human can judge effort BEFORE any build work." Revision input: "Follow the Doctor-Assist serverless, cost-optimised design (vault `Projects/Doctor-Assistant/Cloud-Architecture.md`, its spec 008) as the primary candidate." v3 input: "Option S confirmed; turn the spec into the executable plan for Option S only, reflecting what is already built."

> Narrative record: vault note `Projects/Story-Engine/AWS-Deployment-Architecture.md` with the
> one-page diagram `Diagrams/AWS-Cloud-Architecture.excalidraw`. Research, prices and the
> analysis record: [research.md](./research.md).
> **Decided 2026-10-16 (human), research.md R5:** D1 Option S Serverless; D2 us-east-1; D3 Route 53
> public hosted zone `storyteller.techvigilant.com` NS-delegated from Cloudflare's `techvigilant.com`,
> ACM DNS-validated there, no Cloudflare Tunnel or proxy on the request path, edge = API Gateway REST
> API with response transfer mode `STREAM` on `api.storyteller.techvigilant.com`, CloudFront + S3
> serve only the SPA; D4 Amazon Bedrock in production, Anthropic API for local dev (revised 2026-10-16);
> D5 Langfuse local only (production tracing off). Go-live deferred, not scheduled.
> The two alternatives to Option S were rejected (one line in research.md R1).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Readers use Story Engine served from AWS (Priority: P1)

A story author opens `storyteller.techvigilant.com`, signs in, generates a story and watches it
stream in, exactly as today, but every request is served from AWS instead of the home server.

**Why this priority**: it is the whole point of the move; nothing else matters if this fails.

**Independent Test**: on the staging names (runbook step 5, pinned DNS) and after cutover, run the
Playwright suites listed in SC-001 against the public URL and check `GET /health` returns `ok`;
the SSE stream delivers `start`, `node_complete` events and `done` for a story that streams longer
than 150 seconds (T028).

**Acceptance Scenarios**:

1. **Given** the AWS stack is live, **When** a signed-in user generates a story, **Then** the SSE
   events arrive in order, one by one (not buffered to the end), and the story row reaches
   `completed` in Aurora.
2. **Given** a node that sends no event for 60 seconds, **When** it runs, **Then** `: ping`
   comments every 15 s keep the stream open and API Gateway (5 min idle limit) does not close it.
3. **Given** an SSLCommerz payment, **When** the gateway posts its IPN, **Then** it reaches
   `story-api` at `BACKEND_PUBLIC_URL`, passes the signature check and server-side validation.
4. **Given** Aurora has been idle and paused, **When** the next user generates a story, **Then**
   the request succeeds after the resume delay (<= 45 s retry) instead of failing.
5. **Given** a burst of generations that hits `story-graph`'s reserved concurrency, **When** a user
   signs in or lists stories, **Then** `story-api` still answers.

### User Story 2 - Operator deploys and rolls back safely (Priority: P1)

The operator starts the deploy workflow on `master`; it builds the three images, runs migrations
and deploys to AWS without AWS keys stored in GitHub, then smoke-tests `/health`. A bad release
is rolled back in minutes.

**Independent Test**: deploy a release, then roll back to the previous one; both pass `/health`.

**Acceptance Scenarios**:

1. **Given** a green CI run on the commit, **When** the operator dispatches the deploy workflow
   and approves the `production` environment, **Then** it authenticates through GitHub OIDC,
   CodeDeploy runs `alembic upgrade head` (migrate Lambda, PreTraffic hook) before each alias
   shifts, and the job fails if `/health` is not `ok`. Automatic deploys on green `master` stay
   off until the human approves them.
2. **Given** a failed health check or an errors alarm, **When** the operator rolls back (the
   `live` alias of `story-api`, `story-graph` or both to an earlier version), **Then** service is
   restored within 10 minutes.

### User Story 3 - Data is backed up and restorable (Priority: P2)

**Independent Test**: Aurora point-in-time restore of last night into a scratch cluster, then
count `stories` rows (T035).

### User Story 4 - Operator sees failures and cost (Priority: P3)

**Independent Test**: break the backend; an alarm notifies the operator within 5 minutes. A
budget alarm fires before the monthly estimate is exceeded. Production has no Langfuse (D5); a
local run of the same commit still produces a trace.

### Edge Cases

- Function timeout mid-stream: the story row ends `failed`, never stuck in `running`, and a
  stuck row does not block the user's quota. The app's own deadline (600 s) fires before the
  Lambda timeout (900 s); quota ignores `running` rows older than 15 minutes.
- Aurora paused: the Data API returns `DatabaseResumingException`; the app retries with backoff
  for up to 45 s (`story-api` 20 s, under API Gateway's 29 s buffered limit).
- Concurrency cap reached on `story-graph`: the user gets an error response, not a hung request;
  login and CRUD on `story-api` keep working. The exact status code API Gateway returns for a
  throttled streaming integration is checked on the first deploy (T039).
- LLM provider unreachable or not permitted (Bedrock model access missing, throttled): `/health` stays
  up; generation returns `error`. Production cannot generate stories until the Bedrock adapter (T044)
  and Bedrock model access (T004) exist.
- Langfuse unreachable or off: generation still succeeds (constitution IV, degrade to no-op).
- SSLCommerz IPN retried: payment confirmation stays idempotent.
- A request to the default `execute-api` URL instead of the custom domain: rejected (endpoint disabled).
- A burst above the API Gateway stage throttle: 429 from API Gateway, Lambda never invoked.
- `POST /api/v1/llm/ping` (a real inference) is not served on AWS: `story-api` has no LLM SDK.

## Requirements *(mandatory)*

Requirements of the rejected alternatives were removed in v3 (research.md R1).

### Functional Requirements

- **FR-001**: The system MUST serve the SPA and the API from AWS under the existing public
  hostname: SPA at `storyteller.techvigilant.com` (CloudFront + S3), API at
  `api.storyteller.techvigilant.com` (API Gateway REST custom domain); both names live in a Route 53
  hosted zone NS-delegated from Cloudflare, with one ACM certificate DNS-validated in that zone.
  No nginx, no Cloudflare Tunnel and no Cloudflare proxy on the request path.
- **FR-002**: Every hop on the generate path MUST allow an SSE response of at least 600 seconds
  (the run deadline, FR-014). The API Gateway integration for generation MUST use response
  transfer mode `STREAM` on a Regional endpoint (15 min max, 5 min idle). The backend MUST send an
  SSE comment at least every 15 seconds while a node runs.
- **FR-003**: Production MUST fail closed at startup on default or missing secrets (`prod_guard`,
  HAG-17). The LLM provider MUST stay switchable by configuration only (`LLM_PROVIDER`, stack
  parameter `LlmProvider`, model parameters `Model*`), with no node edits (constitution III).
  Production runs `LLM_PROVIDER=bedrock` (D4 revised) with `UseBedrock=true`, which grants
  `story-graph` only `bedrock:InvokeModel` and `InvokeModelWithResponseStream`; no LLM API key is needed
  in production. Local development keeps `LLM_PROVIDER=anthropic`. `prod_guard` MUST accept `bedrock`
  without `ANTHROPIC_API_KEY` (part of T044).
- **FR-004**: Secrets MUST NOT be in git, images or Lambda environment variables: they are SSM
  Parameter Store SecureStrings, loaded at cold start before settings are validated; an
  environment variable of the same name wins (local dev only).
- **FR-005**: CI/CD MUST authenticate to AWS with GitHub OIDC and a least-privilege deploy role
  bound to the GitHub environment `production`.
- **FR-006**: Each deploy MUST run `alembic upgrade head` before traffic shifts (migrate Lambda as
  the CodeDeploy PreTraffic hook, reporting its status) and MUST smoke-test `/health`. Migrations
  MUST stay backward compatible with the previous release (expand, then contract), because the
  schema is not rolled back with the alias.
- **FR-007**: Postgres MUST keep the `vector` extension; migration 0003 (`vector(384)`) MUST apply
  cleanly on Aurora PostgreSQL 16.
- **FR-008**: Backups MUST be kept at least 7 days and a restore MUST be rehearsed before cutover.
- **FR-009**: An alarm MUST notify the operator by email within 5 minutes on sustained Lambda
  errors, API Gateway 5xx, or `/health` failure.
- **FR-010**: Tracing follows D5: production on AWS runs with tracing off (`TRACING_ENABLED=false`,
  no `LANGFUSE_*` parameters); local and staging runs keep a Langfuse trace per generation, and
  the trace client MUST be flushed before the response ends. This requires the constitution IV
  amendment (T005) before cutover.
- **FR-011**: The backend MUST use the real client IP (API Gateway request context / last
  `X-Forwarded-For` hop) for logs and limits.
- **FR-012**: The Lambda functions MUST be reachable only through the API Gateway custom domain
  (no function URL; default `execute-api` endpoint disabled); stage throttling MUST cap the
  request rate; the database MUST have no internet-reachable port.
- **FR-013**: The per-user rate limit and monthly quota MUST work without Redis (Postgres
  `rate_limit_window`); LangGraph runs stateless (`CHECKPOINTER=none`).
- **FR-014**: A run MUST end (completed or failed, row updated) within 600 s; the quota check MUST
  ignore `running` rows older than 15 minutes.
- **FR-015**: The embedding model MUST be in the `graph` image (read-only file system) and load
  only when `SEMANTIC_CACHE_ENABLED` is on.
- **FR-016**: Data API calls MUST retry `DatabaseResumingException`; the IAM role MUST allow
  `BeginTransaction`, `CommitTransaction`, `RollbackTransaction`, `ExecuteStatement`, `BatchExecuteStatement`.
- **FR-017**: (ADR `split-api-graph`, research.md R7) The API MUST run as two Lambda functions
  chosen by route at API Gateway, with no Lambda-to-Lambda call: `story-graph` serves only
  `POST /api/v1/stories/generate` (and its CORS preflight; STREAM integration, 2048 MB, 900 s
  timeout, 600 s app deadline, reserved concurrency) and `story-api` serves every other route
  (BUFFERED, 512 MB, 30 s). The `story-api` image MUST NOT load LangGraph, the LLM SDKs or the
  ONNX model. `story-graph` MUST enforce the same JWT check, story ownership and quota as
  `story-api`. Only `story-graph` may call the LLM (Bedrock IAM grant; SSM path `graph/` is optional
  and unused with Bedrock). Migrations stay in a
  separate `migrate` function with no SSM access.

### Key Entities

- **Environment**: region us-east-1, public hosts, SSM paths `/story-engine/<stage>/shared/` and
  `/story-engine/<stage>/graph/` (optional with Bedrock), image digests, Lambda aliases (`story-api`, `story-graph` `live`) and `migrate`.
- **Release**: image digests per target (git sha), Lambda versions, migration head, deploy time, health result.
- **Rate limit window**: user id, window start, count (replaces the Redis key; migration 0005).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The Playwright suites `api.spec.ts`, `frontend.spec.ts` and `auth.spec.ts` pass
  against the AWS deployment (LLM mocked or real). Not expected on AWS: `langfuse.spec.ts`
  (tracing off, D5) and the `/llm/ping` tests in `llm-adapter.spec.ts` (route not served).
- **SC-002**: Monthly AWS bill at under 1,000 stories/month, LLM tokens excluded: <= $20, and
  <= $5 in a month with no traffic (estimate ~$12.60 and ~$2.40, research.md R2). Budget alarm at $25.
- **SC-003**: LLM cost per story is unchanged by the move (~$0.0073/story at Anthropic list prices
  with the models on `master`; lower once #13 Haiku editor merges), assuming Bedrock on-demand prices
  equal Anthropic list prices (unverified).
- **SC-004**: A deploy from dispatch to healthy takes <= 15 minutes; a rollback <= 10 minutes.
- **SC-005**: A restore drill recovers data in <= 1 hour.
- **SC-006**: Zero secrets in git, images or CI logs (secret scan before cutover).
- **SC-007**: p95 time to the first SSE event <= 5 s with the database awake (cold start
  included) and <= 25 s right after a pause.

## Assumptions

- Traffic is low (under 1,000 stories/month, a handful of concurrent streams) for the first months.
- A story runs about 1-2 minutes end to end; not measured on the prod models yet (T006).
- Prod-readiness work (#12 `prod-config-safety`, #16 SPA login) and the Bedrock adapter (T044)
  land before cutover. No date is set: go-live is deferred.
- Cost impact on tokens (constitution I): none.
- As of 2026-10-16 no AWS account, CLI or deploy has been touched; all AWS behaviour in the
  draft PRs is verified by cfn-lint, `sam validate`, stubbed tests and local amd64 image builds only.
