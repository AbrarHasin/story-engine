# Feature Specification: Run Story Engine on AWS

**Feature Branch**: `aws-deployment-plan` (spec id `002-aws-deployment`)
**Created**: 2026-10-16
**Status**: Draft - planning only, for the human to judge cost and effort before any build
**Input**: "Produce a deployment architecture and a Spec Kit plan for running Story Engine on AWS, so the human can judge effort BEFORE any build work."

> Narrative record: vault note `Projects/Story-Engine/AWS-Deployment-Architecture.md` with the
> diagram `Diagrams/AWS-Deployment.excalidraw`. Research and price sources: [research.md](./research.md).
> Two options are specified; requirements marked **[OPT-1]** or **[OPT-2]** apply to one option only.
> Open decisions are marked **[DECIDE Dn]** and listed in research.md.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Readers use Story Engine served from AWS (Priority: P1)

A story author opens `storyteller.techvigilant.com`, signs in, generates a story and watches it
stream in, exactly as today, but every request is served from AWS instead of the home server.

**Why this priority**: it is the whole point of the move; nothing else matters if this fails.

**Independent Test**: after cutover, run `e2e/api.spec.ts` and `e2e/frontend.spec.ts` against the
public URL (mocked or real LLM) and check `GET /health` returns `ok`; the SSE stream delivers
`start`, `node_complete` x6, `done` for a story that takes longer than 100 seconds end to end.

**Acceptance Scenarios**:

1. **Given** the AWS stack is live, **When** a signed-in user generates a story, **Then** the SSE
   events arrive in order and the story row reaches `completed` in the AWS database.
2. **Given** a generation that streams for 150 seconds, **When** it runs, **Then** no proxy,
   tunnel or load balancer closes the stream early.
3. **Given** an SSLCommerz payment, **When** the gateway posts its IPN, **Then** it reaches the
   backend at `BACKEND_PUBLIC_URL` and is verified server-side.

### User Story 2 - Operator deploys and rolls back safely (Priority: P1)

The operator merges to `master`; CI builds the image, runs migrations and deploys to AWS without
AWS keys stored in GitHub, then smoke-tests `/health`. A bad release is rolled back in minutes.

**Why this priority**: today `make deploy` runs on the home server; the AWS path must be at least as safe.

**Independent Test**: deploy a tagged release, then deploy the previous tag; both pass `/health`.

**Acceptance Scenarios**:

1. **Given** a green CI run on `master`, **When** the deploy job runs, **Then** it authenticates to
   AWS through GitHub OIDC (no long-lived keys), applies `alembic upgrade head`, deploys and
   fails the job if `/health` is not `ok`.
2. **Given** a failed health check, **When** the operator re-deploys the previous image tag,
   **Then** service is restored within 10 minutes.

### User Story 3 - Data is backed up and restorable (Priority: P2)

**Why this priority**: today there are no automated backups.

**Independent Test**: restore last night's backup into a scratch database and count `stories` rows.

**Acceptance Scenarios**:

1. **Given** the nightly backup ran, **When** it is restored to a scratch database, **Then** row
   counts match production at backup time.

### User Story 4 - Operator sees failures and cost (Priority: P3)

**Independent Test**: stop the backend; an alarm notifies the operator within 5 minutes. Every
generation still produces a Langfuse trace.

### Edge Cases

- Host or task restart mid-stream: the client gets an `error` event or a dropped stream, the
  story row ends `failed`, not stuck in `running`.
- Database disk near full: an alarm fires before writes fail.
- Anthropic API without credit or unreachable: `/health` stays up; generation returns `error`.
- Langfuse unreachable: generation still succeeds (constitution IV, degrade to no-op).
- SSLCommerz IPN retried: payment confirmation stays idempotent.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST serve the SPA and the API from AWS under the existing public hostname.
- **FR-002**: Every hop on the API path (edge, tunnel or load balancer, nginx, uvicorn) MUST allow an
  SSE response of at least 300 seconds without buffering.
- **FR-003**: Production MUST run with `LLM_PROVIDER=anthropic` (or `bedrock` if D4 chooses it) and
  MUST fail closed at startup on default secrets (`prod_guard`, HAG-17).
- **FR-004**: Secrets (JWT, database, Anthropic, SSLCommerz, Langfuse) MUST NOT be in git or in the
  image. [OPT-1] root-only env file or SSM Parameter Store. [OPT-2] Secrets Manager injected into the task.
- **FR-005**: CI/CD MUST authenticate to AWS with GitHub OIDC and a least-privilege deploy role.
- **FR-006**: Each deploy MUST run `alembic upgrade head` before traffic shifts and MUST smoke-test `/health`.
- **FR-007**: Postgres MUST keep the `vector` extension; migration 0003 (`vector(384)`) MUST apply cleanly.
- **FR-008**: Backups MUST run daily, be kept 7 to 30 days, and a restore MUST be rehearsed before cutover.
- **FR-009**: An alarm MUST notify the operator when `/health` fails for 5 minutes or disk/DB storage passes 80%.
- **FR-010**: Every generation MUST still produce a Langfuse trace (self-hosted, or Cloud if D5 amends the constitution).
- **FR-011**: The backend MUST read the real client IP behind the proxy so per-user rate limits work.
- **FR-012**: No inbound port other than the load balancer's 443 [OPT-2] or none at all [OPT-1, Cloudflare Tunnel].
- **FR-013**: [OPT-2] Database and Redis connections MUST use TLS (`DATABASE_URL` with SSL, `rediss://`).

### Key Entities

- **Environment**: region (D2), public hosts, secrets set, image tag.
- **Release**: image tag (git sha), migration head, deploy time, health result.
- **Backup**: time, location (S3 key or snapshot id), size, last restore test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 38 Playwright tests that pass locally pass against the AWS deployment (LLM mocked or real).
- **SC-002**: Monthly AWS bill at low traffic (under 1,000 stories/month) stays within the chosen
  option's estimate: [OPT-1] <= $60, [OPT-2] <= $120 minimal or <= $180 with HA (LLM tokens excluded).
- **SC-003**: LLM cost per story is unchanged by the move (~$0.0073/story with the chosen models).
- **SC-004**: A deploy from merge to healthy takes <= 15 minutes; a rollback <= 10 minutes.
- **SC-005**: A restore drill recovers last night's data in <= 1 hour.
- **SC-006**: Zero secrets in git, images or CI logs (checked with a secret scan before cutover).

## Assumptions

- Traffic is low (under 1,000 stories/month, a handful of concurrent streams) for the first months.
- The human picks one option and answers the open decisions D1-D7 in research.md before build work.
- Prod-readiness work already in flight (HAG-17 `prod-config-safety`, frontend token, a funded
  Anthropic key) lands before cutover; it is counted as phase P0, not re-specified here.
- Cost impact on tokens (constitution I): none. The move changes hosting cost only; per-story LLM
  cost stays ~$0.0073. A Bedrock switch (D4) would need its own cost check.
- No AWS account, CLI or IaC has been touched; prices are list prices from research.md.
