# Feature Specification: Run Story Engine on AWS

**Feature Branch**: `aws-deployment-plan` (spec id `002-aws-deployment`)
**Created**: 2026-10-16 | **Revised**: 2026-10-16 (v2, serverless first)
**Status**: Draft - planning only, for the human to judge cost and effort before any build
**Input**: "Produce a deployment architecture and a Spec Kit plan for running Story Engine on AWS, so the human can judge effort BEFORE any build work." Revision input: "Follow the Doctor-Assist serverless, cost-optimised design (vault `Projects/Doctor-Assistant/Cloud-Architecture.md`, its spec 008) as the primary candidate."

> Narrative record: vault note `Projects/Story-Engine/AWS-Deployment-Architecture.md` with the
> diagram `Diagrams/AWS-Deployment.excalidraw` (5 views). Research and price sources: [research.md](./research.md).
> Two options are specified: **Option S Serverless (recommended)** and **Option 1 Lean (baseline)**.
> Requirements marked **[OPT-S]** or **[OPT-1]** apply to one option only. Option 2 Managed (Fargate)
> is kept in research.md as a cost line only. Open decisions are marked **[DECIDE Dn]**.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Readers use Story Engine served from AWS (Priority: P1)

A story author opens `storyteller.techvigilant.com`, signs in, generates a story and watches it
stream in, exactly as today, but every request is served from AWS instead of the home server.

**Why this priority**: it is the whole point of the move; nothing else matters if this fails.

**Independent Test**: after cutover, run `e2e/api.spec.ts` and `e2e/frontend.spec.ts` against the
public URL (mocked or real LLM) and check `GET /health` returns `ok`; the SSE stream delivers
`start`, `node_complete` events, `done` for a story that streams longer than 150 seconds.

**Acceptance Scenarios**:

1. **Given** the AWS stack is live, **When** a signed-in user generates a story, **Then** the SSE
   events arrive in order and the story row reaches `completed` in the AWS database.
2. **Given** a node that sends no event for 60 seconds, **When** it runs, **Then** heartbeats keep
   the stream open and no proxy, CDN or function URL closes it early.
3. **Given** an SSLCommerz payment, **When** the gateway posts its IPN, **Then** it reaches the
   backend at `BACKEND_PUBLIC_URL`, passes the signature check and server-side validation.
4. **[OPT-S] Given** the database has been idle and paused, **When** the next user generates a
   story, **Then** the request succeeds (after the resume delay) instead of failing.

### User Story 2 - Operator deploys and rolls back safely (Priority: P1)

The operator merges to `master`; CI builds the image, runs migrations and deploys to AWS without
AWS keys stored in GitHub, then smoke-tests `/health`. A bad release is rolled back in minutes.

**Independent Test**: deploy a tagged release, then roll back to the previous one; both pass `/health`.

**Acceptance Scenarios**:

1. **Given** a green CI run on `master`, **When** the deploy job runs, **Then** it authenticates
   through GitHub OIDC, applies `alembic upgrade head`, deploys and fails if `/health` is not `ok`.
2. **Given** a failed health check, **When** the operator rolls back ([OPT-S] Lambda alias to the
   previous version, [OPT-1] previous image tag), **Then** service is restored within 10 minutes.

### User Story 3 - Data is backed up and restorable (Priority: P2)

**Independent Test**: restore last night's backup ([OPT-S] Aurora point-in-time restore,
[OPT-1] `pg_dump`) into a scratch database and count `stories` rows.

### User Story 4 - Operator sees failures and cost (Priority: P3)

**Independent Test**: break the backend; an alarm notifies the operator within 5 minutes. Every
generation still produces a Langfuse trace. A budget alarm fires before the monthly estimate is exceeded.

### Edge Cases

- Function timeout or host restart mid-stream: the story row ends `failed`, never stuck in
  `running`, and a stuck row does not block the user's quota. [OPT-S] the app's own deadline
  (600 s) fires before the Lambda timeout (900 s).
- [OPT-S] Aurora paused: the Data API returns `DatabaseResumingException`; the app retries with
  backoff for up to 45 s.
