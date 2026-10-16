---

description: "Task list for Parallax (003)"
---

# Tasks: Parallax

**Human decisions (2026-10-16)**: (1) name **Parallax**; (2) ADR-001 approved, new repo `parallax` seeded from Story Engine; (3) **no human review queue**: every claim is shown with its rating, model confidence and source links under an "Automated assessment, not reviewed by a person" label, with the automatic safeguards kept (only fetched documents citable, verbatim quotes, FR-020 independence rule, attributive wording, corrections / right-of-reply contact link); (4) media-law review deferred (the product is a review report); `docs/legal/source-terms.md` stays because it governs what may be fetched. Defaults accepted: free sources only, no social-media claims in MVP, quotes-only retention (FR-034).

**Input**: Design documents from `/specs/003-parallax/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (openapi.yaml, sse-events.schema.json, rating-scale.md)

**Tests**: Included. The constitution (VII) requires mocked-LLM CI tests and a regression test per bug; trust requirements (FR-019..FR-024) are only credible with tests.

**Organization**: by user story. Paths are in the new repository `parallax` (ADR-001); see plan.md "Source Code".

**Owner tags**: `[HUMAN]` needs the human (decision, account, spend); everything else is agent work.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup (P0)

- [ ] T001 (ADR-001 approved 2026-10-16) Create private repo `AbrarHasin/parallax` from the pilot at a recorded commit: copy `backend/app/{core,llm,payment,cache}`, `api/v1/auth.py`, alembic env, `docker-compose.yml`, `scripts/local-{up,down}.sh`, CI; list every copied file with source commit in `PLATFORM.md`; move `specs/003-parallax` into the repo as `specs/001-parallax`
- [ ] T002 Amend `.specify/memory/constitution.md` to v1.1 for Parallax: unit = report, typed JSON per stage, `verifier_premium` role, new principles IX Evidence before assertion and X Harm and fairness (plan.md Constitution Check)
- [ ] T003 [P] CI in `.github/workflows/ci.yml`: ruff + mypy on `backend/app`, pytest (mocked LLM, HTTP cassettes), contract tests, frontend build; no secrets
- [ ] T004 [P] Compose services `api`, `graph`, `ingest`, `frontend`, `postgres`, `redis`, `langfuse` in `docker-compose.yml`; `RUN_ROLE=api|graph|ingest|all`
- [ ] T005 [P] Write `docs/legal/source-terms.md`: robots, terms and allowed use per connector (RSS, GDELT, Wikipedia CC BY-SA, Wayback, Fact Check Tools, CourtListener, NewsAPI, GNews, Guardian) per research R5
- [ ] T006 Settings in `backend/app/core/config.py`: `MAX_TOKENS_{RESOLVER,STANCE,EXTRACTOR,VERIFIER,NARRATOR,MAPPER}`, model roles, cache TTLs (FR-031), `SPEND_CAP_USD`, `PREMIUM_CLAIMS_MAX=3`, retrieval budget 25 s

## Phase 2: Foundational (blocks all stories)

- [ ] T007 Migration `0001_platform` (pilot tables, timestamptz, `users.role`) in `backend/alembic/versions/`
- [ ] T008 [P] Migration `0002_sources_feeds_articles` per data-model.md
- [ ] T009 [P] Migration `0003_topics_reports_clusters`
- [ ] T010 [P] Migration `0004_claims_ratings_evidence_factchecks` (ratings immutable: no UPDATE grant except `status` superseded via trigger)
- [ ] T011 [P] Migration `0005_trust_submissions_audit` and `0006_watches_alerts`
- [ ] T012 Models `backend/app/models/db.py` and schemas `backend/app/models/schemas.py` generated from `contracts/openapi.yaml`
- [ ] T013 Source registry import `backend/app/sources/import_directory.py` (vault directory + `news-feeds-additions-2026-10-16.json`, tiers, state flags, rationale) with test on a fixture copy
- [ ] T014 Adapter roles `resolver, stance, extractor, verifier, verifier_premium, narrator, mapper` in `backend/app/llm/adapter.py`; mock adapter returning recorded JSON in `backend/tests/fakes/llm.py`; test that no module under `app/agents` imports a provider SDK (FR-033)
- [ ] T015 Audit service `backend/app/trust/audit.py` (hash chain, daily digest) + DB rule rejecting UPDATE/DELETE, 6-year retention; test `tests/unit/test_audit.py` (FR-022)
- [ ] T016 `SearchProvider` base, HTTP cassette harness and per-domain politeness limiter (Redis) in `backend/app/retrieval/{base,politeness}.py`
- [ ] T017 Report state `backend/app/agents/report_state.py`, graph skeleton with stub nodes `report_graph.py`, SSE emitter, Langfuse callback per report (pilot `core/observability.py`, no-op when unreachable) with trace link in `done` (constitution IV); contract test validating every emitted event against `contracts/sse-events.schema.json`

**Checkpoint**: skeleton streams stub events that validate against the schema.

## Phase 3: User Story 1 - Sourced report on a topic (P1) MVP

**Goal**: topic in, cited report out, with ratings. **Independent Test**: spec US1.

- [ ] T018 [P] [US1] RSS ingest worker + scheduler `backend/app/workers/{ingest,scheduler}.py` (ETag, Last-Modified, health after 3 failures) (FR-005)
- [ ] T019 [P] [US1] GDELT DOC connector `retrieval/gdelt.py` (1 request / 5 s, artlist + timeline) (FR-006)
- [ ] T020 [P] [US1] Wikipedia (article + references) and Wayback connectors `retrieval/{wikipedia,wayback}.py` (FR-006, FR-009)
- [ ] T021 [US1] Extraction `retrieval/extract.py` (trafilatura; robots.txt, meta robots, X-Robots-Tag; `extraction_basis`; full text only in the transient Redis work cache, TTL 24 h; persist excerpts + hash + metadata); tests: robots honoured, no full text written to the DB (FR-007, FR-034)
- [ ] T022 [P] [US1] Fact Check Tools connector `retrieval/factcheck_tools.py` + mapping loader from `contracts/rating-scale.md` (FR-017)
- [ ] T023 [P] [US1] CourtListener connector `retrieval/courtlistener.py` with daily budget 125 and 30 d cache (FR-006)
- [ ] T024 [US1] Dedup into source families `analysis/dedup.py` (MinHash 0.8) (FR-008)
- [ ] T025 [US1] Clustering + timeline `analysis/{cluster,timeline}.py` (FR-008, FR-009)
- [ ] T026 [US1] `resolve_topic` node + versioned prompt + `needs_choice` flow (FR-002)
- [ ] T027 [US1] `cache_lookup` node (report cache by topic embedding) (FR-031)
- [ ] T028 [US1] Refusal rules for private individuals and minors + test (FR-026)
- [ ] T029 [US1] `extract_claims` node (max 12, checkable flag, living-person flag) (FR-015, FR-016)
- [ ] T030 [US1] `match_factchecks` node (embedding >= 0.85 + entity overlap, mapper fallback) (FR-017)
- [ ] T031 [US1] `gather_evidence` node (passages, rerank, >= 3 families where available) (FR-018)
- [ ] T032 [US1] `verify` node with Send fan-out per claim and premium escalation (<= 3) (FR-018)
- [ ] T033 [US1] Verdict cache `cache/verdict_cache.py` with `reverify_at` (FR-031)
- [ ] T034 [US1] Validator `agents/validate.py`: evidence ids exist, quotes verbatim against stored hash, one retry, else `Unproven`; tests (FR-019, SC-002)
- [ ] T035 [US1] Independence rule for `Verified` / `False`; test (FR-020)
- [ ] T036 [US1] Living-person allegation safeguards (no hold): attributive-wording check on claim, reason and narrative, FR-020 cap on `Verified` / `False`; test (FR-021)
- [ ] T037 [US1] `guard_publish`: snippet limits, disclaimers, `assessment_label` on every rating, corrections contact link, audit events; test (FR-024, FR-025)
- [ ] T038 [US1] `narrate` node + narrative validator dropping unmarked sentences; test (FR-003, FR-004)
- [ ] T039 [US1] `POST /api/v1/reports` (SSE, quota unit, 402/422/429) + `GET /api/v1/reports[/{id}]`; contract tests (FR-001, FR-030)
- [ ] T040 [US1] Frontend `SearchPage`, `ReportPage`, `useReportStream.ts`, `reportStore.ts`, components `TopicCard`, `Timeline`, `ClaimRow`, `RatingBadge`, `EvidenceQuote`
- [ ] T041 [US1] Playwright `e2e/report.spec.ts` on the Michael Jackson fixture (quickstart step 3)

## Phase 4: User Story 2 - Who says what, no false balance (P1) MVP

- [ ] T042 [US2] `stance` node, perspective gate (standing or >= 5 % coverage) and evidence-weighted ordering; false-balance fixture test (FR-012, FR-013)
- [ ] T043 [US2] Link policy: `nofollow ugc`, no preview, no quoting beyond claim text for `social` / low-support sources (API flag + `PerspectiveCard`, `TierChip`); test (FR-014)
- [ ] T044 [US2] `GET /api/v1/sources[/{id}]`, `SourcePage`, tier criteria on `MethodologyPage` (FR-010, FR-011)

## Phase 5: User Story 3 - Trust every rating (P1) MVP

- [ ] T045 [US3] `GET /api/v1/claims/{id}` and `/history`, `ClaimPage` drawer; test that ratings are never updated in place (FR-022)
- [ ] T046 [US3] One e2e assertion per SSE event type (constitution V) in `e2e/trust.spec.ts`
- [ ] T047 [US3] `GET /api/v1/methodology` from `contracts/rating-scale.md`, disclaimer and CC BY-SA attribution on every report; test (FR-025)
- [ ] T048 [US3] Corrections / right-of-reply contact link on every report and claim (`CORRECTIONS_CONTACT` setting) and the "Automated assessment, not reviewed by a person" label in `RatingBadge`; test (FR-023 MVP part, FR-025)
- [ ] T049 [US3] Per-stage token, LLM and search cost accounting in `done` and `reports` (FR-032)

**Checkpoint (MVP)**: US1-US3 pass; then Phase 9 evaluation gates.

## Phase 6: User Story 4 - Corrections, replies, takedowns (P2)

- [ ] T050 [US4] `POST /api/v1/submissions` + status by tracking code, captcha, rate limit, audit, correction -> re-verification job; acknowledgement email and time-to-ack / time-to-decision metrics on the admin page (FR-023, SC-007)
- [ ] T051 [US4] Operator admin action (audited) accepts a reply or a takedown; accepted replies rendered beside the claim; claim re-verified (FR-023)
- [ ] T052 [US4] Takedown action hides snippet, keeps link, audited; test (FR-023, FR-024)

## Phase 7: User Story 5 - Journalist workspace (P2)

- [ ] T053 [P] [US5] Export Markdown / JSON / CSL-JSON `api/v1/exports.py` (FR-027)
- [ ] T054 [P] [US5] Watches + alerts (new coverage, new fact-check, rating changed) `watch/` + API (FR-028)
- [ ] T055 [US5] Plan mapping: journalist plan quotas, roles, SSLCommerz product (FR-030) [HUMAN: pricing]
- [x] T056 *Removed 2026-10-16: no human review queue (human decision 3).*

## Phase 8: User Story 6 - Fast repeat questions (P2)

- [ ] T057 [US6] Report freshness by topic type, "refresh" action counted as quota (FR-031, FR-030)
- [ ] T058 [US6] Re-verification worker `workers/reverify.py` with daily spend bound (FR-031)

## Phase 9: Evaluation and launch gates (part of MVP)

- [ ] T059 Gold set builder `tests/eval/gold/` (200 ClaimReview claims across >= 8 IFCN publishers, 100 from licence-checked research sets; publisher article excluded from evidence) (SC-003)
- [ ] T060 Evaluation harness `tests/eval/run.py`: agreement, macro-F1, inversion, ECE, citation validity, unsupported sentences, living-person attribution compliance, cost, latency p95 cold and cached (SC-001, SC-002, SC-003, SC-004, SC-005, SC-006)
- [ ] T061 Red-team topics + prompt-injection and flooding fixtures `tests/eval/redteam/`; CI runs the mocked subset (SC-005)
- [ ] T062 [HUMAN approves spend] Budgeted live evaluation run (about $0.30 cap, research R6)
- [ ] T063 [HUMAN] Usability test with 10 readers (SC-008)

## Phase 10: Production (P3)

- [ ] T064 Ingest Lambda on EventBridge Scheduler in `infra/template.yaml` (reuse spec 002 Option S)
- [ ] T065 Aurora awake-cost decision: ingestion batch interval or S3 buffering (research R7)
- [ ] T066 Bedrock adapter (shared with spec 002 T044) + verify Bedrock prices for Haiku/Sonnet 5.5
- [x] T067 *Deferred 2026-10-16 (human decision 4): media-law review is not an MVP or P3 gate; the product is a review report.*
- [ ] T068 Production tracing decision (inherits spec 002 constitution IV amendment); audit log stays on

## Phase 11: Scale (P4)

- [ ] T069 [P] Multilingual evidence with marked machine translation
- [ ] T070 [P] Paid search adapters (NewsAPI, GNews, Brave) behind flags [HUMAN: budget]
- [ ] T071 [P] Social-claim tracking for "also circulating" (link-only)
- [ ] T072 [P] Embeddable widget / browser extension

## Dependencies & Execution Order

- Phase 1 -> Phase 2 -> US1 (Phase 3) -> US2, US3 (can run in parallel after T039) -> Phase 9 gates -> public beta.
- US4-US6 depend on Phase 2 and T039; independent of each other.
- T034-T038 depend on T029-T032; T040 depends on T017 schema; T048 depends on T037.
- Phase 10 depends on the human's go for AWS (spec 002 deferred).

## Effort by phase (research R8)

| R8 phase | Tasks | pd |
|---|---|---|
| P0 Foundations | T001-T017 | 5 |
| P1 MVP | T018-T049, T059-T061 | 33 |
| P2 Trust ops and journalists | T050-T058 | 10 |
| P3 Production | T064-T068 | 7 |
| P4 Scale | T069-T072 | 16 |
| Human-only | T055 pricing, T062, T063, T070 budget | - |

## Parallel Example: User Story 1

```bash
Task: "T018 RSS ingest worker"     Task: "T019 GDELT connector"
Task: "T020 Wikipedia + Wayback"   Task: "T022 Fact Check Tools"   Task: "T023 CourtListener"
```

## Implementation Strategy

MVP first: Phases 1-5 + Phase 9, validate against SC-002..SC-005 on fixtures, one budgeted live run, then a private beta. P2 trust operations (Phase 6) before any public launch.
