# Specification Analysis Report

**Feature**: 001-story-engine-baseline | **Date**: 2026-10-15 | **Code**: `c2db465`
**Artifacts**: spec.md, plan.md, tasks.md, `.specify/memory/constitution.md` (v1.0.0)
**Run**: speckit-analyze procedure, executed by hand (the skill's prerequisite script needs WSL; plan.md and tasks.md were created in this same pass). Read-only on code.

## Findings

| ID | Category | Severity | Location | Summary | Recommendation |
|----|----------|----------|----------|---------|----------------|
| C1 | Constitution VI | CRITICAL | spec NFR-003; `stories.py:244,269,324`, `personalities.py:38-64` | Spec says "partially"; in code 6 of 10 story/personality endpoints have no auth or ownership check | Task T001-T003; rewrite NFR-003 as "all but 0 endpoints" |
| C2 | Constitution VI | CRITICAL | spec NFR-004; `sslcommerz.py:87,127,141-158` | Payment upgrades dev user only, signature optional, no gateway verification | T004-T006 |
| C3 | Constitution VI | CRITICAL | spec NFR-005; `docker-compose.prod.yml:33` | No fail-closed on default secret; frontend sends no token, so non-dev secret yields 401 everywhere | T007, T008; add FR-019 |
| C4 | Constitution I | CRITICAL | spec NFR-006; `nodes.py:61-76,258-267` | Supervisor result discarded | T009 |
| C5 | Constitution I | HIGH | `nodes.py:63`, `api/v1/llm.py:30` | Two LLM calls use literal `max_tokens` (50, 20), not `Settings.MAX_TOKENS_*` | T010 |
| C6 | Constitution I | HIGH | spec FR-005; `stories.py:105-107` | FR-005 says all per-call usage is accumulated; supervisor usage is dropped, so cost is understated | T012 |
| C7 | Constitution I | MEDIUM | `nodes.py:100,125,150,175` | "3-5 short bullets" is a prompt request only; count is not enforced and failure falls back to one prose bullet | Add a bullet-count check or schema (Pydantic) |
| C8 | Constitution VII | MEDIUM | `backend/tests/test_api.py` | No auth, ownership or payment tests; five smoke tests only | T003, T006 |
| C9 | Constitution VIII | MEDIUM | none | No dependency licence audit exists | T022 |
| C10 | Constitution Workflow | MEDIUM | `Makefile:82` | Smoke test passes on `degraded`; constitution requires a real `/health` check | T019 |
| U1 | Underspecification | HIGH | spec FR-004 | Caps defined per node, but no rule that synthesizer capacity covers writer output; currently 500 vs 1500, truncating the final story | T011; add NFR-008 |
| U2 | Underspecification | HIGH | spec FR-011 | No requirement for frontend authentication (login, bearer header) | T008; add FR-019 |
| U3 | Underspecification | MEDIUM | spec FR-010 / Story entity | `stories.research` column exists but spec does not say it is populated; code never does | T017 |
| U4 | Underspecification | MEDIUM | spec FR-014 | "trace link" not defined: `run_id` is used as a Langfuse trace id without being set as one | T016 |
| A1 | Ambiguity | MEDIUM | spec NFR-007 | "bound spend" has no numbers (stories/month, tokens/day) | Specify free-plan limits from Hub (5/mo) |
| A2 | Ambiguity | LOW | spec SC-003 | "reference machine" undefined (Hub: RTX 2060 6 GB) | Name the hardware |
| A3 | Ambiguity | LOW | spec SC-004 | $0.19 and $0.08 are targets with no measurement method | T014 |
| I1 | Inconsistency | MEDIUM | spec FR-015 vs Hub P2 | Hub says in-memory fallback; code is stateless | Fix Hub wording |
| I2 | Inconsistency | LOW | spec SC-001 vs Hub, Testing.md | 38 tests in code; Hub 32/37, Testing.md 25 | T023 |
| I3 | Inconsistency | LOW | constitution Additional Constraints | Backend dev port 8080 vs Makefile/`main.py` 8000 | T021 |
| D1 | Coverage | LOW | spec FR-001..018 | Built requirements have no tasks (correct for a baseline); regressions covered by existing e2e | none |

## Coverage Summary

| Requirement | Has task? | Task IDs | Notes |
|---|---|---|---|
| NFR-001 prompt caching | yes | T013 | |
| NFR-002 semantic cache | spec only | T015 | needs its own spec and cost estimate |
| NFR-003 ownership | yes | T001-T003 | |
| NFR-004 payment verification | yes | T004-T006 | |
| NFR-005 fail closed | yes | T007 | |
| NFR-006 no discarded calls | yes | T009 | |
| NFR-007 quotas | yes | T018 | needs numbers (A1) |
| SC-004 cost target | yes | T014 | |
| FR-004 caps | yes | T010, T011 | |
| FR-005 accounting | yes | T012 | |
| FR-010 / FR-014 / FR-011 | yes | T017, T016, T008 | |

## Constitution Alignment Issues

Principles I and VI each have MUST violations (C1-C4, C5, C6). Principle IV, VII, VIII and the Development Workflow have partial gaps (C8-C10, U4).

## Unmapped Tasks

T020 (prod compose secrets) maps to constitution VI (secrets), not to a numbered requirement: add NFR-009. T021 and T023 are hygiene with no requirement.

## Metrics

- Requirements: 18 FR + 7 NFR + 4 SC = 29 (plus 2 added by this analysis: FR-019, NFR-008)
- Tasks: 23 | Gap requirements with a task: 8 of 8 (NFR-002 spec-only)
- Ambiguity: 3 | Duplication: 0 | Critical: 4 | High: 4 | Medium: 9 | Low: 4

## Next Actions

Resolve C1-C4 before any new roadmap feature or public sign-up. Suggested order: T001-T003, T007-T008, T004-T006, T011, T009-T012. Roadmap features (streaming, critique loop, HITL, `Send`) each need their own `specs/00N-*` with a cost estimate (constitution Workflow).