- [OPT-S] Concurrency cap reached: the user gets a clear 429/503, not a hung request.
- Anthropic API without credit or unreachable: `/health` stays up; generation returns `error`.
- Langfuse unreachable: generation still succeeds (constitution IV, degrade to no-op).
- SSLCommerz IPN retried: payment confirmation stays idempotent.
- A request that reaches the function URL directly, not through CloudFront: rejected (403).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST serve the SPA and the API from AWS under the existing public hostname.
- **FR-002**: Every hop on the API path MUST allow an SSE response of at least 300 seconds.
  [OPT-S] The backend MUST send an SSE comment at least every 15 seconds (CloudFront waits 30 s per packet).
- **FR-003**: Production MUST run with `LLM_PROVIDER=anthropic` (or `bedrock` if D4 chooses it) and
  MUST fail closed at startup on default secrets (`prod_guard`, HAG-17).
- **FR-004**: Secrets MUST NOT be in git or in the image. [OPT-S] SSM Parameter Store SecureString.
  [OPT-1] root-only env file or SSM Parameter Store.
- **FR-005**: CI/CD MUST authenticate to AWS with GitHub OIDC and a least-privilege deploy role.
- **FR-006**: Each deploy MUST run `alembic upgrade head` before traffic shifts and MUST smoke-test `/health`.
- **FR-007**: Postgres MUST keep the `vector` extension; migration 0003 (`vector(384)`) MUST apply cleanly.
- **FR-008**: Backups MUST be kept at least 7 days and a restore MUST be rehearsed before cutover.
- **FR-009**: An alarm MUST notify the operator on sustained errors or `/health` failure within 5 minutes.
- **FR-010**: Every generation MUST still produce a Langfuse trace (D5). [OPT-S] The trace client
  MUST be flushed before the response ends.
- **FR-011**: The backend MUST use the real client IP behind the proxy for logs and limits.
- **FR-012**: [OPT-S] The function URL MUST reject requests without the CloudFront origin-verify
  secret header; the database MUST have no internet-reachable port. [OPT-1] No inbound port (Cloudflare Tunnel).
- **FR-013**: [OPT-S] The per-user rate limit and monthly quota MUST work without Redis
  (Postgres-backed); LangGraph runs stateless.
- **FR-014**: [OPT-S] A run MUST end (completed or failed, row updated) within 600 s; the quota
  check MUST ignore `running` rows older than 15 minutes.
- **FR-015**: [OPT-S] The embedding model MUST be in the image (read-only file system) and load
  only when `SEMANTIC_CACHE_ENABLED` is on.
- **FR-016**: [OPT-S] Data API calls MUST retry `DatabaseResumingException`; the IAM role MUST allow
  `BeginTransaction`, `CommitTransaction`, `RollbackTransaction`, `ExecuteStatement`, `BatchExecuteStatement`.

### Key Entities

- **Environment**: region (D2), public host, secrets set, image digest, Lambda alias.
- **Release**: image digest (git sha), Lambda version, migration head, deploy time, health result.
- **Rate limit window** [OPT-S]: user id, window start, count (replaces the Redis key).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All Playwright tests that pass locally pass against the AWS deployment (LLM mocked or real).
- **SC-002**: Monthly AWS bill at under 1,000 stories/month stays within the chosen option's
  estimate, LLM tokens excluded: [OPT-S] <= $20 (and <= $5 in a month with no traffic);
  [OPT-1] <= $60.
- **SC-003**: LLM cost per story is unchanged by the move (~$0.0073/story with the chosen models).
- **SC-004**: A deploy from merge to healthy takes <= 15 minutes; a rollback <= 10 minutes.
- **SC-005**: A restore drill recovers data in <= 1 hour.
- **SC-006**: Zero secrets in git, images or CI logs (secret scan before cutover).
- **SC-007**: [OPT-S] p95 time to the first SSE event <= 5 s with the database awake (cold start
  included) and <= 25 s right after a pause.

## Assumptions

- Traffic is low (under 1,000 stories/month, a handful of concurrent streams) for the first months.
- A story runs about 1-2 minutes end to end; this is not measured on the prod models yet.
- The human picks one option and answers D1-D9 in research.md before build work.
- Prod-readiness work in flight (HAG-17 `prod-config-safety`, frontend token, a funded Anthropic
  key) lands first; it is phase P0, not re-specified here.
- Cost impact on tokens (constitution I): none.
- No AWS account, CLI or IaC has been touched; prices are list prices from research.md.
