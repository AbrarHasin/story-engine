# Implementation Plan: News Lens (working name)

**Branch**: `news-lens-plan` (feature `003-news-lens`) | **Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-news-lens/spec.md`; research in [research.md](./research.md); pilot `specs/001-story-engine-baseline`; deployment plan `specs/002-aws-deployment` (branch `aws-deployment-plan`, Option S serverless + Bedrock, deferred).

## Summary

A topic goes in; a sourced report streams out: topic card, event timeline, the mainstream account, the other positions with who holds them, and every key claim rated on a six-point scale with confidence, verbatim evidence quotes and links to documents the system actually fetched. A LangGraph pipeline (built on the pilot's adapter, SSE, cache, quota and auth code, in a new repository per ADR-001) resolves the topic, retrieves from a background RSS index plus free on-demand sources (GDELT, Wikipedia, Wayback, Google Fact Check Tools, CourtListener), clusters articles into events, classifies stances against source tiers, extracts claims, checks existing fact-checks first, verifies the rest with Haiku (Sonnet for at most 3 high-risk claims), and validates every citation in code before anything is shown. Living-person allegations are held for human review. Modelled LLM cost about $0.006 per cold report (all Haiku), about $0.021 with premium verification, $0 on a cache hit. MVP (P0 + P1) is about 39 person-days. Local Docker first; AWS Option S later.

## Technical Context

**Language/Version**: Python 3.12 (backend, workers), TypeScript 5 / React 18 / Vite (frontend), same as the pilot

**Primary Dependencies**: FastAPI, LangGraph 1.x, SQLAlchemy async + Alembic, pgvector, fastembed/sentence-transformers MiniLM-L6 (384-d), trafilatura (Apache-2.0), feedparser (BSD), datasketch (MIT, MinHash), hdbscan or scikit-learn clustering (BSD), httpx, Langfuse v3 (local), pilot `app/llm/adapter.py` (anthropic | local | bedrock)

**Storage**: PostgreSQL 16 + pgvector (articles, claims, ratings, audit); Redis (rate limits, per-domain fetch politeness, job queue in local mode); local disk / S3 (prod) for extracted text blobs with 90-day lifecycle

**Testing**: pytest with mocked LLM and recorded HTTP fixtures (VCR-style cassettes) in CI; contract tests against `contracts/openapi.yaml` and `contracts/sse-events.schema.json`; Playwright e2e on the local stack; offline evaluation harness (gold set, red team) run manually with a spend cap

**Target Platform**: local Docker Compose (api, graph worker, ingest worker, scheduler, postgres, redis, langfuse, frontend); later AWS Option S: Lambda (api, graph with response streaming, ingest on EventBridge Scheduler), Aurora Serverless v2 via Data API, S3 + CloudFront, Bedrock

**Project Type**: web service + SPA + background workers

**Performance Goals**: first stage event <= 5 s; full cold report p95 <= 90 s; cached report <= 3 s; ingestion of ~235 feeds in <= 5 min per cycle

**Constraints**: LLM cost <= $0.02 per cold report (Haiku), <= $0.05 with premium; every LLM call capped; no citation without a stored fetched document; quotes <= 300 chars; robots/terms honoured; no paid API in MVP; no provider SDK in nodes

**Scale/Scope**: MVP: < 1,000 reports/day, ~3,500 new articles/day ingested, English only

## Constitution Check

*GATE: the new repo starts from the Story Engine constitution v1.0.0 and amends it (task T002). Checked against the inherited principles.*

| Principle | Status | Note |
|---|---|---|
| I Token cost primary | PASS with amendment | Cost stated per stage (research R7); caps in settings (`MAX_TOKENS_*` per stage); discarded calls none. Amend: unit is "report" not "story"; sub-agent output is a typed JSON schema per stage instead of "3-5 bullets". |
| II Model tiering | PASS with amendment | Haiku for all stages; Sonnet only as an explicit `verifier_premium` role for at most 3 high-risk claims per report (quality justification: defamation risk), cost delta in R7. |
| III Provider-agnostic | PASS | All LLM calls via `get_adapter().chat(role, ...)`; new roles `resolver`, `stance`, `extractor`, `verifier`, `verifier_premium`, `narrator`. Bedrock adapter shared with spec 002 T044. |
| IV Observable | PASS (local) / AMEND (prod) | Langfuse trace per report locally; prod tracing decision inherits spec 002 D5 amendment. Add: audit log is NOT observability and is never sampled or disabled. |
| V Streaming contract | PASS | New events defined in `contracts/sse-events.schema.json`; pilot events kept; e2e test per event (T046). |
| VI Secure by default | PASS | Pilot JWT, prod fail-closed guard, ownership checks; new `reviewer` and `admin` roles; public submissions rate-limited and captcha'd; fetched text treated as untrusted data (prompt-injection controls). |
| VII Test discipline | PASS | Mocked LLM + HTTP cassettes in CI; no live calls; evaluation is a separate manual, budgeted job. |
| VIII Licensing | PASS | New deps Apache-2.0 / BSD / MIT (GPL-3.0 compatible); Wikipedia text CC BY-SA attributed; datasets licence-checked before use (R6). |
| New principle IX (proposed) Evidence before assertion | ADD | No rating or factual sentence is published unless its citation validates against a stored fetched document; uncertainty defaults to `Unproven`. |
| New principle X (proposed) Harm and fairness | ADD | Living-person rules, no private individuals or minors, right of reply, corrections, append-only audit, published methodology. |

Re-check after Phase 1 design: no violations; amendments listed are additive and land in T002 before code.

## Architecture

### Components

```text
                    +--------------------+         +------------------------------+
  Reader/Journalist |  SPA (React/Vite)  |  fetch  |  API (FastAPI)               |
  ----------------> |  report, claim     | ------> |  auth/quota/billing (pilot)  |
                    |  drawer, sources,  |  SSE    |  reports, claims, sources,   |
                    |  review, exports   | <------ |  submissions, review, watch  |
                    +--------------------+         +--------------+---------------+
                                                                  | invoke
                                         +------------------------v-----------------------+
                                         |  Report graph (LangGraph)                       |
                                         |  resolve -> cache? -> retrieve || factcheck_seed|
                                         |  -> extract_text -> cluster -> stance           |
                                         |  -> claims -> match_factchecks -> evidence      |
                                         |  -> verify (fan-out per claim) -> validate      |
                                         |  -> narrate -> guard -> publish                 |
                                         +----+---------------+---------------+-----------+
                                              |               |               |
          +-----------------------+    +------v-----+  +------v------+  +-----v--------+
  cron -> | Ingest worker (RSS)   | -> | Postgres + |  | Redis       |  | Text blobs   |
          | ~235 feeds / 30 min   |    | pgvector   |  | rate limits |  | (disk / S3)  |
          +-----------------------+    +------------+  +-------------+  +--------------+
  external: RSS feeds, GDELT DOC, Wikipedia, Wayback, Fact Check Tools, CourtListener, LLM (Anthropic local / Bedrock prod)
