# Specification Analysis Report: News Lens (003)

**Date**: 2026-10-16 | **Artifacts**: spec.md, plan.md, research.md, data-model.md, contracts/, tasks.md, checklists/ | **Constitution**: Story Engine v1.0.0 (inherited; amendments in T002)

Run as `/speckit-analyze` (non-destructive), then findings were fixed in place. Coverage was checked with a script (every `FR-*` and `SC-*` in spec.md searched in tasks.md); contracts were parsed (`openapi.yaml` YAML + all `$ref`s resolve; `sse-events.schema.json` passes the JSON Schema 2020-12 meta-schema).

## Findings

| ID | Category | Severity | Location | Summary | Fix |
|---|---|---|---|---|---|
| A1 | Constitution IV | HIGH | tasks.md | No task attached a Langfuse trace per report ("every generation MUST produce a trace"). | T017 now wires the pilot callback, no-op on failure, trace link in `done`. FIXED |
| A2 | Coverage | MEDIUM | spec FR-033 | Provider-agnostic rule had no task or test. | T014 adds an import test (no provider SDK under `app/agents`). FIXED |
| A3 | Coverage | MEDIUM | spec SC-001, SC-004, SC-007 | Latency, hallucination-rate and SLA criteria had no measuring task. | T060 measures SC-001/SC-004; T050 adds ack/decision metrics for SC-007. FIXED |
| A4 | Inconsistency | MEDIUM | data-model ratings | "Immutable, never updated" contradicted the `held_for_review -> published` transition. | Content write-once; only `status` changes via a trigger that writes an audit event. FIXED |
| A5 | Inconsistency | MEDIUM | openapi `POST /reports` vs SSE `refused_topic` | Resolver refusals happen after the stream starts, so they cannot be HTTP 422. | 422 only for cheap pre-checks; resolver refusals are an `error` event at zero quota. FIXED |
| A6 | Inconsistency | LOW | spec FR-005 vs plan | 171 feeds (spec) vs ~235 (plan). | FR-005 states 171 validated + 64 extra = ~235. FIXED |
| A7 | Inconsistency | LOW | research R6 | Gold set pointed at T060 (harness) instead of T059. | FIXED |
| A8 | Coverage | LOW | FR-022 | Audit retention (6 years) had no task text. | T015 states retention and FR-022. FIXED |
| A9 | Constitution I/II | INFO | plan | Premium Sonnet role and typed JSON stage outputs differ from pilot principles. | Documented in Complexity Tracking; constitution amendment T002 must merge before code. OPEN by design |
| A10 | Constitution IV (prod) | INFO | plan | Production tracing is off under spec 002 D5. | Inherits the spec 002 amendment (T068); audit log never disabled. OPEN by design |
| A11 | Underspecified | INFO | spec open questions | Name, legal review, reviewers, paid API budget, ADR approval, pricing, retention, social scope need the human. | Listed as open questions 1-8. OPEN (human) |

## Coverage summary (after fixes)

| Requirement | Tasks |
|---|---|
| FR-001..FR-004 | T039, T026, T038 |
| FR-005..FR-009 retrieval | T018-T025 |
| FR-010..FR-014 perspectives | T042-T044 |
| FR-015..FR-021 claims, ratings | T022, T029-T036, T048 |
| FR-022..FR-026 trust, legal | T015, T028, T037, T045, T047, T050-T052 |
| FR-027..FR-033 platform | T006, T014, T027, T033, T039, T049, T053-T058 |
| SC-001..SC-008 | T060 (SC-001..006), T050 (SC-007), T063 (SC-008) |

- Requirements: 33 FR, 8 SC; all mapped to at least one task. Tasks: 72, no duplicate ids; every task id cited in `checklists/trust-legal.md` exists.
- Unmapped tasks: setup and scale tasks (T001-T005, T069-T072) by design.

## Metrics

- Critical issues: 0. High: 1 (fixed). Medium: 4 (fixed). Low: 3 (fixed). Info: 3 (open by design or with the human).
- Ambiguity markers (`NEEDS CLARIFICATION`) remaining: 0.

## Next actions

1. Human answers open questions 1, 2, 5 (name, legal review, ADR-001) before T001.
2. T002 constitution amendment before any code.
3. Then `/speckit-implement` from Phase 1.