```

The vault diagram `Projects/News-Lens/Diagrams/News-Lens-Architecture.excalidraw` (+ `.png`) shows the same with a numbered flow.

### LangGraph design (`app/agents/report_graph.py`)

| # | Node | LLM | Writes | Notes |
|---|---|---|---|---|
| 1 | `resolve_topic` | Haiku `resolver`, cap 200 | topic, entities, type, span, key_questions, living_parties, refusal | Refuses private individuals/minors (FR-026); returns candidates when ambiguous (stream `topic` with `needs_choice`, graph ends). |
| 2 | `cache_lookup` | none | cached_report_id | Topic embedding cosine >= 0.92 and within freshness window -> replay (pilot `with_semantic_cache` pattern). |
| 3a | `retrieve` | none | candidates[] | Parallel connectors by topic type (research R2.4); dedup by canonical URL. |
| 3b | `seed_factchecks` | none | factchecks[] | `claims:search` on topic + entities (parallel with 3a). |
| 4 | `extract_text` | none | documents[] | trafilatura with robots/terms policy; hash; blob store. |
| 5 | `cluster` | none | families[], clusters[], timeline[] | MinHash families, embedding clusters, dates. |
| 6 | `stance` | Haiku `stance`, cap 1,000 | positions[] | Per source family x key question; gate FR-013. |
| 7 | `extract_claims` | Haiku `extractor`, cap 1,200 | claims[] | Max 12; checkable flag; living-person flag. |
| 8 | `match_factchecks` | Haiku only for unmapped verdict strings, cap 50 | claim.factcheck | Embedding match >= 0.85 + entity overlap. |
| 9 | `gather_evidence` | none | passages[claim] | Local + Wikipedia + topic docs; rerank. |
| 10 | `verify` (Send fan-out per claim) | Haiku `verifier` cap 300; Sonnet `verifier_premium` for <= 3 high-risk | ratings[] (`Annotated[list, operator.add]`) | Claim-verdict cache checked first (FR-031). |
| 11 | `validate` | none | ratings (fixed), retries | Citation + quote + independence + living-person hold; one retry via conditional edge back to `verify` for failures, then `Unproven`. |
| 12 | `narrate` | Haiku `narrator`, cap 1,600 | sections | Mainstream + positions with `[e:<evidence_id>]` markers; sentences without a valid marker dropped by `validate_narrative` (code). |
| 13 | `guard_publish` | none | report row, audit events | Disclaimers, snippet limits, nofollow flags, review tasks for held claims, audit events, cache write. |

State uses `Annotated[list, operator.add]` for fan-out writes; each node returns only its keys (constitution). Checkpointer: Redis as in the pilot (stateless fallback).

### Ingestion vs on-demand

- **Background**: scheduler (local: APScheduler in the `ingest` container; prod: EventBridge Scheduler -> Lambda) polls feeds every 30 min with ETag/Last-Modified; stores Article metadata + lede + embedding; full text only on demand (keeps storage and robots exposure low). Feeds that fail 3 cycles are marked unhealthy (the vault directory validation rule).
- **On demand**: per report, connectors in parallel with a 25 s retrieval budget; partial results allowed (`stage` event with `degraded`).
- **Re-verification**: daily job re-runs claims past `reverify_at` that belong to reports viewed in the last 30 days (bounded spend: max N per day from settings).

### Caching

| Level | Key | Hit rule | TTL |
|---|---|---|---|
| Report | topic embedding (MiniLM) + topic type | cosine >= 0.92, report age < freshness | breaking 1 h, recent 24 h, historical 30 d |
| Claim verdict | claim embedding + entity set | cosine >= 0.90 and same entities | `reverify_at`: Unproven/Mixed 7 d, others 90 d, breaking 6 h |
| Fact-check lookup | normalised query | exact | 24 h |
| Connector HTTP | URL | exact, ETag aware | GDELT 15 min, Wikipedia 24 h, Wayback 30 d, CourtListener 30 d |
| Extracted text | URL + hash | exact | 90 d then quotes-only |

### Streaming UX

Events (full schema in `contracts/sse-events.schema.json`): `start` -> `topic` (card or `needs_choice`) -> `stage` (retrieve, extract, cluster, stance, claims, verify, narrate; with counts and `degraded`) -> `timeline` -> `perspective` (one per position) -> `claim` (as extracted, rating pending) -> `rating` (per claim, may say `held_for_review`) -> `section` (narrative blocks) -> `done` (report id, cost, tokens, cache_hit, trace url) | `error`. The UI renders skeletons per section and fills them as events arrive; claims show "checking..." until their `rating` arrives.

### Journalist features, auth, quotas, billing

Reused pilot code: JWT login, `enforce_quota` / `enforce_rate_limit` / `record_completion`, plans free/pro/enterprise via SSLCommerz. Mapping: free = 10 reports/month, pro (journalist) = 300 + exports + watches + alerts, enterprise = reviewer seats. Exports: Markdown, JSON, citation list (CSL-JSON). Alerts: in-app in MVP-P2, email later.

### Deployment

Local first: `docker compose` services `api`, `graph` (same image, `RUN_ROLE`), `ingest`, `frontend`, `postgres`, `redis`, `langfuse`; scripts `local-up.sh` / `local-down.sh` copied from the pilot (PR #18). Production later: spec 002 Option S plus an `ingest` Lambda on a schedule; Aurora cannot auto-pause with 30-min ingestion (about $45/month at 0.5 ACU always on) -> decide batch interval at Phase 3 (research R7).

## Project Structure

### Documentation (this feature)

```text
specs/003-news-lens/
├── spec.md
├── plan.md              # this file
├── research.md          # names, ADR-001, retrieval, perspectives, fact-check, legal, cost, eval, risks
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml           # public API
│   ├── sse-events.schema.json # SSE event schema
│   └── rating-scale.md        # ratings, confidence, ClaimReview mapping table
├── checklists/
│   ├── requirements.md        # spec quality
│   └── trust-legal.md         # trust, legal and safety gates
├── analysis.md          # /speckit-analyze report and fixes
└── tasks.md
```

### Source Code (new repository `news-lens`, ADR-001)

```text
backend/
├── app/
│   ├── core/            # copied from pilot: config, auth, database, limits, observability, prod_guard
│   ├── llm/             # copied adapter + new roles (+ bedrock adapter shared with spec 002)
│   ├── payment/         # copied SSLCommerz
│   ├── cache/           # report_cache.py (from pilot semantic cache), verdict_cache.py
│   ├── sources/         # registry.py, tiers.py, import_directory.py
│   ├── retrieval/       # base.py (SearchProvider), rss.py, gdelt.py, wikipedia.py, wayback.py,
│   │                    # factcheck_tools.py, courtlistener.py, extract.py (trafilatura + robots), politeness.py
│   ├── analysis/        # dedup.py (MinHash), cluster.py, timeline.py
│   ├── agents/          # report_state.py, report_graph.py, nodes/{resolve,stance,claims,verify,narrate}.py,
│   │                    # validate.py, guard.py, prompts/ (versioned)
│   ├── trust/           # audit.py (hash chain), submissions.py, review.py, disclaimers.py
│   ├── watch/           # watches.py, alerts.py
│   ├── api/v1/          # reports.py (SSE), claims.py, sources.py, submissions.py, review.py, watches.py,
│   │                    # exports.py, methodology.py, auth.py (pilot)
│   ├── workers/         # ingest.py, reverify.py, scheduler.py
│   └── models/          # db.py, schemas.py
├── alembic/versions/
└── tests/               # unit, contract, integration (cassettes), eval/ (offline harness, gold set)
frontend/src/
├── pages/               # SearchPage, ReportPage, ClaimPage, SourcePage, MethodologyPage, ReviewPage, WatchesPage, LoginPage
├── components/          # TopicCard, Timeline, PerspectiveCard, ClaimRow, RatingBadge, EvidenceQuote, TierChip
├── hooks/useReportStream.ts
└── stores/reportStore.ts
e2e/                     # Playwright: report.spec.ts, trust.spec.ts, review.spec.ts
docker-compose.yml, scripts/local-up.sh, scripts/local-down.sh, infra/ (later, from spec 002)
```

**Structure Decision**: web application layout identical to the pilot (backend + frontend + e2e), plus `workers/` for ingestion and re-verification, in a new repository seeded from the pilot (research R1). Copied files and their source commit are listed in `PLATFORM.md` in the new repo.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Second Sonnet-tier role (`verifier_premium`) beyond the pilot's tiering | Defamation risk on living-person allegations warrants the stronger model for <= 3 claims/report | All-Haiku: cheaper but unmeasured on adversarial claims; a human hold alone delays every such report |
| Background workers (ingest, re-verify) beyond the pilot's single request path | Recent-news coverage and rating freshness need scheduled work | On-demand only: every query would hit 235 feeds and rate limits; stale ratings would never be refreshed |
| New repository instead of a module in the pilot | Different risk, retention and release cadence; live pilot stays stable | Module in pilot (option A) couples deploys and constitutions; monorepo (option C) costs 4-6 pd up front |
